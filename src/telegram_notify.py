import os
import requests
from src.logger import log_info


def _msg_success(report):
    return (
        "CL Afisha Parser OK\n"
        f"shows: {report.get('showsCount', 0)}\n"
        f"pages: {report.get('pagesScanned', 0)}\n"
        f"duration: {report.get('durationSeconds', 0)}s\n"
        "output: output/current/go2.json"
    )


def _msg_validation_failed(report):
    reason = "; ".join((report.get("validation") or {}).get("errors", [])[:3]) or "unknown"
    return (
        "CL Afisha Parser WARNING\n"
        "validation failed\n"
        f"reason: {reason}\n"
        "current output not overwritten"
    )


def _msg_error(report):
    err = (report.get("errors") or [{"step": "unknown", "error": "unknown"}])[-1]
    return f"CL Afisha Parser ERROR\nstep: {err.get('step')}\nerror: {err.get('error')}"


def send_telegram_summary(report, config):
    res = {"enabled": False, "sent": 0, "failed_recipients": [], "errors": []}
    if not config:
        return res
    tg = config.get("telegram", {})
    if not tg.get("enabled", False):
        return res

    res["enabled"] = True
    token = os.getenv(tg.get("bot_token_env", "TELEGRAM_BOT_TOKEN"))
    if not token:
        res["errors"].append("telegram enabled but token is missing")
        return res

    status = report.get("status")
    if status == "success" and tg.get("notify_on_success", True):
        text = _msg_success(report)
    elif status == "validation_failed" and tg.get("notify_on_validation_failed", True):
        text = _msg_validation_failed(report)
    elif status == "error" and tg.get("notify_on_error", True):
        text = _msg_error(report)
    else:
        return res

    for r in tg.get("recipients", []):
        if not r.get("enabled", False):
            continue
        chat_id = r.get("chat_id")
        name = r.get("name", "unknown")
        if not chat_id:
            res["failed_recipients"].append(name)
            res["errors"].append(f"{name}: empty chat_id")
            continue
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try:
            rr = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=20)
            if rr.ok:
                res["sent"] += 1
            else:
                res["failed_recipients"].append(name)
                res["errors"].append(f"{name}: http {rr.status_code}")
        except Exception as exc:
            res["failed_recipients"].append(name)
            res["errors"].append(f"{name}: {exc}")

    log_info("telegram", f"sent recipients={res['sent']}")
    return res
