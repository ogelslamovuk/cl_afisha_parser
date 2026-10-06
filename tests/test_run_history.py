import json
import tempfile
import unittest
from pathlib import Path

from src.run_history import append_from_report


class RunHistoryTests(unittest.TestCase):
    def test_persists_successful_result_without_report_payload(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            report = output / "current" / "report.json"
            report.parent.mkdir()
            report.write_text(json.dumps({"startedAt": "2026-10-06T14:58:01Z", "status": "success", "finishedAt": "2026-10-06T15:00:00Z", "showsCount": 1282}), encoding="utf-8")

            record = append_from_report("2026-10-06T14:58:00Z", 0, output)

            self.assertEqual(record["status"], "success")
            self.assertEqual(record["shows_count"], 1282)
            saved = json.loads((output / "run-history.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(saved["finished_at"], "2026-10-06T15:00:00Z")

    def test_persists_error_without_secret_trace(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            report = output / "current" / "report.json"
            report.parent.mkdir()
            report.write_text(json.dumps({
                "startedAt": "2026-10-06T14:58:01Z", "status": "error",
                "errors": [{"step": "runtime", "error": "Authorization: Bearer TOPSECRET"}],
            }), encoding="utf-8")
            record = append_from_report("2026-10-06T14:58:00Z", 1, output)

            self.assertEqual(record["status"], "error")
            self.assertEqual(record["error"], "runtime failed")
            self.assertNotIn("TOPSECRET", (output / "run-history.jsonl").read_text(encoding="utf-8"))

    def test_does_not_copy_old_report_into_failed_new_run(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            report = output / "current" / "report.json"
            report.parent.mkdir()
            report.write_text(json.dumps({
                "startedAt": "2026-10-06T15:00:00Z", "finishedAt": "2026-10-06T15:01:00Z",
                "status": "success", "showsCount": 7,
            }), encoding="utf-8")

            record = append_from_report("2026-10-06T16:00:00Z", 1, output)

            self.assertEqual(record["status"], "error")
            self.assertIsNone(record["finished_at"])
            self.assertIsNone(record["shows_count"])
