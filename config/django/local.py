# flake8: noqa

from .base import *

INSTALLED_APPS.append("django_extensions")

SKIPPABLE_HTTP_ERROR: list[int] = [
    400,  # Bad Request
    401,  # Unauthorized
    403,  # Forbidden
    404,  # Not Found
    409,  # Conflict
    500,  # Internal Server Error
    501,  # Not Implemented
    504,  # Gateway Timeout
]
EARLIEST_DATA: str = env("EARLIEST_DATA", default="20200101") if not DEBUG else "20250101"

if DEBUG:
    # The order is important. The new middleware must come before CsrfViewMiddleware.
    MIDDLEWARE.insert(
        MIDDLEWARE.index("django.middleware.csrf.CsrfViewMiddleware"),
        "nilakandi.middleware.ForceTemporaryFileUploadHandlerMiddleware",
    )
    INSTALLED_APPS.append("debug_toolbar")
    MIDDLEWARE.append("debug_toolbar.middleware.DebugToolbarMiddleware")
    INTERNAL_IPS = ["127.0.0.1"]
    # tricks to have debug toolbar when developing with docker
    import socket

    hostname, _, ips = socket.gethostbyname_ex(socket.gethostname())
    INTERNAL_IPS += [ip[:-1] + "1" for ip in ips]
