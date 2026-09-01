import json
import os
import tempfile
import unittest

from src.writer import validate_shows, write_outputs


def _config(tmp):
    return {
        "output": {
            "current_file": os.path.join(tmp, "current", "go2.json"),
            "report_file": os.path.join(tmp, "current", "report.json"),
            "archive_dir": os.path.join(tmp, "archive"),
        },
        "validation": {"min_shows": 1, "min_theatres": 1, "min_distinct_dates": 1},
    }


def _show(show_id=1):
    return {
        "showId": show_id,
        "showUrl": f"https://saleframe.24afisha.by/?sid={show_id}",
        "eventUrl": f"https://bycard.by/afisha/minsk/kino/{show_id}?sid={show_id}",
        "title": "Film",
        "dttmShowStart": "2026-08-03T12:00:00+03:00",
        "theatreId": 10,
        "images": {"eventLargeImagePortrait": "https://example.test/poster.jpg"},
    }


class WriterTests(unittest.TestCase):
    def test_validate_shows_accepts_valid_minimal_show(self):
        ok, info = validate_shows([_show()], _config(os.getcwd()))

        self.assertTrue(ok)
        self.assertEqual(info["errors"], [])

    def test_write_outputs_writes_current_archive_and_report_when_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = _config(tmp)
            payload = {"shows": [_show()]}
            report = {"status": "success"}

            result = write_outputs(payload, report, True, config)

            self.assertTrue(os.path.exists(config["output"]["current_file"]))
            self.assertTrue(os.path.exists(config["output"]["report_file"]))
            self.assertTrue(os.path.exists(result["archive_file"]))
            with open(config["output"]["current_file"], "r", encoding="utf-8") as f:
                self.assertEqual(json.load(f), payload)

    def test_write_outputs_writes_report_only_when_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = _config(tmp)
            payload = {"shows": []}
            report = {"status": "validation_failed"}

            result = write_outputs(payload, report, False, config)

            self.assertIsNone(result["output_file"])
            self.assertIsNone(result["archive_file"])
            self.assertFalse(os.path.exists(config["output"]["current_file"]))
            self.assertTrue(os.path.exists(config["output"]["report_file"]))


if __name__ == "__main__":
    unittest.main()
