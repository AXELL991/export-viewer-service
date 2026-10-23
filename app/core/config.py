"""Core configuration for export‑viewer‑service.
All settings are read from environment variables (Twelve‑Factor).
"""
import os

# Logging level (default INFO)
LOGLEVEL = os.getenv("LOGLEVEL", "INFO")

# URLs of downstream services (must include scheme and port)
EXTRACTOR_URL = os.getenv("EXTRACTOR_URL", "http://pdf-extractor-service:8000")
CRUD_URL = os.getenv("CRUD_URL", "http://document-crud-service:8000")

# HTTP timeout (seconds) for calls to downstream services
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "5"))

# Retry configuration (max attempts)
RETRY_ATTEMPTS = int(os.getenv("RETRY_ATTEMPTS", "3"))

