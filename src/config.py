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


def _read_yaml_file(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config(path: str, local_path: str = "config.local.yaml"):
    defaults = {
        "source": {
            "start_url": "https://bycard.by/objects/minsk/2",
            "api_url": "https://api.24afisha.by/api/v3/pages/objects",
            "city_id": 3,
            "object_type_id": 2,
            "per_page": 18,
            "max_pages": 20,
            "timeout_seconds": 45,
            "connect_timeout_seconds": 10,
            "retries": 2,
            "retry_delay_seconds": 1,
            "max_response_bytes": 31457280,
            "fallback_ips": ["178.172.148.3"],
        },
        "output": {"current_file": "output/current/go2.json", "report_file": "output/current/report.json", "archive_dir": "output/archive"},
        "validation": {"min_shows": 100, "min_theatres": 15, "min_distinct_dates": 3},
        "telegram": {"enabled": False, "bot_token_env": "TELEGRAM_BOT_TOKEN", "recipients": [], "notify_on_success": True, "notify_on_error": True, "notify_on_validation_failed": True},
    }
    if not os.path.exists(path):
        raise ConfigError(f"config file not found: {path}")
    try:
        user = _read_yaml_file(path)
        local = _read_yaml_file(local_path) if local_path else {}
    except Exception as exc:
        raise ConfigError(f"failed to parse config.yaml: {exc}") from exc
    cfg = deep_merge(deep_merge(defaults, user), local)
    if not cfg["source"].get("start_url"):
        raise ConfigError("source.start_url is required")
    if not cfg["source"].get("api_url"):
        raise ConfigError("source.api_url is required")
    return cfg
