"""WebSocket URL routing for nilakandi application.

Defines the mapping between WebSocket URL paths and channel consumers. The
primary consumer exposed here streams Celery task progress (stored in Redis)
to connected clients so the front-end can render real-time loading states.
"""
from __future__ import annotations

from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    # Example: ws://<host>/ws/task-progress/<task_uuid>/
    re_path(r"^ws/task-progress/(?P<task_id>[0-9a-f-]+)/$", consumers.TaskProgressConsumer.as_asgi()),
]
