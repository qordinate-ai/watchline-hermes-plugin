"""Hermes platform adapter for Watchline pull delivery."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from datetime import datetime
from typing import Any

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
)
from gateway.session import SessionSource

from .client import WatchlineClient
from .config import (
    DEFAULT_API_BASE_URL,
    WATCHLINE_PLATFORM_NAME,
    config_from_platform,
)
from .delivery import delivery_id, format_delivery, parse_delivery_channel

logger = logging.getLogger(__name__)


class WatchlinePlatformAdapter(BasePlatformAdapter):
    """Pull Watchline deliveries and feed them into Hermes' normal gateway."""

    def __init__(self, config: PlatformConfig):
        super().__init__(config=config, platform=Platform(WATCHLINE_PLATFORM_NAME))
        self.watchline_config = config_from_platform(config)
        self.client = WatchlineClient(self.watchline_config)
        self._poll_task: asyncio.Task | None = None
        self.gateway_runner: Any | None = None

    @property
    def name(self) -> str:
        return "Watchline"

    async def connect(self) -> bool:
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        return True

    async def disconnect(self) -> None:
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._poll_task

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        return SendResult(
            success=False,
            error=(
                "Watchline is an inbound delivery adapter and cannot send "
                "messages back to Watchline."
            ),
        )

    async def get_chat_info(self, chat_id: str) -> dict[str, Any]:
        return {"name": chat_id, "type": "watchline"}

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                delivered = await self._poll_once()
                if delivered:
                    logger.info("Watchline delivered %s event(s) into Hermes", delivered)
            except Exception as error:
                logger.warning("Watchline delivery poll failed: %s", error)
            await asyncio.sleep(self.watchline_config.poll_interval_seconds)

    async def _poll_once(self) -> int:
        cursor: str | None = None
        ack_ids: list[str] = []
        delivered = 0
        while True:
            response = await asyncio.to_thread(self.client.pending, limit=50, cursor=cursor)
            for item in response.get("data", []):
                if isinstance(item, dict):
                    await self._deliver(item)
                    delivery_public_id = delivery_id(item)
                    if delivery_public_id:
                        ack_ids.append(delivery_public_id)
                    delivered += 1
            next_cursor = response.get("next_cursor")
            cursor = next_cursor if isinstance(next_cursor, str) and next_cursor else None
            if not cursor:
                break
        await asyncio.to_thread(self.client.ack, ack_ids)
        return delivered

    async def _deliver(self, delivery: dict[str, Any]) -> None:
        if not self.gateway_runner:
            raise RuntimeError("Hermes gateway runner is not ready.")
        if not self._message_handler:
            raise RuntimeError("Hermes gateway message handler is not ready.")
        source = self._resolve_delivery_source(delivery)
        message_id = delivery_id(delivery) or None
        event = MessageEvent(
            text=format_delivery(delivery),
            message_type=MessageType.TEXT,
            source=source,
            raw_message=delivery,
            message_id=message_id,
            timestamp=datetime.now(),
            internal=True,
        )
        response_text = await self.gateway_runner._handle_message(event)
        if not response_text:
            return

        adapter = self.gateway_runner.adapters.get(source.platform)
        if not adapter:
            raise RuntimeError(f"Hermes adapter for {source.platform.value} is not active.")
        metadata = {"thread_id": source.thread_id} if source.thread_id else None
        result = await adapter.send(
            chat_id=source.chat_id,
            content=response_text,
            metadata=metadata,
        )
        if not getattr(result, "success", False):
            raise RuntimeError(getattr(result, "error", "Hermes send returned success=False"))

    def _resolve_delivery_source(self, delivery: dict[str, Any]) -> SessionSource:
        channel = parse_delivery_channel(self.watchline_config.delivery_channel)
        if channel.is_main:
            platform, chat_id, chat_name, thread_id = self._main_home_channel()
        else:
            platform = Platform(channel.platform or "")
            if channel.chat_id:
                chat_id = channel.chat_id
                chat_name = channel.chat_id
                thread_id = channel.thread_id
            else:
                home = self.gateway_runner.config.get_home_channel(platform)
                if not home or not home.chat_id:
                    raise RuntimeError(
                        f"No Hermes home channel configured for {platform.value}; "
                        "run /sethome there or set watchline.delivery_channel to "
                        f"{platform.value}:<chat_id>."
                    )
                chat_id = str(home.chat_id)
                chat_name = home.name
                thread_id = str(home.thread_id) if home.thread_id else None

        message_id = delivery_id(delivery) or None
        return SessionSource(
            platform=platform,
            chat_id=chat_id,
            chat_name=chat_name,
            chat_type="dm",
            user_id="system:watchline",
            user_name="Watchline",
            thread_id=thread_id,
            message_id=message_id,
        )

    def _main_home_channel(self) -> tuple[Platform, str, str, str | None]:
        excluded = {
            self.platform,
            Platform.LOCAL,
            Platform.API_SERVER,
            Platform.WEBHOOK,
            Platform.MSGRAPH_WEBHOOK,
        }
        for platform in self.gateway_runner.adapters:
            if platform in excluded:
                continue
            home = self.gateway_runner.config.get_home_channel(platform)
            if home and home.chat_id:
                return (
                    platform,
                    str(home.chat_id),
                    home.name,
                    str(home.thread_id) if home.thread_id else None,
                )
        raise RuntimeError(
            "No Hermes main/home channel configured for Watchline delivery. "
            "Run /sethome in the destination chat or set watchline.delivery_channel "
            "to <platform>:<chat_id>."
        )


def check_requirements() -> bool:
    return True


def validate_config(config: Any) -> bool:
    try:
        config_from_platform(config)
        return True
    except Exception:
        return False


def env_enablement() -> dict[str, Any] | None:
    api_key = os.getenv("WATCHLINE_API_KEY", "").strip()
    channel_id = os.getenv("WATCHLINE_CHANNEL_ID", "").strip()
    if not api_key or not channel_id:
        return None
    return {
        "api_key": api_key,
        "channel_id": channel_id,
        "user_id": os.getenv("WATCHLINE_USER_ID", "me").strip() or "me",
        "api_base_url": os.getenv("WATCHLINE_API_BASE_URL", DEFAULT_API_BASE_URL).strip()
        or DEFAULT_API_BASE_URL,
        "delivery_channel": os.getenv("WATCHLINE_DELIVERY_CHANNEL", "main").strip() or "main",
    }


def register(ctx: Any) -> None:
    ctx.register_platform(
        name=WATCHLINE_PLATFORM_NAME,
        label="Watchline",
        adapter_factory=lambda cfg: WatchlinePlatformAdapter(cfg),
        check_fn=check_requirements,
        validate_config=validate_config,
        is_connected=validate_config,
        env_enablement_fn=env_enablement,
        allow_all_env="WATCHLINE_ALLOW_ALL_USERS",
        allowed_users_env="WATCHLINE_ALLOWED_USERS",
        platform_hint=(
            "Watchline delivers matched external events. Treat each message as "
            "fresh event context and avoid saying it came from a human chat."
        ),
        emoji="🔔",
    )
    _register_cli(ctx)


def _register_cli(ctx: Any) -> None:
    from .watchline_cli import build_cli

    ctx.register_cli_command(
        name=WATCHLINE_PLATFORM_NAME,
        help="Configure Watchline delivery and hosted MCP for Hermes.",
        setup_fn=build_cli,
        handler_fn=None,
    )
