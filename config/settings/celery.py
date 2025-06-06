from __future__ import absolute_import, unicode_literals

from celery import Celery
from config.env import env


import os

from celery import Celery

from config.env import BASE_DIR, env

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.django.local")
env.read_env(os.path.join(BASE_DIR, ".env"))


app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


CELERY_BROKER_URL = env("CELERY_BROKER_URL")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = env("TIME_ZONE", default="UTC")

CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60  # 25 minutes
CELERY_WORKER_MAX_TASKS_PER_CHILD = 128
CELERY_WORKER_PREFETCH_MULTIPLIER = 4

# Broker settings
CELERY_BROKER_URL = env("CELERY_BROKER_URL")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND")
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True  # New setting for Celery 6.0+

# Serialization
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"

# Time and timezone
CELERY_TIMEZONE = env("TIME_ZONE", default="UTC")

# Task settings
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60  # 25 minutes

# Worker settings
CELERY_WORKER_MAX_TASKS_PER_CHILD = 128
CELERY_WORKER_PREFETCH_MULTIPLIER = 4

# Result settings
CELERY_RESULT_EXPIRES = 60 * 60 * 24  # Results expire after 1 day