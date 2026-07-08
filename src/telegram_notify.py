import os
import requests
from src.logger import log_info


TELEGRAM_LIMIT = 4096


def _split_message(message, limit=TELEGRAM_LIMIT):
    if len(message) <= limit:
        return [message]

    chunks = []
    current = ""
    for line in message.splitlines():
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = line
    if current:
        chunks.append(current)
    return chunks


def _get_token(tg):
    token = tg.get("bot_token", "")
    if token:
        return token

    token_env = tg.get("bot_token_env", "TELEGRAM_BOT_TOKEN")
    if token_env:
        return os.getenv(token_env, "")
    return ""


def _send_text(text, config):
    res = {"enabled": False, "sent": 0, "failed_recipients": [], "errors": []}
    if not config:
        return res

    tg = config.get("telegram", {})
    if not tg.get("enabled", False):
        return res

    res["enabled"] = True
    token = _get_token(tg)
    if not token:
        res["errors"].append("telegram enabled but token is missing")
        return res

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for r in tg.get("recipients", []):
        if not r.get("enabled", False):
            continue
        chat_id = r.get("chat_id")
        name = r.get("name", "unknown")
        if not chat_id:
            res["failed_recipients"].append(name)
            res["errors"].append(f"{name}: empty chat_id")
            continue

        for chunk in _split_message(text):
            try:
                rr = requests.post(
                    url,
                    json={
                        "chat_id": chat_id,
                        "text": chunk,
                        "disable_web_page_preview": True,
                    },
                    timeout=20,
                )
                if rr.ok:
                    res["sent"] += 1
                else:
                    res["failed_recipients"].append(name)
                    res["errors"].append(f"{name}: http {rr.status_code}: {rr.text}")
            except Exception as exc:
                res["failed_recipients"].append(name)
                res["errors"].append(f"{name}: {exc}")

    log_info("telegram", f"sent recipients={res['sent']}")
    return res


def _msg_success(report):
    github = report.get("githubPages") or {}
    publish_status = "опубликован на GitHub Pages" if github.get("published") else "не опубликован"
    return (
        "Парсинг BYCard для афиши выполнен успешно.\n"
        "Ошибок нет.\n"
        f"Событий: {report.get('showsCount', 0)}\n"
        f"Страниц просканировано: {report.get('pagesScanned', 0)}\n"
        f"JSON: {publish_status}.\n"
        f"URL: {github.get('url', 'https://ogelslamovuk.github.io/cl_afisha_parser/data/go2.json')}"
    )


def _msg_validation_failed(report):
    reason = "; ".join((report.get("validation") or {}).get("errors", [])[:3]) or "unknown"
    return (
        "Парсинг BYCard для афиши завершился с предупреждением.\n"
        "Валидация не прошла.\n"
        f"Причина: {reason}\n"
        "Текущий опубликованный JSON не перезаписан."
    )


def _msg_error(report):
    err = (report.get("errors") or [{"step": "unknown", "error": "unknown"}])[-1]
    return (
        "Парсинг BYCard для афиши завершился с ошибкой.\n"
        f"Шаг: {err.get('step')}\n"
        f"Ошибка: {err.get('error')}"
    )


def send_telegram_summary(report, config):
    res = {"enabled": False, "sent": 0, "failed_recipients": [], "errors": []}
    if not config:
        return res
    tg = config.get("telegram", {})
    if not tg.get("enabled", False):
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

    return _send_text(text, config)
