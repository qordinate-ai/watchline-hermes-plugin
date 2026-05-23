"""Delivery formatting and polling primitives."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class DeliveryClient(Protocol):
    def pending(self, *, limit: int = 50, cursor: str | None = None) -> dict[str, Any]: ...

    def ack(self, delivery_ids: list[str]) -> None: ...


def format_delivery(delivery: dict[str, Any]) -> str:
    """Render a Watchline delivery as the user message Hermes should receive."""

    if delivery.get("type") == "watchline.match":
        return "\n".join(
            [
                f"Matched event with user intent: {delivery.get('intent', '')}",
                "",
                "Use this event as fresh context. Only act if the user intent asks for action.",
                "",
                "Event:",
                _stable_json(delivery.get("event", {})),
            ],
        )
    return "\n".join(
        [
            f"Watch needs action: {delivery.get('action', '')}",
            "",
            f"User intent: {delivery.get('intent', '')}",
            "",
            "Connection links:",
            _stable_json(delivery.get("connect_urls", {})),
        ],
    )


@dataclass(frozen=True)
class DeliveryChannel:
    value: str
    platform: str | None = None
    chat_id: str | None = None
    thread_id: str | None = None

    @property
    def is_main(self) -> bool:
        return self.value == "main"

    @property
    def uses_home_channel(self) -> bool:
        return self.platform is not None and self.chat_id is None


def parse_delivery_channel(value: str | None) -> DeliveryChannel:
    raw = (value or "main").strip()
    if not raw or raw.lower() == "main":
        return DeliveryChannel(value="main")

    parts = raw.split(":", 2)
    platform = parts[0].strip().lower()
    chat_id = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
    thread_id = parts[2].strip() if len(parts) > 2 and parts[2].strip() else None
    return DeliveryChannel(
        value=raw,
        platform=platform,
        chat_id=chat_id,
        thread_id=thread_id,
    )


def delivery_id(delivery: dict[str, Any]) -> str:
    raw = delivery.get("delivery_id")
    return str(raw) if raw else ""


def _stable_json(value: Any) -> str:
    import json

    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)
