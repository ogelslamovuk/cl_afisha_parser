from src.config import load_config, ConfigError
from src.bycard_parser import fetch_screening_events
from src.normalizer import normalize_events
from src.writer import validate_shows, write_outputs
from src.logger import log_info, log_error
from src.telegram_notify import send_telegram_summary

from datetime import datetime, timezone
import time
import traceback


def main() -> int:
    start_ts = time.time()
    started_at = datetime.now(timezone.utc)
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

        write_result = write_outputs(normalized, report, is_valid, config)
        report["outputFile"] = write_result.get("output_file")
        report["archiveFile"] = write_result.get("archive_file")

        report["status"] = "success" if is_valid else "validation_failed"

    except ConfigError as exc:
        report["errors"].append({"step": "config", "error": str(exc)})
        log_error("config", str(exc))
    except Exception as exc:
        report["errors"].append({"step": "runtime", "error": str(exc), "trace": traceback.format_exc()})
        log_error("runtime", str(exc))

    finished_at = datetime.now(timezone.utc)
    report["finishedAt"] = finished_at.isoformat()
    report["durationSeconds"] = round(time.time() - start_ts, 2)

    tg_result = send_telegram_summary(report, config if 'config' in locals() else None)
    report["telegram"] = tg_result

    # rewrite report to include telegram status
    from src.writer import write_report_only

    write_report_only(report, (config if 'config' in locals() else None))

    log_info("done", f"duration={report['durationSeconds']}s")
    return 0 if report["status"] in ("success", "validation_failed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
