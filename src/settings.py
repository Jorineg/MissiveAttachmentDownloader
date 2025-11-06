"""Configuration management for Missive Attachment Downloader."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
(DATA_DIR / "queue").mkdir(exist_ok=True)
(DATA_DIR / "checkpoints").mkdir(exist_ok=True)

# Application settings
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Missive settings
MISSIVE_API_TOKEN = os.getenv("MISSIVE_API_TOKEN")
MISSIVE_PROCESS_AFTER = os.getenv("MISSIVE_PROCESS_AFTER")  # Format: DD.MM.YYYY

# Betterstack settings
BETTERSTACK_SOURCE_TOKEN = os.getenv("BETTERSTACK_SOURCE_TOKEN")

# Attachment storage settings
ATTACHMENT_STORAGE_PATH = os.getenv("ATTACHMENT_STORAGE_PATH")

# Timezone settings
TIMEZONE = os.getenv("TIMEZONE", "Europe/Berlin")

# Polling settings
POLLING_INTERVAL = int(os.getenv("POLLING_INTERVAL", "60"))  # seconds

# Queue settings
QUEUE_DIR = DATA_DIR / "queue"
CHECKPOINT_DIR = DATA_DIR / "checkpoints"
BACKFILL_OVERLAP_SECONDS = int(os.getenv("BACKFILL_OVERLAP_SECONDS", "120"))

# Spool queue settings
SPOOL_BASE_DIR = QUEUE_DIR / "spool"
SPOOL_MISSIVE_DIR = SPOOL_BASE_DIR / "missive"
SPOOL_RETRY_SECONDS = int(os.getenv("SPOOL_RETRY_SECONDS", "60"))


def validate_config():
    """Validate that required configuration is present."""
    errors = []
    
    if not MISSIVE_API_TOKEN:
        errors.append("MISSIVE_API_TOKEN is required")
    
    if not ATTACHMENT_STORAGE_PATH:
        errors.append("ATTACHMENT_STORAGE_PATH is required")
    else:
        # Verify the path is absolute and create it if it doesn't exist
        storage_path = Path(ATTACHMENT_STORAGE_PATH)
        if not storage_path.is_absolute():
            errors.append(f"ATTACHMENT_STORAGE_PATH must be an absolute path, got: {ATTACHMENT_STORAGE_PATH}")
        else:
            try:
                storage_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                errors.append(f"Failed to create ATTACHMENT_STORAGE_PATH: {e}")
    
    if errors:
        raise ValueError("Configuration errors:\n  " + "\n  ".join(errors))


if __name__ == "__main__":
    try:
        validate_config()
        print("✓ Configuration is valid")
    except ValueError as e:
        print(f"✗ {e}")

