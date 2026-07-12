from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend import main


def _sample_report(report_id: str = "report-1", sport: str = "swimming") -> dict:
    report: dict = {
        "id": report_id,
        "source": "video",
        "sport": sport,
        "title": "自由泳 · 视频动作分析",
        "date": "今天",
        "displayName": "10月1日训练记录",
        "createdAt": "2024-10-01T08:30:00+08:00",
        "trainingDate": "2024-10-01",
        "sourceHash": f"hash-{report_id}",
        "duration": "00:42",
        "score": 78,
        "headline": "入水点略微越过中线",
        "summary": "整体节奏稳定，重点关注入水路径。",
        "image": "http://127.0.0.1:8000/media/report-1/evidence.jpg",
        "fileName": "swim.mp4",
        "metadata": {"durationSeconds": 42, "frameCount": 420},
        "metrics": [],
        "insights": [
            {
                "id": "insight-a",
                "title": "入水点越过中线",
                "summary": "手掌越过身体中线入水。",
                "action": "让手掌对准同侧肩线入水。",
                "severity": "focus",
                "timestamp": "00:12",
                "marker": "A",
            }
        ],
        "prescription": {
            "priorityIssueId": "insight-a",
            "reason": "越线入水会降低推进效率。",
            "drill": "单臂划水，注意入水路径。",
            "volume": "4 组 × 25 米",
            "rest": "组间休息 30 秒",
            "focusCue": "入水对准肩线",
            "successCue": "划水更顺畅",
        },
    }
    if sport == "swimming":
        report["swimStroke"] = {
            "stroke": "freestyle",
            "strokeName": "自由泳",
            "confidence": 88,
            "candidates": [],
        }
    return report


class ReportApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._tmp_path = Path(self._tmp.name)
        self._report_dir = self._tmp_path / "reports"
        self._report_dir.mkdir(parents=True, exist_ok=True)
        self._feedback_file = self._tmp_path / "feedback.jsonl"

        self._orig_report_dir = main.REPORT_DIR
        self._orig_feedback_file = main.FEEDBACK_FILE
        self._orig_reports = main.reports
        self._orig_jobs = main.jobs

        main.REPORT_DIR = self._report_dir
        main.FEEDBACK_FILE = self._feedback_file
        main.reports = {}
        main.jobs = {}

        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        main.REPORT_DIR = self._orig_report_dir
        main.FEEDBACK_FILE = self._orig_feedback_file
        main.reports = self._orig_reports
        main.jobs = self._orig_jobs
        self._tmp.cleanup()

    def _seed(self, report: dict) -> dict:
        stored = copy.deepcopy(report)
        main.reports[stored["id"]] = stored
        report_path = self._report_dir / stored["id"]
        report_path.mkdir(parents=True, exist_ok=True)
        (report_path / "report.json").write_text(
            json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return stored

    # ---- health -------------------------------------------------------

    def test_health_reports_ok(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertIn("reviewProvider", body)

    # ---- list / get ---------------------------------------------------

    def test_list_reports_returns_seeded_reports_sorted(self) -> None:
        older = _sample_report("older")
        older["createdAt"] = "2024-09-01T08:00:00+08:00"
        newer = _sample_report("newer")
        newer["createdAt"] = "2024-10-05T08:00:00+08:00"
        self._seed(older)
        self._seed(newer)

        response = self.client.get("/api/reports")
        self.assertEqual(response.status_code, 200)
        ids = [item["id"] for item in response.json()]
        self.assertEqual(ids, ["newer", "older"])

    def test_list_reports_deduplicates_by_source_hash(self) -> None:
        first = _sample_report("dup-1")
        second = _sample_report("dup-2")
        second["sourceHash"] = first["sourceHash"]
        self._seed(first)
        self._seed(second)

        response = self.client.get("/api/reports")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)

    def test_get_report_returns_report(self) -> None:
        self._seed(_sample_report("get-me"))
        response = self.client.get("/api/reports/get-me")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], "get-me")

    def test_get_missing_report_returns_404(self) -> None:
        response = self.client.get("/api/reports/nope")
        self.assertEqual(response.status_code, 404)

    # ---- update -------------------------------------------------------

    def test_update_report_persists_name_and_date(self) -> None:
        self._seed(_sample_report("edit-me"))
        response = self.client.patch(
            "/api/reports/edit-me",
            json={"displayName": "周一晨泳", "trainingDate": "2024-10-02"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["displayName"], "周一晨泳")
        self.assertEqual(body["trainingDate"], "2024-10-02")

        on_disk = json.loads((self._report_dir / "edit-me" / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(on_disk["displayName"], "周一晨泳")
        self.assertEqual(on_disk["trainingDate"], "2024-10-02")

    def test_update_report_rejects_blank_name(self) -> None:
        self._seed(_sample_report("edit-blank"))
        response = self.client.patch(
            "/api/reports/edit-blank",
            json={"displayName": "   ", "trainingDate": "2024-10-02"},
        )
        self.assertEqual(response.status_code, 400)

    def test_update_report_rejects_bad_date(self) -> None:
        self._seed(_sample_report("edit-date"))
        response = self.client.patch(
            "/api/reports/edit-date",
            json={"displayName": "有效名称", "trainingDate": "2024/10/02"},
        )
        self.assertEqual(response.status_code, 400)

    def test_update_missing_report_returns_404(self) -> None:
        response = self.client.patch(
            "/api/reports/ghost",
            json={"displayName": "名称", "trainingDate": "2024-10-02"},
        )
        self.assertEqual(response.status_code, 404)

    # ---- delete -------------------------------------------------------

    def test_delete_report_removes_state_and_files(self) -> None:
        self._seed(_sample_report("delete-me"))
        response = self.client.delete("/api/reports/delete-me")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"deleted": True, "reportId": "delete-me"})
        self.assertNotIn("delete-me", main.reports)
        self.assertFalse((self._report_dir / "delete-me").exists())

    def test_delete_missing_report_returns_404(self) -> None:
        response = self.client.delete("/api/reports/ghost")
        self.assertEqual(response.status_code, 404)

    # ---- stroke correction -------------------------------------------

    def test_correct_stroke_updates_report(self) -> None:
        self._seed(_sample_report("stroke-me", sport="swimming"))
        response = self.client.patch(
            "/api/reports/stroke-me/stroke",
            json={"stroke": "breaststroke"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["swimStroke"]["stroke"], "breaststroke")
        self.assertEqual(body["swimStroke"]["strokeName"], "蛙泳")
        self.assertTrue(body["swimStroke"]["correctedByUser"])
        self.assertTrue(body["adviceNeedsReanalysis"])

    def test_correct_stroke_rejects_running_report(self) -> None:
        self._seed(_sample_report("run-me", sport="running"))
        response = self.client.patch(
            "/api/reports/run-me/stroke",
            json={"stroke": "freestyle"},
        )
        self.assertEqual(response.status_code, 404)

    def test_correct_stroke_rejects_invalid_stroke(self) -> None:
        self._seed(_sample_report("stroke-bad", sport="swimming"))
        response = self.client.patch(
            "/api/reports/stroke-bad/stroke",
            json={"stroke": "sidestroke"},
        )
        self.assertEqual(response.status_code, 422)

    # ---- feedback -----------------------------------------------------

    def test_feedback_is_appended_to_file(self) -> None:
        self._seed(_sample_report("fb-me"))
        response = self.client.post(
            "/api/reports/fb-me/feedback",
            json={"insightId": "insight-a", "value": "accurate"},
        )
        self.assertEqual(response.status_code, 201)
        record = response.json()
        self.assertEqual(record["reportId"], "fb-me")
        self.assertEqual(record["insightId"], "insight-a")
        self.assertEqual(record["value"], "accurate")

        lines = self._feedback_file.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["value"], "accurate")

    def test_feedback_rejects_unknown_insight(self) -> None:
        self._seed(_sample_report("fb-bad"))
        response = self.client.post(
            "/api/reports/fb-bad/feedback",
            json={"insightId": "does-not-exist", "value": "accurate"},
        )
        self.assertEqual(response.status_code, 400)

    def test_feedback_rejects_unknown_report(self) -> None:
        response = self.client.post(
            "/api/reports/ghost/feedback",
            json={"insightId": "insight-a", "value": "accurate"},
        )
        self.assertEqual(response.status_code, 404)

    # ---- job lifecycle ------------------------------------------------

    def test_create_job_rejects_unsupported_extension(self) -> None:
        response = self.client.post(
            "/api/analysis/jobs",
            data={"sport": "running"},
            files={"video": ("clip.avi", b"not-a-real-video", "video/x-msvideo")},
        )
        self.assertEqual(response.status_code, 415)

    def test_get_missing_job_returns_404(self) -> None:
        response = self.client.get("/api/analysis/jobs/ghost")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
