from __future__ import annotations

import os
import hashlib
import json
import logging
import shutil
import threading
import uuid
from pathlib import Path
from typing import Literal
from datetime import datetime, timezone

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.analyzer import AnalysisError, analyze_video
from backend.model_review import review_provider, review_report


ROOT = Path(__file__).resolve().parent.parent


def _load_project_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_project_env(ROOT / ".env")

DATA_DIR = ROOT / "backend" / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
REPORT_DIR = DATA_DIR / "reports"
FEEDBACK_FILE = DATA_DIR / "feedback.jsonl"
MAX_UPLOAD_BYTES = 300 * 1024 * 1024
PUBLIC_API_URL = os.getenv("NEVERSTOP_PUBLIC_API_URL", "http://127.0.0.1:8000").rstrip("/")

for directory in (UPLOAD_DIR, REPORT_DIR):
    directory.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="NeverStop Analysis API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:4173",
        "http://localhost:4173",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
app.mount("/media", StaticFiles(directory=REPORT_DIR), name="media")

jobs: dict[str, dict] = {}
reports: dict[str, dict] = {}
state_lock = threading.Lock()
logger = logging.getLogger(__name__)

for report_file in REPORT_DIR.glob("*/report.json"):
    try:
        stored_report = json.loads(report_file.read_text(encoding="utf-8"))
        fallback_time = datetime.fromtimestamp(report_file.stat().st_mtime).astimezone()
        stored_report.setdefault("createdAt", fallback_time.isoformat())
        stored_report.setdefault("trainingDate", fallback_time.date().isoformat())
        generated_name = f"{fallback_time.month}月{fallback_time.day}日训练记录"
        file_stem = str(stored_report.get("fileName") or "").rsplit(".", 1)[0]
        if not stored_report.get("displayName") or stored_report.get("displayName") == file_stem:
            stored_report["displayName"] = generated_name
            report_file.write_text(json.dumps(stored_report, ensure_ascii=False, indent=2), encoding="utf-8")
        reports[str(stored_report["id"])] = stored_report
    except (OSError, ValueError, KeyError):
        logger.warning("Ignoring invalid stored report %s", report_file)


class StrokeCorrection(BaseModel):
    stroke: Literal["freestyle", "breaststroke", "backstroke", "butterfly"]


class ReportFeedback(BaseModel):
    insightId: str
    value: Literal["accurate", "inaccurate", "unclear", "not_visible", "not_suitable"]


class ReportUpdate(BaseModel):
    displayName: str
    trainingDate: str


def _update_job(job_id: str, **changes) -> None:
    with state_lock:
        if job_id in jobs:
            jobs[job_id].update(changes)


