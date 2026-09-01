from src.config import load_config, ConfigError
from src.bycard_parser import fetch_screening_events
from src.normalizer import normalize_events
from src.writer import validate_shows, write_outputs
from src.logger import log_info, log_error
from src.telegram_notify import send_telegram_summary
from src.publisher_github import publish_to_github_pages

from datetime import datetime, timezone, timedelta
import time
import traceback


APP_TZ = timezone(timedelta(hours=3))


def _exception_message(exc):
    return str(exc).strip() or exc.__class__.__name__


def _format_meta_time(value):
    if not value:
        dt = datetime.now(APP_TZ)
    else:
        dt = datetime.fromisoformat(value).astimezone(APP_TZ)
    return dt.replace(tzinfo=None, microsecond=0).isoformat()


def _add_payload_meta(payload, report):
    payload["meta"] = {
        "updatedAt": _format_meta_time(report.get("finishedAt")),
        "timezone": "UTC+3",
        "durationSec": report.get("durationSeconds"),
        "showsCount": report.get("showsCount"),
        "pagesScanned": report.get("pagesScanned"),
        "source": report.get("sourceUrl"),
        "status": report.get("status"),
        "validation": report.get("validation", {}),
    }
    return payload


def main() -> int:
    start_ts = time.time()
    started_at = datetime.now(timezone.utc)
    config = None
    normalized = None
    report = {
        "status": "error",
        "startedAt": started_at.isoformat(),
        "finishedAt": None,
        "durationSeconds": None,
        "sourceUrl": None,
        "pagesScanned": 0,
        "showsCount": 0,
        "outputFile": None,
        "archiveFile": None,
        "validation": {},
        "githubPages": {},
        "telegram": {},
        "errors": [],
    }

    log_info("start", "cl_afisha_parser")

    try:
        config = load_config("config.yaml")
        report["sourceUrl"] = config["source"]["start_url"]

        raw_events, pages_scanned = fetch_screening_events(config)
        report["pagesScanned"] = pages_scanned

        normalized = normalize_events(raw_events)
        shows = normalized["shows"]
        report["showsCount"] = len(shows)

        is_valid, validation_info = validate_shows(shows, config)
        report["validation"] = validation_info
        report["status"] = "success" if is_valid else "validation_failed"

    except ConfigError as exc:
        error = _exception_message(exc)
        report["errors"].append({"step": "config", "error": error})
        log_error("config", error)
    except Exception as exc:
        error = _exception_message(exc)
        report["errors"].append({"step": "runtime", "error": error, "trace": traceback.format_exc()})
        log_error("runtime", error)

    finished_at = datetime.now(timezone.utc)
    report["finishedAt"] = finished_at.isoformat()
    report["durationSeconds"] = round(time.time() - start_ts, 2)

    if normalized is not None and config is not None:
        normalized = _add_payload_meta(normalized, report)
        write_result = write_outputs(normalized, report, report["status"] == "success", config)
        report["outputFile"] = write_result.get("output_file")
        report["archiveFile"] = write_result.get("archive_file")
        report["githubPages"] = publish_to_github_pages(normalized, report, config)
        if report["status"] == "success" and report["githubPages"].get("enabled") and not report["githubPages"].get("published"):
            error_text = "; ".join(report["githubPages"].get("errors", [])) or "GitHub Pages deploy was not confirmed"
            report["status"] = "error"
            report["errors"].append({"step": "github_pages", "error": error_text})

    tg_result = send_telegram_summary(report, config)
    report["telegram"] = tg_result

    # rewrite report to include GitHub publication and Telegram statuses
    from src.writer import write_report_only

    write_report_only(report, config)

    log_info("done", f"duration={report['durationSeconds']}s")
    return 0 if report["status"] in ("success", "validation_failed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
