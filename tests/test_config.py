import tempfile
from pathlib import Path

from watchline_hermes_plugin.config import (
    load_hermes_config,
    patch_mcp_config,
    patch_watchline_config,
)


def test_configure_writes_platform_and_mcp_config():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.yaml"
        config = patch_watchline_config(
            api_key="wl_test",
            channel_id="ch_test",
            user_id="me",
            path=path,
        )
        patch_mcp_config(config, path=path)

        data = load_hermes_config(path)
        assert "watchline" in data["plugins"]["enabled"]
        assert data["platforms"]["watchline"]["extra"]["channel_id"] == "ch_test"
        assert data["mcp_servers"]["watchline"]["headers"]["x-watchline-channel-id"] == "ch_test"
        assert data["platforms"]["watchline"]["extra"]["delivery_channel"] == "main"
