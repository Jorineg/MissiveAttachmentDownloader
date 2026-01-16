"""Configuration for Missive Attachment Downloader."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
BETTERSTACK_SOURCE_TOKEN = os.getenv("BETTERSTACK_SOURCE_TOKEN")
BETTERSTACK_INGEST_HOST = os.getenv("BETTERSTACK_INGEST_HOST")

# PostgREST API (database operations)
# MAD_SERVICE_SECRET is used as X-API-Key header for PostgREST proxy auth
# (same secret is also the mad_downloader DB role password on server side)
POSTGREST_URL = os.getenv("POSTGREST_URL")
MAD_SERVICE_SECRET = os.getenv("MAD_SERVICE_SECRET")

# Missive API (for refreshing expired signed URLs)
MISSIVE_API_TOKEN = os.getenv("MISSIVE_API_TOKEN")

# Attachment storage
ATTACHMENT_STORAGE_PATH = os.getenv("ATTACHMENT_STORAGE_PATH")

# Worker settings
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "5"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "10"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))

# Skip filter: images below these thresholds are skipped
SKIP_IMAGE_MIN_SIZE = int(os.getenv("SKIP_IMAGE_MIN_SIZE", "25000"))  # 25KB
SKIP_IMAGE_MIN_DIMENSION = int(os.getenv("SKIP_IMAGE_MIN_DIMENSION", "360"))  # 360px

# Skip outgoing emails
SKIP_SENDER_DOMAINS = [d.strip().lower() for d in os.getenv("SKIP_SENDER_DOMAINS", "").split(",") if d.strip()]

# Max subject length in folder name
MAX_SUBJECT_LENGTH = int(os.getenv("MAX_SUBJECT_LENGTH", "50"))


def validate_config():
    """Validate required configuration."""
    errors = []
    
    if not POSTGREST_URL:
        errors.append("POSTGREST_URL is required")
    if not MAD_SERVICE_SECRET:
        errors.append("MAD_SERVICE_SECRET is required")
    if not MISSIVE_API_TOKEN:
        errors.append("MISSIVE_API_TOKEN is required")
    
    if not ATTACHMENT_STORAGE_PATH:
        errors.append("ATTACHMENT_STORAGE_PATH is required")
    else:
        storage_path = Path(ATTACHMENT_STORAGE_PATH)
        if not storage_path.is_absolute():
            errors.append(f"ATTACHMENT_STORAGE_PATH must be absolute: {ATTACHMENT_STORAGE_PATH}")
        else:
            try:
                storage_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                errors.append(f"Cannot create ATTACHMENT_STORAGE_PATH: {e}")
    
    if errors:
        raise ValueError("Config errors:\n  " + "\n  ".join(errors))
