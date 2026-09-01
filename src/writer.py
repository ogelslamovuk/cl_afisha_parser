import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from src.logger import log_info


REQUIRED_SHOW_FIELDS = ("showId", "showUrl", "eventUrl", "title", "dttmShowStart")


def _validation_config(config):
    cfg = config.get("validation", {})
    return {
        "min_shows": int(cfg.get("min_shows", 100)),
        "min_theatres": int(cfg.get("min_theatres", 0)),
        "min_distinct_dates": int(cfg.get("min_distinct_dates", 0)),
    }


def _is_http_url(value):
    if not value:
        return True
    parsed = urlparse(str(value))
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _add_collection_errors(shows, limits, errors):
    if len(shows) < limits["min_shows"]:
        errors.append(f"shows count {len(shows)} < min_shows {limits['min_shows']}")

    theatre_ids = {show.get("theatreId") for show in shows if show.get("theatreId") is not None}
    if len(theatre_ids) < limits["min_theatres"]:
        errors.append(f"theatres count {len(theatre_ids)} < min_theatres {limits['min_theatres']}")

    distinct_dates = {
        str(show.get("dttmShowStart"))[:10]
        for show in shows
        if show.get("dttmShowStart")
    }
    if len(distinct_dates) < limits["min_distinct_dates"]:
        errors.append(
            f"dates count {len(distinct_dates)} < min_distinct_dates {limits['min_distinct_dates']}"
        )

    show_ids = [show.get("showId") for show in shows if show.get("showId") is not None]
    duplicate_count = len(show_ids) - len(set(show_ids))
    if duplicate_count:
        errors.append(f"duplicate showId count {duplicate_count}")


def _add_row_errors(index, show, errors):
    for key in REQUIRED_SHOW_FIELDS:
        if show.get(key) in (None, ""):
            errors.append(f"row {index} missing {key}")
            return

    for key in ("showUrl", "eventUrl"):
        if not _is_http_url(show.get(key)):
            errors.append(f"row {index} invalid {key}")
            return

    image = (show.get("images") or {}).get("eventLargeImagePortrait")
    if image and not _is_http_url(image):
        errors.append(f"row {index} invalid eventLargeImagePortrait")


def validate_shows(shows, config):
    errors = []
    _add_collection_errors(shows, _validation_config(config), errors)
    for index, show in enumerate(shows):
        _add_row_errors(index, show, errors)
    return not errors, {"ok": not errors, "errors": errors}


def _dump_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def write_outputs(payload, report, is_valid, config):
    current_file = config["output"]["current_file"]
    report_file = config["output"]["report_file"]
    archive_dir = config["output"]["archive_dir"]

    archive_file = None
    if is_valid:
        _dump_json(current_file, payload)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        archive_file = str(Path(archive_dir) / f"{ts}_go2.json")
        _dump_json(archive_file, payload)
        log_info("write", f"{current_file} shows={len(payload.get('shows', []))}")

    _dump_json(report_file, report)
    return {"output_file": current_file if is_valid else None, "archive_file": archive_file}


def write_report_only(report, config):
    report_file = "output/current/report.json"
    if config:
        report_file = config["output"]["report_file"]
    _dump_json(report_file, report)
