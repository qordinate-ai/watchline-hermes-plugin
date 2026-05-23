"""Hermes CLI commands for Watchline setup."""

from __future__ import annotations

import argparse
import json
from typing import Any

from .config import (
    DEFAULT_API_BASE_URL,
    DEFAULT_DELIVERY_CHANNEL,
    DEFAULT_POLL_INTERVAL_SECONDS,
    DEFAULT_USER_ID,
    HERMES_CONFIG_PATH,
    load_hermes_config,
    mcp_config_for_display,
    normalize_config,
    patch_mcp_config,
    patch_watchline_config,
)


def build_cli(parser: argparse.ArgumentParser) -> None:
    subcommands = parser.add_subparsers(dest="watchline_command", required=True)

    configure = subcommands.add_parser("configure", help="Save Watchline Hermes config")
    configure.add_argument("--api-key", required=True)
    configure.add_argument("--channel-id", required=True)
    configure.add_argument("--user-id", default=DEFAULT_USER_ID)
    configure.add_argument("--api-base-url", default=DEFAULT_API_BASE_URL)
    configure.add_argument(
        "--poll-interval-seconds",
        type=int,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
    )
    configure.add_argument("--delivery-channel", default=DEFAULT_DELIVERY_CHANNEL)
    configure.set_defaults(func=_configure)

    install_mcp = subcommands.add_parser("install-mcp", help="Install Watchline hosted MCP config")
    install_mcp.set_defaults(func=_install_mcp)

    status = subcommands.add_parser("status", help="Print Watchline config status")
    status.set_defaults(func=_status)

    preview = subcommands.add_parser(
        "preview-delivery",
        help="Preview a Watchline delivery message",
    )
    preview.set_defaults(func=_preview_delivery)


def _configure(args: argparse.Namespace) -> None:
    config = patch_watchline_config(
        api_key=args.api_key,
        channel_id=args.channel_id,
        user_id=args.user_id,
        api_base_url=args.api_base_url,
        poll_interval_seconds=args.poll_interval_seconds,
        delivery_channel=args.delivery_channel,
    )
    patch_mcp_config(config)
    print(f"Saved Watchline platform and MCP config to {HERMES_CONFIG_PATH}.")
    print("Restart Hermes gateway to load the adapter and MCP tools.")


def _install_mcp(_: argparse.Namespace) -> None:
    config = _read_saved_config()
    patch_mcp_config(config)
    print(f"Saved Watchline MCP server to {HERMES_CONFIG_PATH}.")
    print("Restart Hermes gateway or start a new Hermes session to load MCP tools.")


def _status(_: argparse.Namespace) -> None:
    config = _read_saved_config()
    display = mcp_config_for_display(config)
    print("Watchline is configured.")
    print(f"  channel_id: {config.channel_id}")
    print(f"  user_id:    {config.user_id}")
    print(f"  api_base:   {config.api_base_url}")
    print(f"  delivery:   {config.delivery_channel}")
    print("")
    print("Hermes MCP entry:")
    print(json.dumps(display, indent=2))


def _preview_delivery(_: argparse.Namespace) -> None:
    from .delivery import format_delivery

    print(
        format_delivery(
            {
                "type": "watchline.match",
                "delivery_id": "del_preview",
                "watch_id": "watch_preview",
                "user_id": "me",
                "intent": "urgent billing emails",
                "event": {
                    "from": "customer@example.com",
                    "subject": "Production invoice failure",
                    "snippet": "Our invoice payment is failing before renewal.",
                },
            },
        ),
    )


def _read_saved_config() -> Any:
    data = load_hermes_config()
    try:
        platform = data["platforms"]["watchline"]
        return normalize_config(platform.get("extra", {}))
    except Exception as error:
        raise SystemExit(
            "Watchline is not configured. Run `hermes watchline configure` "
            f"first. ({error})"
        ) from error
