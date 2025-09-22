import os

# Bind al puerto que da Railway
bind = f"0.0.0.0:{os.getenv('PORT', '8080')}"

# Perfil ultra liviano por defecto (puede subirse luego)
workers = int(os.getenv("WEB_CONCURRENCY", "1"))   # 1 worker
threads = int(os.getenv("WEB_THREADS", "1"))        # 1 thread
worker_class = os.getenv("WEB_WORKER_CLASS", "sync")

# Estabilidad (evita fugas de memoria a largo plazo)
max_requests = int(os.getenv("WEB_MAX_REQUESTS", "200"))
max_requests_jitter = int(os.getenv("WEB_MAX_REQUESTS_JITTER", "50"))

# Timeouts / logs
timeout = int(os.getenv("WEB_TIMEOUT", "60"))
keepalive = 30
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("LOG_LEVEL", "info")
