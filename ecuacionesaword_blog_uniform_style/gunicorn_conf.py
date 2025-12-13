import multiprocessing
import os

# Render provides PORT. Default to 8000 for local.
bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"

# Conservative default for small instances; can be overridden with WEB_CONCURRENCY.
_default_workers = max(2, (multiprocessing.cpu_count() * 2) + 1)
workers = int(os.getenv("WEB_CONCURRENCY", str(_default_workers)))

worker_class = "uvicorn.workers.UvicornWorker"

# Timeouts: allow enough time for file conversion.
timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", "5"))

accesslog = "-"
errorlog = "-"
loglevel = os.getenv("LOG_LEVEL", "info")