def _process_job(job_id: str, report_id: str, upload_path: Path, file_name: str, sport: str, source_hash: str, swim_stroke_hint: str | None) -> None:
    output_path = REPORT_DIR / report_id / "evidence.jpg"
    media_url = f"{PUBLIC_API_URL}/media/{report_id}/evidence.jpg"

    def progress(value: int, stage: str) -> None:
        status = "estimating_pose" if value < 82 else "building_report"
        _update_job(job_id, status=status, progress=value, stage=stage)

    try:
        _update_job(job_id, status="preprocessing", progress=8, stage="读取视频")
        report = analyze_video(
            video_path=upload_path,
            sport=sport,
            report_id=report_id,
            file_name=file_name,
            output_path=output_path,
            media_url=media_url,
            progress=progress,
            swim_stroke_hint=swim_stroke_hint,
        )
        created_at = datetime.now().astimezone()
        report["createdAt"] = created_at.isoformat()
        report["trainingDate"] = created_at.date().isoformat()
        report["displayName"] = f"{created_at.month}月{created_at.day}日训练记录"
        report["sourceHash"] = source_hash
        with state_lock:
            previous = next((item for item in reversed(list(reports.values())) if item.get("sport") == report.get("sport") and item.get("swimStroke", {}).get("stroke") == report.get("swimStroke", {}).get("stroke") and len(item.get("cycles", [])) >= 2), None)
        current_stroke = report.get("swimStroke", {}).get("stroke")
        if previous and current_stroke not in {None, "unknown"} and len(report.get("cycles", [])) >= 2:
            previous_issues = {item["id"] for item in previous.get("insights", []) if item.get("severity") in {"focus", "observe"}}
            current_issues = {item["id"] for item in report.get("insights", []) if item.get("severity") in {"focus", "observe"}}
            report["comparison"] = {
                "status": "comparable",
                "previousReportId": previous["id"],
                "improved": sorted(previous_issues - current_issues),
                "remaining": sorted(previous_issues & current_issues),
                "newIssues": sorted(current_issues - previous_issues),
                "basis": "同一泳姿、均包含至少两个可见动作周期",
            }
        else:
            report["comparison"] = {"status": "not_comparable", "reason": "暂时没有同泳姿且动作周期完整的历史报告"}
        report["modelReview"] = review_report(report)
        review_result = report["modelReview"].get("result", {})
        if report["modelReview"].get("evidenceValidated") and review_result.get("verdict") == "supported":
            primary_id = review_result["evidenceIds"][0]
            primary = next((item for item in report["insights"] if item["id"] == primary_id), None)
            if primary:
                primary.update({
                    "title": review_result["problem"],
                    "impact": review_result["impact"],
                    "action": review_result["action"],
                    "successCue": review_result["successCue"],
                    "severity": "focus",
                })
                report["insights"] = [primary, *[item for item in report["insights"] if item["id"] != primary_id]]
                report["headline"] = review_result["problem"]
                report["summary"] = review_result["impact"]
                report["prescription"].update({
                    "priorityIssueId": primary_id,
                    "reason": review_result["impact"],
                    "drill": review_result["action"],
                    "focusCue": review_result["problem"],
                    "successCue": review_result["successCue"],
                })
        report_file = REPORT_DIR / report_id / "report.json"
        report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        with state_lock:
            reports[report_id] = report
        _update_job(
            job_id,
            status="completed",
            progress=100,
            stage="分析完成",
            reportId=report_id,
        )
    except AnalysisError as exc:
        _update_job(
            job_id,
            status="failed",
            progress=100,
            stage="分析失败",
            errorCode=exc.code,
            errorMessage=exc.message,
        )
    except Exception:
        logger.exception("Analysis job %s failed", job_id)
        _update_job(
            job_id,
            status="failed",
            progress=100,
            stage="分析失败",
            errorCode="ANALYSIS_INTERNAL_ERROR",
            errorMessage="分析服务出现异常，请重新尝试。",
        )
    finally:
        upload_path.unlink(missing_ok=True)


@app.get("/api/health")
def health() -> dict:
    provider, configured = review_provider()
    return {
        "status": "ok",
        "analyzer": "mediapipe-pose",
        "storage": "local",
        "reviewProvider": provider,
        "reviewConfigured": configured,
    }


@app.post("/api/analysis/jobs", status_code=202)
async def create_analysis_job(
    background_tasks: BackgroundTasks,
    sport: Literal["running", "swimming"] = Form(...),
    video: UploadFile = File(...),
) -> dict:
    file_name = video.filename or "training-video"
    suffix = Path(file_name).suffix.lower()
    if suffix not in {".mp4", ".mov"}:
        raise HTTPException(status_code=415, detail="只支持 MP4 或 MOV 视频。")

    job_id = uuid.uuid4().hex
    report_id = uuid.uuid4().hex
    upload_path = UPLOAD_DIR / f"{job_id}{suffix}"
    written = 0
    digest = hashlib.sha256()
    try:
        with upload_path.open("wb") as destination:
            while chunk := await video.read(1024 * 1024):
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="视频不能超过 300 MB。")
                destination.write(chunk)
                digest.update(chunk)
    except Exception:
        upload_path.unlink(missing_ok=True)
        raise
    finally:
        await video.close()

    if written == 0:
        upload_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="视频文件为空。")

    source_hash = digest.hexdigest()
    with state_lock:
        same_video = next((item for item in reversed(list(reports.values())) if item.get("sourceHash") == source_hash), None)
    swim_stroke_hint = same_video.get("swimStroke", {}).get("stroke") if same_video and sport == "swimming" else None
    job = {
        "id": job_id,
        "sport": sport,
        "status": "queued",
        "progress": 5,
        "stage": "等待分析",
        "reportId": None,
        "errorCode": None,
        "errorMessage": None,
        "sourceHash": source_hash,
    }
    with state_lock:
        jobs[job_id] = job
    background_tasks.add_task(_process_job, job_id, report_id, upload_path, file_name, sport, source_hash, swim_stroke_hint)
    return job


