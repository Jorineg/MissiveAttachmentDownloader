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

# Database connection
DATABASE_URL = os.getenv("DATABASE_URL")

# Attachment storage
ATTACHMENT_STORAGE_PATH = os.getenv("ATTACHMENT_STORAGE_PATH")

# Worker settings
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "5"))  # seconds between DB polls
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "10"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))


def validate_config():
    """Validate required configuration."""
    errors = []
    
    if not DATABASE_URL:
        errors.append("DATABASE_URL is required")
    
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
