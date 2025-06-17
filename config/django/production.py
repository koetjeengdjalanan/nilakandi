from config.env import env

from .base import *  # noqa: F403

DEBUG = env("DEBUG", default=True)

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

EARLIEST_DATA: str = (
    env("EARLIEST_DATA", default="20200101") if not DEBUG else "20250101"  # noqa: F405
)
