# Gunicorn configuration file
import os

# Timeout in seconds
# Default is 30, increasing to 120 to handle long-running AI generation tasks
timeout = 120

# Worker class
# Using default 'sync' worker. For heavy AI tasks, 'gthread' might be better but 'sync' is simpler.
# Worker class
# Using 'gthread' to allow concurrency (multiple requests) within a single worker process.
# This saves memory compared to multiple workers.
worker_class = 'gthread'

# Number of workers
# Render sets WEB_CONCURRENCY, defaulting to 2 if not set
# Keep at 1 to minimize memory footprint (Render Starter is 512MB)
workers = 1

# Threads per worker
# Allow 4 simultaneous requests per worker. Good for I/O bound tasks like AI/DB waits.
threads = 4

# Worker recycle (メモリリーク防止)
# 各ワーカーを500リクエスト処理後に自動再起動してメモリをクリア (1000 -> 500 へ変更)
max_requests = 500
# ランダムジッター（100リクエストの揺らぎを持たせる）
max_requests_jitter = 100

# Bind address
bind = "0.0.0.0:" + os.environ.get("PORT", "10000")

# Logging
accesslog = '-'
errorlog = '-'
loglevel = 'info'

