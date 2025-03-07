from pathlib import Path
from config.env import env
import logging.handlers

# Logging configuration
# https://docs.djangoproject.com/en/5.1/topics/logging/

LOG_DIR = Path(env("LOG_DIRECTORY", default="/var/log/nilakandi"))

LOG_DIR.mkdir(parents=True, exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "file": {
            "level": "DEBUG",
            "class": "logging.handlers.TimedRotatingFileHandler",
            "filename": Path(LOG_DIR, "nilakandi.log"),
            "when": "D",
            "interval": 1,
            "backupCount": 30,
            "formatter": "verbose",
        },
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["file", "console"],
            "level": "INFO",
            "propagate": True,
        },
        "django.db": {
            "handlers": ["file", "console"],
            "level": "INFO",
            "propagate": False
        }
    },
}
