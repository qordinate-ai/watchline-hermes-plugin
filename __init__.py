"""Hermes plugin entrypoint for Watchline."""

from typing import Any


def register(ctx: Any) -> None:
    from watchline_hermes_plugin.adapter import register as register_plugin

    register_plugin(ctx)
