"""ALG-002 抽帧率消融实验：在真实/合成片段上扫描不同目标采样帧率，
量化采样率对「泳姿分类稳定性 / 关键运动信号收敛 / 分析耗时」的影响，
用来判断当前自适应采样率（≤30s:10fps, ≤60s:8fps, >60s:5fps）是否接近最优。

用法：
    .venv/bin/python -m backend.eval.sample_rate_ablation \
        --manifest backend/eval/manifest.json \
        --rates 3 5 8 10 12 15 \
        --json backend/eval/ablation_report.json

设计思路：
- 把「高采样率结果」当作近似参照（ground truth 的稳定值），
  观察低采样率相对参照的偏差随采样率下降如何变化。
- 找到「偏差收敛、再提高采样率也几乎不变」的拐点，即性价比最优采样率。
- 输出每档：抽帧数、检测率、泳姿+置信度、armSynchrony 等信号、耗时。

注意：本脚本不做医疗判断；仅衡量二维姿态观察指标随采样率的数值稳定性。
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from backend.analyzer import (
    AnalysisError,
    _classify_swim_stroke,
    _extract_pose_frames,
    _running_measurements,
    _swimming_measurements,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RATES = [3.0, 5.0, 8.0, 10.0, 12.0, 15.0]


def _noop_progress(_value: int, _stage: str) -> None:
    return None


@dataclass
class RateResult:
    sampleFps: float
    targetSampleFps: float
    sampledFrames: int
    detectedFrames: int
    detectionRatio: float
    confidence: float
    extractSeconds: float
    # 游泳专属
    stroke: str | None = None
    strokeConfidence: float | None = None
    armSynchrony: float | None = None
    legSynchrony: float | None = None
    # 通用运动信号（用于稳定性比较）
    signals: dict[str, float] = field(default_factory=dict)
    error: str | None = None


@dataclass
class ClipAblation:
    path: str
    sport: str
    durationSeconds: float
    fps: float
    results: list[RateResult] = field(default_factory=list)
    reference: dict[str, Any] = field(default_factory=dict)
    verdict: dict[str, Any] = field(default_factory=dict)


def _measure(sport: str, pose_frames: list) -> tuple[dict[str, float], dict]:
    """返回该运动的核心稳定性信号 + 泳姿分类（仅游泳）。"""
    if sport == "swimming":
        measurements, _ = _swimming_measurements(pose_frames)
        stroke_info = _classify_swim_stroke(pose_frames)
        return measurements, stroke_info
    measurements, _ = _running_measurements(pose_frames)
    return measurements, {}


def _run_rate(path: Path, sport: str, rate: float) -> RateResult:
    started = time.perf_counter()
    try:
        pose_frames, meta = _extract_pose_frames(path, _noop_progress, sample_fps_override=rate)
    except AnalysisError as exc:
        return RateResult(
            sampleFps=rate, targetSampleFps=rate, sampledFrames=0, detectedFrames=0,
            detectionRatio=0.0, confidence=0.0, extractSeconds=time.perf_counter() - started,
            error=f"{exc.code}: {exc.message}",
        )
    measurements, stroke_info = _measure(sport, pose_frames)
    signals = stroke_info.get("signals", {}) if stroke_info else {}
    return RateResult(
        sampleFps=round(float(meta["sampleRateFps"]), 3),
        targetSampleFps=round(float(meta["targetSampleFps"]), 3),
        sampledFrames=int(meta["sampledFrames"]),
        detectedFrames=int(meta["detectedFrames"]),
        detectionRatio=round(float(meta["detectionRatio"]), 4),
        confidence=round(float(meta["confidence"]), 2),
        extractSeconds=round(time.perf_counter() - started, 2),
        stroke=stroke_info.get("stroke") if stroke_info else None,
        strokeConfidence=stroke_info.get("confidence") if stroke_info else None,
        armSynchrony=signals.get("armSynchrony"),
        legSynchrony=signals.get("legSynchrony"),
        signals={k: round(float(v), 4) for k, v in measurements.items() if isinstance(v, (int, float))},
    )


def _relative_deviation(value: float, reference: float) -> float:
    denom = abs(reference) if abs(reference) > 1e-6 else 1.0
    return abs(value - reference) / denom


def _analyze_convergence(clip: ClipAblation) -> None:
    """以最高采样率结果为参照，找出信号收敛（偏差 <10%）的最低采样率。"""
    ok = [r for r in clip.results if r.error is None]
    if len(ok) < 2:
        clip.verdict = {"note": "有效采样档不足，无法评估收敛。"}
        return
    ok.sort(key=lambda r: r.sampleFps)
    ref = ok[-1]  # 最高采样率作参照
    clip.reference = {
        "sampleFps": ref.sampleFps,
        "stroke": ref.stroke,
        "signals": ref.signals,
        "armSynchrony": ref.armSynchrony,
    }
    # 选一组代表性信号做偏差比较
    key_signals = [k for k in ref.signals if k in {
        "cadenceSpm", "headDeviation", "bodyIssue", "reachAsymmetry",
        "kneeFlexion", "strideBalance", "trunkLean",
    } and ref.signals[k]] or list(ref.signals)[:4]

    convergence_rate: float | None = None
    stroke_stable_rate: float | None = None
    rows = []
    for r in ok:
        devs = [_relative_deviation(r.signals.get(k, 0.0), ref.signals.get(k, 0.0)) for k in key_signals]
        max_dev = max(devs) if devs else 0.0
        stroke_match = (r.stroke == ref.stroke)
        rows.append({
            "sampleFps": r.sampleFps,
            "maxSignalDeviation": round(max_dev, 4),
            "strokeMatchesRef": stroke_match,
            "stroke": r.stroke,
            "strokeConfidence": r.strokeConfidence,
            "extractSeconds": r.extractSeconds,
            "detectionRatio": r.detectionRatio,
        })
        if max_dev <= 0.10 and convergence_rate is None:
            convergence_rate = r.sampleFps
        if stroke_match and stroke_stable_rate is None:
            stroke_stable_rate = r.sampleFps

    clip.verdict = {
        "keySignals": key_signals,
        "perRate": rows,
        "signalConverged>=Fps": convergence_rate,
        "strokeStable>=Fps": stroke_stable_rate,
        "referenceFps": ref.sampleFps,
    }


def load_manifest(path: Path) -> list[tuple[Path, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    base = path.parent
    clips = []
    for entry in data.get("clips", []):
        p = Path(entry["path"])
        if not p.is_absolute():
            p = (base / p).resolve()
        clips.append((p, entry["sport"]))
    return clips


def main() -> int:
    parser = argparse.ArgumentParser(description="抽帧率消融实验")
    parser.add_argument("--manifest", type=Path, required=True, help="clips 清单（同 run_eval 格式）")
    parser.add_argument("--rates", type=float, nargs="+", default=DEFAULT_RATES, help="要扫描的目标采样帧率列表")
    parser.add_argument("--json", type=Path, default=None, help="输出 JSON 报告路径")
    args = parser.parse_args()

    clips = load_manifest(args.manifest)
    if not clips:
        print("manifest 未包含任何 clip。")
        return 1

    import cv2  # 延迟导入，读取时长/fps

    all_ablations: list[ClipAblation] = []
    rates = sorted(set(args.rates))

    for path, sport in clips:
        if not path.exists():
            print(f"跳过（文件不存在）：{path}")
            continue
        cap = cv2.VideoCapture(str(path))
        fps = float(cap.get(cv2.CAP_PROP_FPS)) or 0.0
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
        duration = (frame_count / fps) if fps else 0.0

        ablation = ClipAblation(path=str(path), sport=sport, durationSeconds=round(duration, 2), fps=round(fps, 2))
        print(f"\n=== {path.name} | {sport} | {duration:.1f}s @ {fps:.0f}fps ===")
        print(f"{'sampleFps':>10} {'sampled':>8} {'detRatio':>9} {'conf':>6} {'stroke':>12} {'strkConf':>9} {'armSync':>8} {'sec':>6}")
        for rate in rates:
            r = _run_rate(path, sport, rate)
            ablation.results.append(r)
            if r.error:
                print(f"{rate:>10.1f}  ERROR: {r.error}")
                continue
            print(
                f"{r.sampleFps:>10.2f} {r.sampledFrames:>8d} {r.detectionRatio:>9.3f} "
                f"{r.confidence:>6.1f} {str(r.stroke):>12} "
                f"{('' if r.strokeConfidence is None else f'{r.strokeConfidence:.0f}'):>9} "
                f"{('' if r.armSynchrony is None else f'{r.armSynchrony:.3f}'):>8} {r.extractSeconds:>6.2f}"
            )
        _analyze_convergence(ablation)
        v = ablation.verdict
        print(
            f"-> 参照={v.get('referenceFps')}fps | 信号收敛(≤10%偏差)最低采样率="
            f"{v.get('signalConverged>=Fps')}fps | 泳姿稳定最低采样率={v.get('strokeStable>=Fps')}"
        )
        all_ablations.append(ablation)

    payload = {"clips": [asdict(a) for a in all_ablations], "ratesTested": rates}
    if args.json:
        args.json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n报告已写入 {args.json}")

    _print_summary(all_ablations)
    return 0


def _print_summary(ablations: list[ClipAblation]) -> None:
    print("\n===== 结论 =====")
    for a in ablations:
        v = a.verdict
        conv = v.get("signalConverged>=Fps")
        stroke_stable = v.get("strokeStable>=Fps")
        current = 10.0 if a.durationSeconds <= 30 else 8.0 if a.durationSeconds <= 60 else 5.0
        current = min(current, a.fps)
        msg = f"{Path(a.path).name}（{a.durationSeconds:.0f}s, 当前策略≈{current:.0f}fps）："
        if conv is None:
            msg += "信号未在测试区间内收敛，建议提高采样率。"
        elif conv <= current:
            msg += f"信号在 {conv:.0f}fps 即收敛，当前 {current:.0f}fps 足够（或可下调至 {conv:.0f}fps 省时）。"
        else:
            msg += f"信号要到 {conv:.0f}fps 才收敛，当前 {current:.0f}fps 偏低，建议提高。"
        if stroke_stable is not None:
            msg += f" 泳姿分类在 ≥{stroke_stable:.0f}fps 与最高档一致。"
        print(msg)


if __name__ == "__main__":
    raise SystemExit(main())
