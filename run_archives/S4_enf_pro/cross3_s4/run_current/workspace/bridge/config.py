"""Bridge configuration."""
import os

SERVICE_A_BASE_URL = os.getenv("SERVICE_A_URL", "http://localhost:5000")
SERVICE_A_RESOURCE = "events"
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL", "5"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
