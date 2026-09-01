import json
import subprocess
import unittest
from unittest.mock import patch

from src.publisher_github import _wait_for_pages_deploy


def _result(payload):
    return subprocess.CompletedProcess(
        args=["gh"],
        returncode=0,
        stdout=json.dumps(payload),
        stderr="",
    )


class PagesDeployWaitTests(unittest.TestCase):
    @patch("src.publisher_github.shutil.which", return_value="gh")
    @patch("src.publisher_github._run_gh")
    def test_accepts_successful_deploy_job_when_workflow_status_is_stuck(self, run_gh, _which):
        run_gh.side_effect = [
            _result(
                [
                    {
                        "databaseId": 123,
                        "status": "in_progress",
                        "conclusion": "",
                        "url": "https://example.test/run/123",
                    }
                ]
            ),
            _result(
                {
                    "jobs": [
                        {
                            "name": "deploy",
                            "status": "completed",
                            "conclusion": "success",
                        }
                    ]
                }
            ),
        ]

        result = _wait_for_pages_deploy("abc", {"deploy_timeout_seconds": 5})

        self.assertTrue(result["ok"])
        self.assertEqual(result["confirmed_by"], "deploy_job")
        self.assertEqual(run_gh.call_count, 2)

    @patch("src.publisher_github.shutil.which", return_value="gh")
    @patch("src.publisher_github._run_gh")
    def test_keeps_completed_workflow_failure_as_failure(self, run_gh, _which):
        run_gh.side_effect = [
            _result(
                [
                    {
                        "databaseId": 456,
                        "status": "completed",
                        "conclusion": "failure",
                        "url": "https://example.test/run/456",
                    }
                ]
            )
        ]

        result = _wait_for_pages_deploy("def", {"deploy_timeout_seconds": 5})

        self.assertFalse(result["ok"])
        self.assertIn("failure", result["error"])

    @patch("src.publisher_github.shutil.which", return_value="gh")
    @patch("src.publisher_github._run_gh")
    def test_returns_failed_deploy_job_without_waiting_for_timeout(self, run_gh, _which):
        run_gh.side_effect = [
            _result(
                [
                    {
                        "databaseId": 789,
                        "status": "in_progress",
                        "conclusion": "",
                        "url": "https://example.test/run/789",
                    }
                ]
            ),
            _result(
                {
                    "jobs": [
                        {
                            "name": "deploy",
                            "status": "completed",
                            "conclusion": "failure",
                        }
                    ]
                }
            ),
        ]

        result = _wait_for_pages_deploy("ghi", {"deploy_timeout_seconds": 5})

        self.assertFalse(result["ok"])
        self.assertIn("deploy job", result["error"])
        self.assertEqual(run_gh.call_count, 2)


if __name__ == "__main__":
    unittest.main()
