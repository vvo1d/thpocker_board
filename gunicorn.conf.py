bind = "0.0.0.0:8000"
workers = 1  # Для этого приложения нужен только 1 worker из-за in-memory state
worker_class = "sync"
timeout = 120