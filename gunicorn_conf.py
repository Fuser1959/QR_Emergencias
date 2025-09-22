import multiprocessing
import os

bind = f"0.0.0.0:{os.getenv('PORT', '8080')}"
workers = int(os.getenv("WEB_CONCURRENCY", str(max(2, multiprocessing.cpu_count() * 2 + 1))))
threads = int(os.getenv("WEB_THREADS", "2"))
timeout = int(os.getenv("WEB_TIMEOUT", "60"))
keepalive = 30
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("LOG_LEVEL", "info")
