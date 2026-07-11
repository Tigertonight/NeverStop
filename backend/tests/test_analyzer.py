from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import cv2

from backend.analyzer import AnalysisError, analyze_video


ROOT = Path(__file__).resolve().parents[2]


class AnalyzerTest(unittest.TestCase):
    def _create_static_video(self, source_name: str, video_path: Path) -> None:
        source = cv2.imread(str(ROOT / "src" / "assets" / source_name))
        self.assertIsNotNone(source)
        frame = cv2.resize(source, (640, 360), interpolation=cv2.INTER_AREA)
        writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (640, 360))
        self.assertTrue(writer.isOpened())
        for _ in range(120):
            writer.write(frame)
        writer.release()

    def test_running_video_produces_real_report_and_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            video_path = directory / "runner.mp4"
            evidence_path = directory / "evidence.jpg"
            self._create_static_video("runner.jpg", video_path)

            updates: list[tuple[int, str]] = []
            report = analyze_video(
                video_path=video_path,
                sport="running",
                report_id="test-report",
                file_name="runner.mp4",
                output_path=evidence_path,
                media_url="http://test/media/evidence.jpg",
                progress=lambda value, stage: updates.append((value, stage)),
            )

            self.assertEqual(report["source"], "video")
            self.assertEqual(report["sport"], "running")
            self.assertGreater(report["confidence"], 40)
            self.assertEqual(len(report["metrics"]), 4)
            self.assertTrue(evidence_path.exists())
            self.assertTrue((directory / "evidence-b.jpg").exists())
            self.assertTrue((directory / "evidence-c.jpg").exists())
            self.assertTrue((directory / "evidence-d.jpg").exists())
            self.assertGreaterEqual(report["metadata"]["sampleRateFps"], 9.5)
            self.assertGreaterEqual(len(report["insights"]), 4)
            self.assertGreaterEqual(len({insight["timestamp"] for insight in report["insights"]}), 4)
            self.assertGreaterEqual(len({insight["image"] for insight in report["insights"]}), 4)
            self.assertNotIn("°", " ".join(insight["summary"] for insight in report["insights"]))
            self.assertTrue(updates)

    def test_obvious_swimming_video_is_rejected_as_running(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            video_path = directory / "swimmer.mp4"
            self._create_static_video("swimmer.jpg", video_path)
            with self.assertRaises(AnalysisError) as context:
                analyze_video(
                    video_path=video_path,
                    sport="running",
                    report_id="mismatch",
                    file_name="swimmer.mp4",
                    output_path=directory / "evidence.jpg",
                    media_url="http://test/media/evidence.jpg",
                    progress=lambda *_: None,
                )
            self.assertEqual(context.exception.code, "SPORT_MISMATCH")


if __name__ == "__main__":
    unittest.main()
