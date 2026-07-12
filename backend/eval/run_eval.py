"""ALG-001 离线评测：在带标签的视频片段上运行真实分析管线，
输出运动识别准确率、混淆矩阵、置信度与拍摄质量分布。

用法：
    .venv/bin/python -m backend.eval.run_eval               # 使用内置合成样本
    .venv/bin/python -m backend.eval.run_eval --manifest path/to/manifest.json
    .venv/bin/python -m backend.eval.run_eval --json report.json

manifest.json 结构（用于接入真实授权片段，见 backend/eval/README.md）：
    {
      "clips": [
        {"path": "clips/run_01.mp4", "sport": "running", "note": "侧面固定机位"},
        {"path": "clips/swim_02.mp4", "sport": "swimming"}
      ]
    }
所有相对路径以 manifest 文件所在目录为基准。

注意：本脚本不做医疗判断；内置样本仅用于验证管线连通与回归，
数值不代表真实运动学测量。
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2

from backend.analyzer import AnalysisError, analyze_video

ROOT = Path(__file__).resolve().parents[2]
SPORTS = ("running", "swimming")


@dataclass
class ClipSpec:
    path: Path
    sport: str
    note: str = ""


@dataclass
class ClipResult:
    path: str
    expected_sport: str
    ok: bool
    predicted_sport: str | None = None
    detected_sport: str | None = None
    error_code: str | None = None
    confidence: float | None = None
    detection_ratio: float | None = None
    capture_quality: str | None = None
    seconds: float = 0.0
    note: str = ""


@dataclass
class EvalSummary:
    results: list[ClipResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def classified(self) -> list[ClipResult]:
        # 成功产出报告（未被 AnalysisError 拒绝）的片段
        return [item for item in self.results if item.ok]

    @property
    def correct(self) -> int:
        return sum(1 for item in self.classified if item.predicted_sport == item.expected_sport)

    @property
    def accuracy(self) -> float:
        graded = self.classified
        return self.correct / len(graded) if graded else 0.0

    def confusion(self) -> dict[str, dict[str, int]]:
        labels = list(SPORTS) + ["rejected"]
        matrix = {expected: {predicted: 0 for predicted in labels} for expected in SPORTS}
        for item in self.results:
            if item.expected_sport not in matrix:
                continue
            key = item.predicted_sport if item.ok and item.predicted_sport in SPORTS else "rejected"
            matrix[item.expected_sport][key] += 1
        return matrix

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "classified": len(self.classified),
            "correct": self.correct,
            "accuracy": round(self.accuracy, 4),
            "confusion": self.confusion(),
            "clips": [vars(item) for item in self.results],
        }


def _build_synthetic_clips(directory: Path) -> list[ClipSpec]:
    """从内置素材生成带真实位移的合成片段，作为无外部数据时的默认评测集。"""
    specs: list[ClipSpec] = []
    plan = [
        ("runner.jpg", "running", "合成·跑步·水平往复位移"),
        ("swimmer.jpg", "swimming", "合成·游泳·水平往复位移"),
    ]
    for source_name, sport, note in plan:
        source = cv2.imread(str(ROOT / "src" / "assets" / source_name))
        if source is None:
            raise FileNotFoundError(f"缺少内置素材 {source_name}")
        base = cv2.resize(source, (720, 405), interpolation=cv2.INTER_AREA)
        height, width = base.shape[:2]
        out_path = directory / f"synthetic_{sport}.mp4"
        writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), 12, (640, 360))
        if not writer.isOpened():
            raise RuntimeError("无法创建合成视频写入器")
        for index in range(144):
            shift = int(20 * ((index % 24) - 12) / 12)
            matrix = cv2.getRotationMatrix2D((width / 2, height / 2), 0, 1.0)
            matrix[0, 2] += shift
            moved = cv2.warpAffine(base, matrix, (width, height), borderMode=cv2.BORDER_REPLICATE)
            writer.write(cv2.resize(moved, (640, 360), interpolation=cv2.INTER_AREA))
        writer.release()
        specs.append(ClipSpec(path=out_path, sport=sport, note=note))
    return specs


def _load_manifest(manifest_path: Path) -> list[ClipSpec]:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    clips = data.get("clips")
    if not isinstance(clips, list) or not clips:
        raise ValueError("manifest 需要非空的 clips 数组")
    base = manifest_path.parent
    specs: list[ClipSpec] = []
    for entry in clips:
        sport = entry.get("sport")
        raw_path = entry.get("path")
        if sport not in SPORTS:
            raise ValueError(f"clip sport 必须是 {SPORTS}，收到 {sport!r}")
        if not raw_path:
            raise ValueError("clip 缺少 path 字段")
        clip_path = (base / raw_path).resolve()
        if not clip_path.exists():
            raise FileNotFoundError(f"找不到片段 {clip_path}")
        specs.append(ClipSpec(path=clip_path, sport=sport, note=str(entry.get("note", ""))))
    return specs


def _run_clip(spec: ClipSpec, work_dir: Path) -> ClipResult:
    evidence_path = work_dir / f"{spec.path.stem}_evidence.jpg"
    started = time.perf_counter()
    try:
        report = analyze_video(
            video_path=spec.path,
            sport=spec.sport,
            report_id=f"eval-{spec.path.stem}",
            file_name=spec.path.name,
            output_path=evidence_path,
            media_url="http://eval/local",
            progress=lambda *_: None,
        )
    except AnalysisError as error:
        return ClipResult(
            path=str(spec.path),
            expected_sport=spec.sport,
            ok=False,
            error_code=error.code,
            seconds=round(time.perf_counter() - started, 2),
            note=spec.note,
        )
    metadata = report.get("metadata", {})
    return ClipResult(
        path=str(spec.path),
        expected_sport=spec.sport,
        ok=True,
        predicted_sport=report.get("sport"),
        detected_sport=metadata.get("detectedSport"),
        confidence=round(float(report.get("confidence", 0.0)), 1),
        detection_ratio=round(float(metadata.get("detectionRatio", 0.0)), 3),
        capture_quality=metadata.get("captureQuality", {}).get("grade")
        if isinstance(metadata.get("captureQuality"), dict)
        else None,
        seconds=round(time.perf_counter() - started, 2),
        note=spec.note,
    )


def evaluate(specs: list[ClipSpec]) -> EvalSummary:
    summary = EvalSummary()
    with tempfile.TemporaryDirectory() as temporary:
        work_dir = Path(temporary)
        for spec in specs:
            summary.results.append(_run_clip(spec, work_dir))
    return summary


def _print_report(summary: EvalSummary) -> None:
    print("=" * 56)
    print("NeverStop 离线评测 (ALG-001)")
    print("=" * 56)
    print(f"片段总数 : {summary.total}")
    print(f"成功分析 : {len(summary.classified)}")
    print(f"分类准确 : {summary.correct}/{len(summary.classified)}  (accuracy={summary.accuracy:.1%})")
    print("-" * 56)
    print("混淆矩阵 (行=真实, 列=预测/拒绝):")
    confusion = summary.confusion()
    header = f"{'':<12}" + "".join(f"{col:<11}" for col in (*SPORTS, "rejected"))
    print(header)
    for expected in SPORTS:
        row = f"{expected:<12}" + "".join(f"{confusion[expected][col]:<11}" for col in (*SPORTS, "rejected"))
        print(row)
    print("-" * 56)
    print("逐片段:")
    for item in summary.results:
        if item.ok:
            mark = "OK " if item.predicted_sport == item.expected_sport else "XX "
            detail = (
                f"pred={item.predicted_sport} conf={item.confidence} "
                f"det={item.detection_ratio} quality={item.capture_quality}"
            )
        else:
            mark = "-- "
            detail = f"rejected={item.error_code}"
        print(f"  {mark}[{item.expected_sport:<8}] {Path(item.path).name:<28} {detail}  {item.seconds}s")
    print("=" * 56)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NeverStop 离线动作评测")
    parser.add_argument("--manifest", type=Path, help="带标签片段的 manifest.json")
    parser.add_argument("--json", type=Path, help="将结果写入 JSON 文件")
    parser.add_argument(
        "--min-accuracy",
        type=float,
        default=None,
        help="设定准确率下限；低于该值时以非零码退出（用于 CI 门禁）",
    )
    args = parser.parse_args(argv)

    if args.manifest:
        specs = _load_manifest(args.manifest)
        summary = evaluate(specs)
    else:
        print("未提供 --manifest，使用内置合成样本（仅验证管线连通）。\n")
        with tempfile.TemporaryDirectory() as temporary:
            specs = _build_synthetic_clips(Path(temporary))
            summary = evaluate(specs)

    _print_report(summary)

    if args.json:
        args.json.write_text(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已写入 {args.json}")

    if args.min_accuracy is not None and summary.classified:
        if summary.accuracy < args.min_accuracy:
            print(f"准确率 {summary.accuracy:.1%} 低于门槛 {args.min_accuracy:.1%}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
