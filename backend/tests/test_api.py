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
        self._source_dir = self._tmp_path / "sources"
        self._source_dir.mkdir(parents=True, exist_ok=True)
        self._upload_dir = self._tmp_path / "uploads"
        self._upload_dir.mkdir(parents=True, exist_ok=True)
        self._feedback_file = self._tmp_path / "feedback.jsonl"

        self._orig_report_dir = main.REPORT_DIR
        self._orig_source_dir = main.SOURCE_DIR
        self._orig_upload_dir = main.UPLOAD_DIR
        self._orig_feedback_file = main.FEEDBACK_FILE
        self._orig_reports = main.reports
        self._orig_jobs = main.jobs

        main.REPORT_DIR = self._report_dir
        main.SOURCE_DIR = self._source_dir
        main.UPLOAD_DIR = self._upload_dir
        main.FEEDBACK_FILE = self._feedback_file
        main.reports = {}
        main.jobs = {}

        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        main.REPORT_DIR = self._orig_report_dir
        main.SOURCE_DIR = self._orig_source_dir
        main.UPLOAD_DIR = self._orig_upload_dir
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

    def test_cors_preflight_allows_patch_and_delete(self) -> None:
        # 前端会对报告改名/改泳姿(PATCH)与删除(DELETE)发跨域预检，
        # 若 allow_methods 缺这些方法，浏览器会拦截并报“无法连接分析服务”。
        for method in ("PATCH", "DELETE"):
            response = self.client.options(
                "/api/reports/report-1",
                headers={
                    "Origin": "http://localhost:5173",
                    "Access-Control-Request-Method": method,
                },
            )
            self.assertEqual(response.status_code, 200, msg=method)
            allowed = response.headers.get("access-control-allow-methods", "")
            self.assertIn(method, allowed, msg=f"{method} not in {allowed!r}")

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

    # ---- reanalyze ----------------------------------------------------

    def test_reanalyze_uses_archived_video_and_passes_stroke(self) -> None:
        from unittest.mock import patch

        report = _sample_report("re-me", sport="swimming")
        self._seed(report)
        # 归档一份源视频，命名需匹配 sourceHash
        (self._source_dir / f"{report['sourceHash']}.mp4").write_bytes(b"fake-video-bytes")

        captured: dict = {}

        def fake_process(job_id, report_id, upload_path, file_name, sport, source_hash, swim_stroke_hint):  # noqa: ANN001
            captured.update(
                report_id=report_id, sport=sport, source_hash=source_hash,
                swim_stroke_hint=swim_stroke_hint, staged_exists=Path(upload_path).exists(),
            )

        with patch.object(main, "_process_job", side_effect=fake_process):
            response = self.client.post("/api/reports/re-me/reanalyze", json={"swimStroke": "freestyle"})

        self.assertEqual(response.status_code, 202)
        body = response.json()
        self.assertEqual(body["status"], "queued")
        self.assertEqual(captured["sport"], "swimming")
        self.assertEqual(captured["source_hash"], report["sourceHash"])
        self.assertEqual(captured["swim_stroke_hint"], "freestyle")
        self.assertTrue(captured["staged_exists"])
        # 重新分析用新的 report_id，不覆盖原报告
        self.assertNotEqual(captured["report_id"], "re-me")

    def test_reanalyze_falls_back_to_stored_stroke_when_unspecified(self) -> None:
        from unittest.mock import patch

        report = _sample_report("re-fallback", sport="swimming")
        report["swimStroke"]["stroke"] = "backstroke"
        self._seed(report)
        (self._source_dir / f"{report['sourceHash']}.mp4").write_bytes(b"vid")

        captured: dict = {}

        def fake_process(*args):  # noqa: ANN002
            captured["swim_stroke_hint"] = args[6]

        with patch.object(main, "_process_job", side_effect=fake_process):
            response = self.client.post("/api/reports/re-fallback/reanalyze", json={})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(captured["swim_stroke_hint"], "backstroke")

    def test_reanalyze_missing_source_returns_409(self) -> None:
        self._seed(_sample_report("re-nosource", sport="swimming"))
        response = self.client.post("/api/reports/re-nosource/reanalyze", json={})
        self.assertEqual(response.status_code, 409)

    def test_reanalyze_missing_report_returns_404(self) -> None:
        response = self.client.post("/api/reports/ghost/reanalyze", json={})
        self.assertEqual(response.status_code, 404)

    def test_archive_prunes_unreferenced_but_keeps_referenced(self) -> None:
        # 归档新视频时，删除无报告引用的旧源视频，但保留仍被报告引用的。
        referenced = _sample_report("keep-me", sport="swimming")
        referenced["sourceHash"] = "refhash"
        self._seed(referenced)
        (self._source_dir / "refhash.mp4").write_bytes(b"referenced")   # 被 keep-me 引用
        (self._source_dir / "orphanhash.mov").write_bytes(b"orphan")    # 无报告引用
        staged = self._upload_dir / "job-new.mp4"
        staged.write_bytes(b"newest")

        main._archive_source_video(staged, "newhash")

        remaining = sorted(p.name for p in self._source_dir.glob("*"))
        # 新归档 + 被引用的都保留，孤儿被清理
        self.assertEqual(remaining, ["newhash.mp4", "refhash.mp4"])
        self.assertFalse(staged.exists())

    def test_reanalyze_same_video_keeps_its_source(self) -> None:
        # 重新分析用的是同一视频(同 hash)，归档时不应把自己删掉。
        target = self._source_dir / "samehash.mp4"
        target.write_bytes(b"archived")
        staged = self._upload_dir / "job-re.mp4"
        staged.write_bytes(b"copy-of-archived")

        main._archive_source_video(staged, "samehash")

        remaining = sorted(p.name for p in self._source_dir.glob("*"))
        self.assertEqual(remaining, ["samehash.mp4"])

    def test_delete_report_reclaims_orphan_source(self) -> None:
        # 删掉唯一引用某源视频的报告后，该源视频应被回收。
        report = _sample_report("del-me", sport="swimming")
        report["sourceHash"] = "delhash"
        self._seed(report)
        src = self._source_dir / "delhash.mp4"
        src.write_bytes(b"video")

        self.client.delete("/api/reports/del-me")

        self.assertFalse(src.exists())

    def test_delete_report_keeps_source_still_referenced(self) -> None:
        # 两份报告共享同一源视频，删其一后源视频仍应保留（另一份还要用）。
        a = _sample_report("share-a", sport="swimming")
        b = _sample_report("share-b", sport="swimming")
        a["sourceHash"] = b["sourceHash"] = "sharedhash"
        self._seed(a)
        self._seed(b)
        src = self._source_dir / "sharedhash.mp4"
        src.write_bytes(b"video")

        self.client.delete("/api/reports/share-a")

        self.assertTrue(src.exists())  # share-b 仍引用

    # ---- measurement trend comparison ---------------------------------

    def test_compare_measurements_directions(self) -> None:
        prev = {"keyMeasurements": {
            "headDeviation": {"value": 0.40, "betterWhen": "lower", "label": "头位偏离", "unit": ""},
            "kneeFlexion": {"value": 50.0, "betterWhen": "lower", "label": "打腿膝屈曲", "unit": "°"},
            "torsoLean": {"value": 4.0, "betterWhen": "range", "target": 10.0, "label": "躯干前倾", "unit": "°"},
        }}
        curr = {"keyMeasurements": {
            "headDeviation": {"value": 0.30, "betterWhen": "lower", "label": "头位偏离", "unit": ""},   # 下降=改善
            "kneeFlexion": {"value": 60.0, "betterWhen": "lower", "label": "打腿膝屈曲", "unit": "°"},   # 上升=退步
            "torsoLean": {"value": 9.0, "betterWhen": "range", "target": 10.0, "label": "躯干前倾", "unit": "°"},  # 更接近目标=改善
        }}
        trends = {t["key"]: t for t in main._compare_measurements(prev, curr)}
        self.assertEqual(trends["headDeviation"]["direction"], "improved")
        self.assertEqual(trends["kneeFlexion"]["direction"], "regressed")
        self.assertEqual(trends["torsoLean"]["direction"], "improved")
        self.assertAlmostEqual(trends["headDeviation"]["delta"], -0.10, places=4)

    def test_compare_measurements_stable_when_tiny_change(self) -> None:
        prev = {"keyMeasurements": {"kneeFlexion": {"value": 50.0, "betterWhen": "lower", "label": "x", "unit": "°"}}}
        curr = {"keyMeasurements": {"kneeFlexion": {"value": 50.5, "betterWhen": "lower", "label": "x", "unit": "°"}}}
        trends = main._compare_measurements(prev, curr)
        self.assertEqual(trends[0]["direction"], "stable")  # 相对变化<3%

    def test_compare_measurements_handles_missing(self) -> None:
        # 上一份没有该测量值时应跳过，不报错。
        prev = {"keyMeasurements": {}}
        curr = {"keyMeasurements": {"kneeFlexion": {"value": 50.0, "betterWhen": "lower", "label": "x", "unit": "°"}}}
        self.assertEqual(main._compare_measurements(prev, curr), [])

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

    def test_feedback_stats_empty(self) -> None:
        response = self.client.get("/api/feedback/stats")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 0)
        self.assertEqual(body["byInsight"], [])
        self.assertEqual(body["overallInaccurateRate"], 0.0)

    def test_feedback_stats_aggregates_and_ranks(self) -> None:
        self._seed(_sample_report("fb-stats"))
        # insight-a 被多次标记：1 准确 + 3 不满意 -> inaccurateRate=0.75
        for value in ("accurate", "inaccurate", "unclear", "not_visible"):
            resp = self.client.post("/api/reports/fb-stats/feedback", json={"insightId": "insight-a", "value": value})
            self.assertEqual(resp.status_code, 201)

        body = self.client.get("/api/feedback/stats").json()
        self.assertEqual(body["total"], 4)
        self.assertEqual(body["byValue"]["inaccurate"], 1)
        self.assertEqual(body["byValue"]["accurate"], 1)
        row = next(r for r in body["byInsight"] if r["insightId"] == "insight-a")
        self.assertEqual(row["total"], 4)
        self.assertEqual(row["accurate"], 1)
        self.assertEqual(row["negative"], 3)
        self.assertEqual(row["inaccurateRate"], 0.75)
        self.assertEqual(body["overallInaccurateRate"], 0.75)

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
