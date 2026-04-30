import os
import yaml


class ConfigError(Exception):
    pass


def deep_merge(base, override):
    if isinstance(base, dict) and isinstance(override, dict):
        out = dict(base)
        for k, v in override.items():
            out[k] = deep_merge(out.get(k), v)
        return out
    return override if override is not None else base


def load_config(path: str):
    defaults = {
        "source": {"start_url": "https://bycard.by/objects/minsk/2", "max_pages": 20, "headless": True, "timeout_seconds": 45},
        "output": {"current_file": "output/current/go2.json", "report_file": "output/current/report.json", "archive_dir": "output/archive"},
        "validation": {"min_shows": 100},
        "telegram": {"enabled": False, "bot_token_env": "TELEGRAM_BOT_TOKEN", "recipients": [], "notify_on_success": True, "notify_on_error": True, "notify_on_validation_failed": True},
    }
    if not os.path.exists(path):
        raise ConfigError(f"config file not found: {path}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            user = yaml.safe_load(f) or {}
    except Exception as exc:
        raise ConfigError(f"failed to parse config.yaml: {exc}") from exc
    cfg = deep_merge(defaults, user)
    if not cfg["source"].get("start_url"):
        raise ConfigError("source.start_url is required")
    return cfg
