from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from backend.model_review import (
    _json_from_text,
    _review_from_response,
    _text_from_opencode_jsonl,
    _validate_review,
    review_provider,
    review_report,
)


class ModelReviewTest(unittest.TestCase):
    def setUp(self) -> None:
        self.report = {"insights": [{"id": "head"}]}

    def test_missing_endpoint_uses_engineering_fallback(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            result = review_report(self.report)
        self.assertEqual(result["status"], "engineering_fallback")

    def test_review_cannot_reference_unknown_evidence(self) -> None:
        with self.assertRaises(ValueError):
            _validate_review({"verdict": "insufficient_evidence", "evidenceIds": ["missing"]}, self.report)

    def test_supported_review_requires_actionable_fields(self) -> None:
        result = _validate_review(
            {
                "verdict": "supported",
                "evidenceIds": ["head"],
                "issueType": "breathing_head_lift",
                "problem": "换气时抬头",
                "impact": "髋腿下沉",
                "action": "随肩膀侧转",
                "successCue": "一侧泳镜留在水中",
                "confidence": 0.82,
            },
            self.report,
        )
        self.assertEqual(result["verdict"], "supported")

    def test_model_assistant_message_can_contain_json(self) -> None:
        result = _review_from_response({"assistant_message": "```json\n{\"verdict\":\"insufficient_evidence\",\"evidenceIds\":[]}\n```"})
        self.assertEqual(result["verdict"], "insufficient_evidence")

    def test_json_from_text_extracts_object_from_mixed_text(self) -> None:
        noisy = '好的，这是复核结果：\n{"verdict": "insufficient_evidence", "evidenceIds": []}\n以上。'
        parsed = _json_from_text(noisy)
        self.assertEqual(parsed["verdict"], "insufficient_evidence")

    def test_json_from_text_handles_braces_inside_strings(self) -> None:
        parsed = _json_from_text('{"problem": "使用 {大括号} 描述", "verdict": "supported"}')
        self.assertEqual(parsed["problem"], "使用 {大括号} 描述")

    def test_text_from_opencode_jsonl_concatenates_text_parts(self) -> None:
        stream = (
            '{"type":"step_start","part":{"type":"step-start"}}\n'
            '{"type":"text","part":{"type":"text","text":"{\\"verdict\\":"}}\n'
            '{"type":"text","part":{"type":"text","text":"\\"insufficient_evidence\\",\\"evidenceIds\\":[]}"}}\n'
            '{"type":"step_finish","part":{"type":"step-finish"}}\n'
        )
        self.assertEqual(_text_from_opencode_jsonl(stream), '{"verdict":"insufficient_evidence","evidenceIds":[]}')

    def test_opencode_provider_reported_when_enabled(self) -> None:
        with patch.dict(os.environ, {"NEVERSTOP_REVIEW_OPENCODE": "1"}, clear=True), patch(
            "backend.model_review.shutil.which", return_value="/usr/local/bin/opencode"
        ):
            provider, configured = review_provider()
        self.assertEqual(provider, "opencode-cli")
        self.assertTrue(configured)

    def test_opencode_review_parses_cli_output(self) -> None:
        report = {
            "insights": [
                {"id": "i1", "title": "肘部下沉", "summary": "抓水肘低", "severity": "warning", "timestamp": 2.4},
            ]
        }
        cli_stdout = (
            '{"type":"text","part":{"type":"text","text":"'
            '{\\"verdict\\":\\"supported\\",\\"evidenceIds\\":[\\"i1\\"],\\"issueType\\":\\"catch\\",'
            '\\"problem\\":\\"抓水肘部偏低\\",\\"impact\\":\\"推进效率下降\\",\\"action\\":\\"高肘抓水练习\\",'
            '\\"successCue\\":\\"肘高于腕\\",\\"confidence\\":0.7}"}}\n'
        )
        completed = type("P", (), {"returncode": 0, "stdout": cli_stdout, "stderr": ""})()
        with patch.dict(os.environ, {"NEVERSTOP_REVIEW_OPENCODE": "1"}, clear=True), patch(
            "backend.model_review.shutil.which", return_value="/usr/local/bin/opencode"
        ), patch("backend.model_review.subprocess.run", return_value=completed):
            result = review_report(report)
        self.assertEqual(result["status"], "reviewed")
        self.assertTrue(result["evidenceValidated"])
        self.assertEqual(result["result"]["evidenceIds"], ["i1"])

    def test_opencode_empty_output_falls_back(self) -> None:
        completed = type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        with patch.dict(os.environ, {"NEVERSTOP_REVIEW_OPENCODE": "1"}, clear=True), patch(
            "backend.model_review.shutil.which", return_value="/usr/local/bin/opencode"
        ), patch("backend.model_review.subprocess.run", return_value=completed):
            result = review_report({"insights": [{"id": "i1", "title": "t", "summary": "s", "timestamp": 1.0}]})
        self.assertEqual(result["status"], "engineering_fallback")


if __name__ == "__main__":
    unittest.main()
