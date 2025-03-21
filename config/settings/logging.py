from pathlib import Path

from config.env import env

# Logging configuration
# https://docs.djangoproject.com/en/5.1/topics/logging/

LOG_DIR: Path = Path(env("LOG_DIRECTORY", default="/var/log/nilakandi"))

LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_LEVEL: str = env("LOG_LEVEL", default="WARNING") if not env("DEBUG") else "DEBUG"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} \t {asctime} {module} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} \t {asctime} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "file": {
            "level": LOG_LEVEL,
            "class": "logging.handlers.TimedRotatingFileHandler",
            "filename": Path(LOG_DIR, "nilakandi.log"),
            "when": "D",
            "interval": 1,
            "backupCount": 30,
            "formatter": "verbose",
        },
        "console": {
            "level": LOG_LEVEL,
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
            "level": "DEBUG",
            "propagate": False,
        },
        "django.db.save": {
            "handlers": ["file", "console"],
            "level": "INFO",
            "propagate": False,
        },
        "nilakandi.pull": {
            "handlers": ["file", "console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
