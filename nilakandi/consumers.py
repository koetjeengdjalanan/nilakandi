"""Channel layer consumers.

Currently includes a WebSocket consumer that streams Celery task progress
JSON objects (persisted in Redis) to the client in real time. The client
subscribes by connecting to the path: ``ws://<host>/ws/task-progress/<task_id>/``.

Implementation notes:
    * Uses redis.asyncio for non-blocking polling.
    * Poll interval kept small (700ms) for responsiveness; adjust via
      ``TASK_PROGRESS_POLL_INTERVAL_SECONDS`` constant if needed.
    * Connection auto-closes once terminal task state encountered or if
      Redis key no longer exists.
    * Expected JSON schema resembles example in ``devAssets/celery_log.example.json``.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings

try:
    from redis.asyncio import Redis  # type: ignore
except Exception as e:  # pragma: no cover - import guard
    raise ImportError("redis>=5 with asyncio support is required for TaskProgressConsumer") from e

logger = logging.getLogger(__name__)

TASK_PROGRESS_POLL_INTERVAL_SECONDS: float = 0.7


class TaskProgressConsumer(AsyncWebsocketConsumer):
    """Stream Celery task progress to a WebSocket client.

    The consumer polls a Redis key derived from the provided ``task_id``.
    By default it checks two key naming patterns commonly produced by
    Celery backends:

    1. Custom progress key: ``task-progress:<task_id>`` (preferred)
    2. Result backend meta key: ``celery-task-meta-<task_id>``

    Whichever key is found first is used for the remainder of the session.

    Messages sent to the client are JSON-encoded objects of the structure:

    {
        "status": str,   # Task lifecycle status e.g. PROGRESS / STARTED / SUCCESS / FAILURE
        "result": {...}, # Nested progress payload (optional)
        ... other fields pass-through ...
    }

    The socket automatically closes when a terminal state is reached
    (``SUCCESS``, ``FAILURE``, ``REVOKED``) or when the key is missing for
    two consecutive polls.
    """

    redis: Redis | None
    redis_key: str | None
    _missing_count: int

    async def connect(self) -> None:  # noqa: D401
        """Validate path, establish Redis connection, and accept socket."""
        self.task_id: str = self.scope["url_route"]["kwargs"]["task_id"]
        self.redis = Redis.from_url(
            getattr(settings, "CELERY_RESULT_BACKEND", getattr(settings, "REDIS_URL", "redis://localhost:6379/0"))
        )
        self.redis_key = None
        self._missing_count = 0
        await self.accept()
        logger.info("task_progress_ws_connected", extra={"task_id": self.task_id})
        asyncio.create_task(self._poll_loop())

    async def disconnect(self, code: int) -> None:  # noqa: D401
        """Close Redis connection on disconnect."""
        try:
            if self.redis:
                await self.redis.close()
        finally:  # pragma: no cover - defensive cleanup
            logger.info(
                "task_progress_ws_disconnected",
                extra={
                    "task_id": getattr(self, "task_id", None),
                    "code": code,
                },
            )

    async def receive(self, text_data: str | None = None, bytes_data: bytes | None = None) -> None:  # noqa: D401
        """Ignore inbound messages (protocol is server push only)."""
        return None

    # Internal helpers -------------------------------------------------
    async def _resolve_key(self) -> str | None:
        """Find which Redis key currently stores progress metadata.

        Returns:
            The discovered key name or ``None`` if neither exists yet.
        """
        assert self.redis is not None
        custom_key: str = f"task-progress:{self.task_id}"
        backend_key: str = f"celery-task-meta-{self.task_id}"
        if await self.redis.exists(custom_key):  # type: ignore[arg-type]
            return custom_key
        if await self.redis.exists(backend_key):  # type: ignore[arg-type]
            return backend_key
        return None

    async def _poll_loop(self) -> None:
        """Continuously poll Redis for updated progress JSON and send to client."""
        assert self.redis is not None
        terminal_states: set[str] = {"SUCCESS", "FAILURE", "REVOKED"}
        while True:
            try:
                if not self.redis_key:
                    self.redis_key = await self._resolve_key()
                    if not self.redis_key:
                        self._missing_count += 1
                        if self._missing_count >= 2:
                            await self.close(code=4404)
                            return
                        await asyncio.sleep(TASK_PROGRESS_POLL_INTERVAL_SECONDS)
                        continue
                raw: bytes | None = await self.redis.get(self.redis_key)
                if raw is None:
                    self._missing_count += 1
                    if self._missing_count >= 2:
                        await self.close(code=4404)
                        return
                    await asyncio.sleep(TASK_PROGRESS_POLL_INTERVAL_SECONDS)
                    continue
                self._missing_count = 0
                try:
                    payload: dict[str, Any] = json.loads(raw.decode("utf-8"))
                except json.JSONDecodeError:
                    logger.warning(
                        "task_progress_ws_bad_json",
                        extra={
                            "task_id": self.task_id,
                            "snippet": raw[:50] if raw else None,
                        },
                    )
                    await asyncio.sleep(TASK_PROGRESS_POLL_INTERVAL_SECONDS)
                    continue
                await self.send_json(payload)
                status_val: str | None = str(payload.get("status")) if payload.get("status") else None
                if status_val in terminal_states:
                    await self.close(code=1000)
                    return
                await asyncio.sleep(TASK_PROGRESS_POLL_INTERVAL_SECONDS)
            except Exception as exc:  # pragma: no cover - runtime safety
                logger.exception("task_progress_ws_error", extra={"task_id": getattr(self, "task_id", None)})
                try:
                    await self.send_json({"status": "ERROR", "error": str(exc)})
                except Exception:
                    pass
                await asyncio.sleep(TASK_PROGRESS_POLL_INTERVAL_SECONDS)

    async def send_json(self, content: Any, close: bool = False) -> None:  # type: ignore[override]
        """Wrapper adding type annotation for send_json inherited method."""
        await super().send(text_data=json.dumps(content))
        if close:
            await self.close()
