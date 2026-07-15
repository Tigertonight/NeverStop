from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request


ALLOWED_VERDICTS = {"supported", "insufficient_evidence"}

DEFAULT_OPENCODE_MODEL = "dibp/claude-4.8-opus"


def _opencode_enabled() -> bool:
    return os.getenv("NEVERSTOP_REVIEW_OPENCODE", "").strip().lower() in {"1", "true", "yes", "on"}


def review_provider() -> tuple[str, bool]:
    """Return (providerLabel, configured) for health reporting."""
    if _opencode_enabled() and shutil.which(_opencode_bin()):
        return "opencode-cli", True
    if os.getenv("NEVERSTOP_MODEL_REVIEW_URL", "").strip():
        return "custom-endpoint", True
    if os.getenv("MINIMAX_ACCESS_TOKEN") or os.getenv("MINIMAX_API_KEY"):
        return "minimax-direct", True
    return "engineering-fallback", False


def _opencode_bin() -> str:
    return os.getenv("NEVERSTOP_REVIEW_OPENCODE_BIN", "opencode").strip() or "opencode"


def _opencode_model() -> str:
    return os.getenv("NEVERSTOP_REVIEW_OPENCODE_MODEL", DEFAULT_OPENCODE_MODEL).strip() or DEFAULT_OPENCODE_MODEL


def _text_from_opencode_jsonl(stdout: str) -> str:
    """Extract concatenated assistant text from opencode `--format json` JSONL event stream."""
    chunks: list[str] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("type") != "text":
            continue
        part = event.get("part")
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            chunks.append(part["text"])
    return "".join(chunks).strip()


