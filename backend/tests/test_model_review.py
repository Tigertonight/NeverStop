from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from backend.model_review import _review_from_response, _validate_review, review_report


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


if __name__ == "__main__":
    unittest.main()
