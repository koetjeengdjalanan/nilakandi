"""ASGI entrypoint.

Supports both traditional Django HTTP handling and WebSocket connections via
`channels` for real-time task progress updates.
"""

from __future__ import annotations

import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", os.getenv("DJANGO_SETTINGS_MODULE", "config.django.local"))

# Standard Django ASGI application to handle traditional HTTP requests.
django_asgi_app = get_asgi_application()

try:  # Local import to avoid import-time side effects if migrations run without channels
    from nilakandi.routing import websocket_urlpatterns  # type: ignore
except Exception:  # pragma: no cover - fallback if routing not yet created
    websocket_urlpatterns = []  # type: ignore

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AuthMiddlewareStack(
            URLRouter(
                websocket_urlpatterns,
            )
        ),
    }
)