def _run_opencode_once(prompt: str) -> str:
    """Invoke opencode CLI once and return the concatenated assistant text."""
    binary = shutil.which(_opencode_bin())
    if not binary:
        raise ValueError("opencode CLI not found on PATH")
    timeout = float(os.getenv("NEVERSTOP_REVIEW_OPENCODE_TIMEOUT", "90"))
    completed = subprocess.run(
        [binary, "run", "--pure", "-m", _opencode_model(), "--format", "json"],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()[:120]
        raise ValueError(f"opencode run failed (exit {completed.returncode}): {detail}")
    output = _text_from_opencode_jsonl(completed.stdout or "")
    if not output:
        raise ValueError("opencode run produced no assistant text")
    return output


def _review_via_opencode(prompt: str, report: dict) -> dict:
    """Run the local opencode CLI as the review model, retrying with correction on invalid output."""
    attempts = max(1, int(os.getenv("NEVERSTOP_REVIEW_OPENCODE_RETRIES", "2")))
    current_prompt = prompt
    last_error: Exception | None = None
    for _ in range(attempts):
        raw = _run_opencode_once(current_prompt)
        try:
            return _validate_review(_json_from_text(raw), report)
        except (ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            current_prompt = (
                prompt
                + "\n\n上一次输出不合规：" + str(exc).strip()[:120]
                + "\n请严格按要求重新只输出一个合法 JSON 对象，verdict 必须是 supported 或 insufficient_evidence，supported 时 evidenceIds 恰好 1 个 id。"
            )
    raise last_error if last_error else ValueError("opencode review failed")


def _json_from_text(value: str) -> dict:
    text = value.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = json.loads(_extract_json_object(text))
    if not isinstance(parsed, dict):
        raise ValueError("model response is not an object")
    return parsed


def _extract_json_object(text: str) -> str:
    """Extract the first brace-balanced JSON object from mixed text (handles strings/escapes)."""
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object found in model response")
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise ValueError("unterminated JSON object in model response")


def _review_from_response(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("invalid model response")
    if payload.get("verdict") in ALLOWED_VERDICTS:
        return payload
    for key in ("assistant_message", "message", "text", "reply"):
        if isinstance(payload.get(key), str) and payload[key].strip():
            return _json_from_text(payload[key])
    nested = payload.get("data")
    if isinstance(nested, dict):
        return _review_from_response(nested)
    content = payload.get("content")
    if isinstance(content, list):
        text = "".join(str(item.get("text") or "") for item in content if isinstance(item, dict) and item.get("type") == "text")
        if text.strip():
            return _json_from_text(text)
    raise ValueError("model response has no review payload")


def _validate_review(payload: object, report: dict) -> dict:
    if not isinstance(payload, dict) or payload.get("verdict") not in ALLOWED_VERDICTS:
        raise ValueError("invalid verdict")
    evidence_ids = {item["id"] for item in report.get("insights", [])}
    supplied_ids = payload.get("evidenceIds", [])
    if not isinstance(supplied_ids, list) or any(item not in evidence_ids for item in supplied_ids):
        raise ValueError("review referenced unknown evidence")
    if payload["verdict"] == "supported":
        replacements = {
            "膝关节负荷": "腿部负担",
            "关节负荷": "动作负担",
            "受伤": "动作代偿",
            "损伤": "动作负担",
            "疼痛": "不适",
            "伤病": "身体负担",
            "治疗": "调整",
            "康复": "恢复训练",
        }
        for key in ("problem", "impact", "action", "successCue"):
            if isinstance(payload.get(key), str):
                for source, target in replacements.items():
                    payload[key] = payload[key].replace(source, target)
        required = ("issueType", "problem", "impact", "action", "successCue", "confidence")
        if any(not payload.get(key) for key in required):
            raise ValueError("supported review is incomplete")
        confidence = float(payload["confidence"])
        if not 0 <= confidence <= 1:
            raise ValueError("invalid confidence")
        if len(supplied_ids) != 1:
            raise ValueError("review must select exactly one primary evidence")
        for key, limit in (("problem", 60), ("impact", 100), ("action", 100), ("successCue", 80)):
            if len(str(payload[key])) > limit:
                raise ValueError(f"{key} is too long")
        if any(token in str(payload["action"]) for token in ("1)", "2)", "1.", "2.", "；2", "；3")):
            raise ValueError("review action contains multiple drills")
    return payload


def review_report(report: dict) -> dict:
    custom_endpoint = os.getenv("NEVERSTOP_MODEL_REVIEW_URL", "").strip()
    minimax_key = (os.getenv("MINIMAX_ACCESS_TOKEN") or os.getenv("MINIMAX_API_KEY") or "").strip()
    minimax_model = os.getenv("MINIMAX_MODEL", "MiniMax-M3").strip()
    minimax_base_url = os.getenv("MINIMAX_BASE_URL", "https://api.minimaxi.com").rstrip("/")
    use_opencode = _opencode_enabled()
    endpoint = custom_endpoint or (f"{minimax_base_url}/anthropic/v1/messages" if minimax_key else "")
    if not endpoint and not use_opencode:
        return {"status": "engineering_fallback", "reason": "未配置多模态复核服务。", "evidenceValidated": False}

    request_payload = {
        "schemaVersion": "coach-review-1",
        "stroke": report.get("swimStroke"),
        "qualityAssessment": report.get("qualityAssessment"),
        "cycles": report.get("cycles"),
        "candidates": [
            {
                "id": item["id"],
                "title": item["title"],
                "summary": item["summary"],
                "severity": item.get("severity"),
                "timestamp": item["timestamp"],
                "image": item.get("image"),
                "clip": item.get("clip"),
            }
            for item in report.get("insights", [])
        ],
    }
    is_minimax_direct = not custom_endpoint and bool(minimax_key)
    review_prompt = (
        "你是运动动作证据复核员。你没有直接看到图片或视频，只能根据给定的工程候选和元数据复核。"
        "不得描述输入中没有提供的角度、关节形态、水花、声音、身体位置或医疗风险。"
        "最多选择一个最值得优先改进的问题；severity=good 的候选是正反馈，禁止选为问题。若证据不足就返回 insufficient_evidence。"
        "输出纯 JSON，字段必须为 verdict、evidenceIds。supported 时 evidenceIds 必须且只能包含一个候选 id，"
        "并输出 issueType、problem、impact、action、successCue、confidence。action 只能是一项可执行练习，不得编号或并列多项。"
        "problem 不超过60字，impact/action 不超过100字，successCue 不超过80字。verdict 只能是 supported 或 insufficient_evidence。输入："
        + json.dumps(request_payload, ensure_ascii=False)
    )
    if use_opencode:
        strict_suffix = (
            "\n\n严格输出要求（务必遵守）："
            "\n1) 只输出一个 JSON 对象，直接以 { 开头、以 } 结尾；禁止任何解释、思考过程、markdown 代码块或前后文字。"
            "\n2) verdict 的值只能是字符串 \"supported\" 或 \"insufficient_evidence\"，不得使用 pass/fail/ok 等其它词。"
            "\n3) 若证据充分只选一个最该改的问题：verdict=\"supported\"，evidenceIds 恰好含 1 个候选 id，且必须同时给出 issueType、problem、impact、action、successCue、confidence(0~1 的数字)。"
            "\n4) 若证据不足：verdict=\"insufficient_evidence\"，evidenceIds 为空数组 []。"
            "\n5) severity 为 good 的候选是正反馈，禁止选为问题。"
        )
        try:
            review = _review_via_opencode(review_prompt + strict_suffix, report)
        except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
            detail = str(exc).strip()[:100]
            return {"status": "engineering_fallback", "reason": f"本地 opencode 复核不可用，已安全降级：{type(exc).__name__}{f'（{detail}）' if detail else ''}", "evidenceValidated": False}
        return {"status": "reviewed", "reason": f"候选问题已通过本地 opencode（{_opencode_model()}）结构化复核。", "evidenceValidated": review["verdict"] == "supported", "result": review}
    if is_minimax_direct:
        request_payload = {
            "model": minimax_model,
            "max_tokens": 500,
            "temperature": 0.2,
            "system": "你只做结构化运动证据复核，只输出合法 JSON。",
            "messages": [{"role": "user", "content": review_prompt}],
        }
    headers = {"Content-Type": "application/json"}
    if is_minimax_direct:
        headers.update({"Authorization": f"Bearer {minimax_key}", "anthropic-version": "2023-06-01"})
    token = os.getenv("NEVERSTOP_MODEL_REVIEW_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(endpoint, data=json.dumps(request_payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=float(os.getenv("NEVERSTOP_MODEL_REVIEW_TIMEOUT", "18"))) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
            review = _validate_review(_review_from_response(response_payload), report)
    except (OSError, ValueError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        provider = "MiniMax 结构化复核" if is_minimax_direct else "模型复核"
        detail = str(exc).strip()[:80]
        return {"status": "engineering_fallback", "reason": f"{provider}不可用，已安全降级：{type(exc).__name__}{f'（{detail}）' if detail else ''}", "evidenceValidated": False}

    provider = "MiniMax" if is_minimax_direct else "模型服务"
    return {"status": "reviewed", "reason": f"候选问题已通过{provider}结构化复核。", "evidenceValidated": review["verdict"] == "supported", "result": review}
