from __future__ import annotations

import json
import sys
from pathlib import Path


HISTORY_LIMIT = 200
OUTPUT_DIR = Path("output")


def _error(report: dict, exit_code: int) -> str:
    errors = report.get("errors") or []
    if errors and isinstance(errors[0], dict):
        return str(errors[0].get("error") or "")[:300]
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
