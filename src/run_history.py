from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path


HISTORY_LIMIT = 200
OUTPUT_DIR = Path("output")


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _belongs_to_current_run(report: dict, started_at: str) -> bool:
    report_started = _parse_time(report.get("startedAt"))
    run_started = _parse_time(started_at)
    return bool(report_started and run_started and report_started >= run_started - timedelta(seconds=5))


def _error(report: dict, exit_code: int) -> str:
    errors = report.get("errors") or []
    if errors and isinstance(errors[0], dict):
        step = str(errors[0].get("step") or "runtime")
        safe_step = step if step in {"config", "runtime", "github_pages"} else "runtime"
        return f"{safe_step} failed"
    if exit_code:
        return f"Process exited with code {exit_code}"
    if report.get("status") != "success":
        return str(report.get("status") or "Unknown result")[:300]
    return ""


def append_from_report(started_at: str, exit_code: int, output_dir: Path = OUTPUT_DIR) -> dict:
    report_path = output_dir / "current" / "report.json"
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        report = {}
    is_current = _belongs_to_current_run(report, started_at)
    if not is_current:
        report = {}
    error = _error(report, exit_code)
    record = {
        "started_at": started_at,
        "finished_at": report.get("finishedAt"),
        "status": "success" if report.get("status") == "success" and not exit_code else "error",
        "error": error,
        "shows_count": report.get("showsCount"),
    }
    history_path = output_dir / "run-history.jsonl"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.touch(exist_ok=True)
    lines = history_path.read_text(encoding="utf-8").splitlines()[-(HISTORY_LIMIT - 1):]
    lines.append(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
    history_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return record


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python -m src.run_history <started_at> <exit_code>")
    append_from_report(sys.argv[1], int(sys.argv[2]))
