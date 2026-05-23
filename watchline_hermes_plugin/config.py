"""Configuration helpers for the Watchline Hermes plugin.

Hermes platform adapters receive a generic ``PlatformConfig`` object. Keeping
Watchline-specific validation in this module lets the CLI commands and gateway
adapter share the same rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from os import environ
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - Hermes normally ships PyYAML.
    yaml = None

DEFAULT_API_BASE_URL = "https://api.watch.qordinate.ai"
DEFAULT_USER_ID = "me"
DEFAULT_POLL_INTERVAL_SECONDS = 15
MIN_POLL_INTERVAL_SECONDS = 5
HERMES_CONFIG_PATH = Path.home() / ".hermes" / "config.yaml"
WATCHLINE_PLATFORM_NAME = "watchline"
DEFAULT_DELIVERY_CHANNEL = "main"


@dataclass(frozen=True)
class WatchlineConfig:
    api_key: str
    channel_id: str
    user_id: str = DEFAULT_USER_ID
    api_base_url: str = DEFAULT_API_BASE_URL
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS
    delivery_channel: str = DEFAULT_DELIVERY_CHANNEL

    @property
    def mcp_url(self) -> str:
        return f"{self.api_base_url.rstrip('/')}/v1/mcp"


def normalize_config(value: Any) -> WatchlineConfig:
    """Normalize config from Hermes ``PlatformConfig.extra`` or raw YAML."""

    raw = value if isinstance(value, dict) else {}
    api_key = _read_string(raw, "api_key") or environ.get("WATCHLINE_API_KEY", "").strip()
    channel_id = _read_string(raw, "channel_id") or environ.get("WATCHLINE_CHANNEL_ID", "").strip()
    user_id = (
        _read_string(raw, "user_id")
        or environ.get("WATCHLINE_USER_ID", "").strip()
        or DEFAULT_USER_ID
    )
    api_base_url = (
        _read_string(raw, "api_base_url")
        or environ.get("WATCHLINE_API_BASE_URL", "").strip()
        or DEFAULT_API_BASE_URL
    )
    poll_interval_seconds = _read_int(raw, "poll_interval_seconds")
    if poll_interval_seconds is None:
        poll_interval_seconds = DEFAULT_POLL_INTERVAL_SECONDS
    delivery_channel = (
        _read_string(raw, "delivery_channel")
        or environ.get("WATCHLINE_DELIVERY_CHANNEL", "").strip()
        or DEFAULT_DELIVERY_CHANNEL
    )

    if not api_key:
        raise ValueError("WATCHLINE_API_KEY or watchline.api_key is required.")
    if not channel_id:
        raise ValueError("WATCHLINE_CHANNEL_ID or watchline.channel_id is required.")

    return WatchlineConfig(
        api_key=api_key,
        channel_id=channel_id,
        user_id=user_id,
        api_base_url=api_base_url.rstrip("/"),
        poll_interval_seconds=max(MIN_POLL_INTERVAL_SECONDS, poll_interval_seconds),
        delivery_channel=delivery_channel,
    )


def config_from_platform(platform_config: Any) -> WatchlineConfig:
    return normalize_config(getattr(platform_config, "extra", {}) or {})


def load_hermes_config(path: Path = HERMES_CONFIG_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8")
    if yaml is None:
        import json

        loaded = json.loads(raw) if raw.strip() else {}
    else:
        loaded = yaml.safe_load(raw)
    return loaded if isinstance(loaded, dict) else {}


def write_hermes_config(data: dict[str, Any], path: Path = HERMES_CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_suffix(f"{path.suffix}.watchline.bak")
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        backup.chmod(0o600)
    if yaml is None:
        import json

        rendered = f"{json.dumps(data, indent=2)}\n"
    else:
        rendered = yaml.safe_dump(data, sort_keys=False)
    path.write_text(rendered, encoding="utf-8")
    path.chmod(0o600)


def patch_watchline_config(
    *,
    api_key: str,
    channel_id: str,
    user_id: str = DEFAULT_USER_ID,
    api_base_url: str = DEFAULT_API_BASE_URL,
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
    delivery_channel: str = DEFAULT_DELIVERY_CHANNEL,
    path: Path = HERMES_CONFIG_PATH,
) -> WatchlineConfig:
    """Write both Hermes platform config and top-level Watchline config."""

    config = normalize_config(
        {
            "api_key": api_key,
            "channel_id": channel_id,
            "user_id": user_id,
            "api_base_url": api_base_url,
            "poll_interval_seconds": poll_interval_seconds,
            "delivery_channel": delivery_channel,
        },
    )
    data = load_hermes_config(path)
    plugins = _ensure_dict(data, "plugins")
    enabled = plugins.setdefault("enabled", [])
    if not isinstance(enabled, list):
        enabled = []
        plugins["enabled"] = enabled
    if WATCHLINE_PLATFORM_NAME not in enabled:
        enabled.append(WATCHLINE_PLATFORM_NAME)

    gateway = _ensure_dict(data, "gateway")
    platforms = _ensure_dict(gateway, "platforms")
    platforms[WATCHLINE_PLATFORM_NAME] = {
        "enabled": True,
        "extra": {
            "api_key": config.api_key,
            "channel_id": config.channel_id,
            "user_id": config.user_id,
            "api_base_url": config.api_base_url,
            "poll_interval_seconds": config.poll_interval_seconds,
            "delivery_channel": config.delivery_channel,
        },
    }
    write_hermes_config(data, path)
    return config


def patch_mcp_config(config: WatchlineConfig, path: Path = HERMES_CONFIG_PATH) -> None:
    """Install the hosted Watchline MCP server into Hermes config.yaml."""

    data = load_hermes_config(path)
    mcp_servers = _ensure_dict(data, "mcp_servers")
    mcp_servers[WATCHLINE_PLATFORM_NAME] = {
        "url": config.mcp_url,
        "headers": {
            "Authorization": f"Bearer {config.api_key}",
            "x-watchline-channel-id": config.channel_id,
            "x-watchline-user-id": config.user_id,
        },
    }
    write_hermes_config(data, path)


def mcp_config_for_display(config: WatchlineConfig) -> dict[str, Any]:
    return {
        "url": config.mcp_url,
        "headers": {
            "Authorization": "Bearer wl_...",
            "x-watchline-channel-id": config.channel_id,
            "x-watchline-user-id": config.user_id,
        },
    }


def _ensure_dict(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.setdefault(key, {})
    if not isinstance(value, dict):
        value = {}
        parent[key] = value
    return value


def _read_string(raw: dict[str, Any], key: str) -> str | None:
    value = raw.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _read_int(raw: dict[str, Any], key: str) -> int | None:
    value = raw.get(key)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return int(value)
        except ValueError:
            return None
    return None