@app.get("/api/analysis/jobs/{job_id}")
def get_analysis_job(job_id: str) -> dict:
    with state_lock:
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="分析任务不存在或服务已经重启。")
        return dict(job)


@app.get("/api/reports")
def list_reports() -> list[dict]:
    with state_lock:
        ordered = sorted((dict(report) for report in reports.values()), key=lambda item: str(item.get("createdAt", "")), reverse=True)
    unique: list[dict] = []
    seen: set[str] = set()
    for report in ordered:
        metadata = report.get("metadata", {})
        legacy_key = f'{report.get("fileName", "")}:{metadata.get("durationSeconds", "")}:{metadata.get("frameCount", "")}'
        source_key = str(report.get("sourceHash") or legacy_key)
        if source_key in seen:
            continue
        seen.add(source_key)
        unique.append(report)
    return unique


@app.get("/api/reports/{report_id}")
def get_report(report_id: str) -> dict:
    with state_lock:
        report = reports.get(report_id)
        if not report:
            raise HTTPException(status_code=404, detail="报告不存在或服务已经重启。")
        return dict(report)


@app.patch("/api/reports/{report_id}")
def update_report(report_id: str, update: ReportUpdate) -> dict:
    display_name = update.displayName.strip()
    if not display_name or len(display_name) > 80:
        raise HTTPException(status_code=400, detail="报告名称需为 1 至 80 个字符。")
    try:
        datetime.strptime(update.trainingDate, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="训练日期格式不正确。") from exc
    with state_lock:
        report = reports.get(report_id)
        if not report:
            raise HTTPException(status_code=404, detail="报告不存在。")
        report["displayName"] = display_name
        report["trainingDate"] = update.trainingDate
        stored = dict(report)
    (REPORT_DIR / report_id / "report.json").write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
    return stored


@app.delete("/api/reports/{report_id}")
def delete_report(report_id: str) -> dict:
    with state_lock:
        if report_id not in reports:
            raise HTTPException(status_code=404, detail="报告不存在。")
        del reports[report_id]
    shutil.rmtree(REPORT_DIR / report_id, ignore_errors=True)
    return {"deleted": True, "reportId": report_id}


@app.patch("/api/reports/{report_id}/stroke")
def correct_report_stroke(report_id: str, correction: StrokeCorrection) -> dict:
    names = {"freestyle": "自由泳", "breaststroke": "蛙泳", "backstroke": "仰泳", "butterfly": "蝶泳"}
    with state_lock:
        report = reports.get(report_id)
        if not report or report.get("sport") != "swimming":
            raise HTTPException(status_code=404, detail="游泳报告不存在。")
        report["swimStroke"]["stroke"] = correction.stroke
        report["swimStroke"]["strokeName"] = names[correction.stroke]
        report["swimStroke"]["correctedByUser"] = True
        report["title"] = f"{names[correction.stroke]} · 视频动作分析"
        report["adviceNeedsReanalysis"] = True
        stored = dict(report)
    (REPORT_DIR / report_id / "report.json").write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
    return stored


@app.post("/api/reports/{report_id}/feedback", status_code=201)
def create_report_feedback(report_id: str, feedback: ReportFeedback) -> dict:
    with state_lock:
        report = reports.get(report_id)
        if not report:
            raise HTTPException(status_code=404, detail="报告不存在。")
        if feedback.insightId not in {item["id"] for item in report.get("insights", [])}:
            raise HTTPException(status_code=400, detail="反馈对应的建议不存在。")
        record = {
            "id": uuid.uuid4().hex,
            "reportId": report_id,
            "insightId": feedback.insightId,
            "value": feedback.value,
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "pipeline": report.get("pipeline", {}),
        }
        with FEEDBACK_FILE.open("a", encoding="utf-8") as destination:
            destination.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record
