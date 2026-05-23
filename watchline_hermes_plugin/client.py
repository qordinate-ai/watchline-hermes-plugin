"""Tiny Watchline API client used by the Hermes delivery adapter."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from watchline_hermes_plugin.config import WatchlineConfig


class WatchlineApiError(RuntimeError):
    pass


class WatchlineClient:
    def __init__(self, config: WatchlineConfig):
        self.config = config

    def pending(self, *, limit: int = 50, cursor: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"channel_id": self.config.channel_id, "limit": limit}
        if cursor:
            body["cursor"] = cursor
        return self._post("/v1/deliveries.pending", body)

    def ack(self, delivery_ids: list[str]) -> None:
        if not delivery_ids:
            return
        self._post(
            "/v1/deliveries.ack",
            {"channel_id": self.config.channel_id, "delivery_ids": delivery_ids},
        )

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        raw_body = json.dumps(body).encode("utf-8")
        request = Request(
            f"{self.config.api_base_url.rstrip('/')}{path}",
            data=raw_body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "watchline-hermes-plugin/0.1.0",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                raw = response.read()
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise WatchlineApiError(f"Watchline API returned {error.code}: {detail}") from error
        if not raw:
            return {}
        parsed = json.loads(raw.decode("utf-8"))
        return parsed if isinstance(parsed, dict) else {}
