from __future__ import annotations

import os
import logging
import threading
import uuid
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.analyzer import AnalysisError, analyze_video


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "backend" / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
REPORT_DIR = DATA_DIR / "reports"
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


def _update_job(job_id: str, **changes) -> None:
    with state_lock:
        if job_id in jobs:
            jobs[job_id].update(changes)


def _process_job(job_id: str, report_id: str, upload_path: Path, file_name: str, sport: str) -> None:
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
        )
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
    return {"status": "ok", "analyzer": "mediapipe-pose", "storage": "local"}


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
    try:
        with upload_path.open("wb") as destination:
            while chunk := await video.read(1024 * 1024):
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="视频不能超过 300 MB。")
                destination.write(chunk)
    except Exception:
        upload_path.unlink(missing_ok=True)
        raise
    finally:
        await video.close()

    if written == 0:
        upload_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="视频文件为空。")

    job = {
        "id": job_id,
        "sport": sport,
        "status": "queued",
        "progress": 5,
        "stage": "等待分析",
        "reportId": None,
        "errorCode": None,
        "errorMessage": None,
    }
    with state_lock:
        jobs[job_id] = job
    background_tasks.add_task(_process_job, job_id, report_id, upload_path, file_name, sport)
    return job


@app.get("/api/analysis/jobs/{job_id}")
def get_analysis_job(job_id: str) -> dict:
    with state_lock:
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="分析任务不存在或服务已经重启。")
        return dict(job)


@app.get("/api/reports/{report_id}")
def get_report(report_id: str) -> dict:
    with state_lock:
        report = reports.get(report_id)
        if not report:
            raise HTTPException(status_code=404, detail="报告不存在或服务已经重启。")
        return dict(report)
