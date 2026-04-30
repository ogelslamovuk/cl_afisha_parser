import json
import os
from datetime import datetime, timezone
from src.logger import log_info


def validate_shows(shows, config):
    min_shows = int(config.get("validation", {}).get("min_shows", 100))
    errors = []
    if len(shows) < min_shows:
        errors.append(f"shows count {len(shows)} < min_shows {min_shows}")
    for i, s in enumerate(shows):
        for key in ("showId", "showUrl", "title", "dttmShowStart"):
            if s.get(key) in (None, ""):
                errors.append(f"row {i} missing {key}")
                break
    return len(errors) == 0, {"ok": len(errors) == 0, "errors": errors}


def _dump_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_outputs(payload, report, is_valid, config):
    current_file = config["output"]["current_file"]
    report_file = config["output"]["report_file"]
    archive_dir = config["output"]["archive_dir"]

    os.makedirs(os.path.dirname(current_file), exist_ok=True)
    os.makedirs(os.path.dirname(report_file), exist_ok=True)
    os.makedirs(archive_dir, exist_ok=True)

    archive_file = None
    if is_valid:
        _dump_json(current_file, payload)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        archive_file = os.path.join(archive_dir, f"{ts}_go2.json")
        _dump_json(archive_file, payload)
        log_info("write", f"{current_file} shows={len(payload.get('shows', []))}")

    _dump_json(report_file, report)
    return {"output_file": current_file if is_valid else None, "archive_file": archive_file}


def write_report_only(report, config):
    report_file = "output/current/report.json"
    if config:
        report_file = config["output"]["report_file"]
    os.makedirs(os.path.dirname(report_file), exist_ok=True)
    _dump_json(report_file, report)
