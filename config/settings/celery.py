from __future__ import absolute_import, unicode_literals

import os

from celery import Celery
from kombu import Exchange, Queue

from config.env import BASE_DIR, env

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.django.local")
env.read_env(os.path.join(BASE_DIR, ".env"))

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.conf.task_queues = (
    Queue("priority", Exchange("priority"), routing_key="priority"),
    Queue("default", Exchange("default"), routing_key="default"),
)
app.conf.task_default_queue = "default"
app.conf.task_default_exchange = "default"
app.conf.task_default_routing_key = "default"

app.conf.task_routes = {
    "nilakandi.tasks.make_report": {
        "queue": "priority",
        "routing_key": "priority",
    },
}
app.autodiscover_tasks()

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
CELERY_TASK_TIME_LIMIT = 6 * 60 * 60  # 6 hours
CELERY_TASK_SOFT_TIME_LIMIT = 6 * 60 * 60  # 6 hours

# Worker settings
CELERY_WORKER_MAX_TASKS_PER_CHILD = int(
    env("CELERY_WORKER_MAX_TASKS_PER_CHILD", default=128)
)
CELERY_WORKER_PREFETCH_MULTIPLIER = int(
    env("CELERY_WORKER_PREFETCH_MULTIPLIER", default=4)
)

# Result settings
CELERY_RESULT_EXPIRES = 60 * 60 * 24  # Results expire after 1 day
