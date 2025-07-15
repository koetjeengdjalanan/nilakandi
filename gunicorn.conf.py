import multiprocessing
import os

# Server socket
bind = f"0.0.0.0:{os.getenv('PORT', '21180')}"

# Worker processes - reduce to avoid memory pressure
workers = min(multiprocessing.cpu_count() + 1, 5)  # Limit maximum workers
worker_class = "sync"
worker_connections = 1000

# Timeout settings for large file uploads (15 minutes)
timeout = 900
keepalive = 5
graceful_timeout = 30

# Request handling
max_requests = 100  # Reduced to mitigate memory leaks
max_requests_jitter = 50

# Memory and performance
preload_app = False  # Set to False to avoid memory issues with preloading
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


# Add a post-fork hook to ensure proper handling of child processes
def post_fork(server, worker):
    server.log.info("Worker spawned (pid: %s)", worker.pid)

    # Set lower memory limit for worker
    try:
        import resource

        # Limit to 2GB (2 * 1024 * 1024 * 1024)
        resource.setrlimit(resource.RLIMIT_AS, (2 * 1024 * 1024 * 1024, -1))
    except (ImportError, ValueError):
        pass
