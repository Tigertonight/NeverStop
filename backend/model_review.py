from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


ALLOWED_VERDICTS = {"supported", "insufficient_evidence"}


def _json_from_text(value: str) -> dict:
    text = value.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("model response is not an object")
    return parsed


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
    endpoint = custom_endpoint or (f"{minimax_base_url}/anthropic/v1/messages" if minimax_key else "")
    if not endpoint:
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
