import multiprocessing
import os

# Server socket
bind = f"0.0.0.0:{os.getenv('PORT', '21180')}"

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000

# Timeout settings for large file uploads (15 minutes)
timeout = 900  # 15 minutes
keepalive = 5
graceful_timeout = 30

# Request handling
max_requests = 1000
max_requests_jitter = 100

# Memory and performance
preload_app = True
worker_tmp_dir = "/dev/shm"

# Logging
loglevel = "info"
accesslog = "-"
errorlog = "-"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "nilakandi-gunicorn"

# Limits for large file uploads
limit_request_line = 8190
limit_request_fields = 100
limit_request_field_size = 16384
