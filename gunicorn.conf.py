# Gunicorn configuration file
import os

# Timeout in seconds
# Default is 30, increasing to 120 to handle long-running AI generation tasks
timeout = 120

# Worker class
# Using default 'sync' worker. For heavy AI tasks, 'gthread' might be better but 'sync' is simpler.
worker_class = 'sync'

# Number of workers
# Render sets WEB_CONCURRENCY, defaulting to 2 if not set
workers = int(os.environ.get('WEB_CONCURRENCY', 2))

# Threads per worker
# If using 'gthread' worker class, this would need to be set > 1
threads = 1

# Bind address
bind = "0.0.0.0:" + os.environ.get("PORT", "10000")

# Logging
accesslog = '-'
errorlog = '-'
loglevel = 'info'
