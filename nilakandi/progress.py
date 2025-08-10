"""Utility helpers to publish Celery task progress snapshots to Redis.

Use this from inside a Celery task to push intermediate progress updates that
will be picked up by the WebSocket ``TaskProgressConsumer``.

Example:
    from nilakandi.progress import set_progress

    def some_long_task(...):
        set_progress(self.request.id, status="PROGRESS", result={"current": 1, "total": 10, "status": "Starting"})
        ... do work ...
        set_progress(self.request.id, status="PROGRESS", result={"current": 5, "total": 10, "status": "Halfway"})
        ...

The final SUCCESS/FAILURE state will overwrite this key automatically once the
result backend stores the final result, but intermediate updates let the UI
stay responsive.
"""

from __future__ import annotations

import json
from typing import Any

from django.conf import settings

try:
    from redis import Redis
except Exception:  # pragma: no cover
    Redis = None  # type: ignore


def _get_redis_url() -> str:
    return getattr(settings, "CELERY_RESULT_BACKEND", getattr(settings, "REDIS_URL", "redis://localhost:6379/0"))


def set_progress(task_id: str, status: str, result: dict[str, Any] | None = None, **extra: Any) -> None:
    """Store a progress structure in Redis under ``task-progress:<task_id>``.

    Parameters
    ----------
    task_id : str
        Celery task ID.
    status : str
        High-level status flag (e.g. PROGRESS, STARTED, SUCCESS, FAILURE).
    result : dict | None
        Nested structure describing progress metrics (must be JSON-serialisable).
    **extra : Any
        Additional top-level fields to include.
    """
    if Redis is None:  # pragma: no cover
        return
    r = Redis.from_url(_get_redis_url())
    payload = {"status": status}
    if result is not None:
        payload["result"] = result
    if extra:
        payload.update(extra)
    key = f"task-progress:{task_id}"
    ttl_seconds: int = int(getattr(settings, "TASK_PROGRESS_TTL_SECONDS", 60 * 60 * 24))  # default 24h
    r.set(key, json.dumps(payload), ex=ttl_seconds)
