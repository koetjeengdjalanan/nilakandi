from .base import *  # noqa: F403

INSTALLED_APPS.append("django_extensions")  # noqa: F405

SKIPPABLE_HTTP_ERROR: list[int] = [
    400,  # Bad Request
    401,  # Unauthorized
    403,  # Forbidden
    404,  # Not Found
    409,  # Conflict
    500,  # Internal Server Error
    501,  # Not Implemented
]
EARLIEST_DATA: str = (
    env("EARLIEST_DATA", default="20200101") if not DEBUG else "20250101"  # noqa: F405
)
