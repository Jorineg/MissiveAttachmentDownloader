"""Logging configuration with Betterstack support."""
import logging
import sys
from pathlib import Path
from logtail import LogtailHandler

from src import settings

# Create logger
logger = logging.getLogger("missive_attachment_downloader")
logger.setLevel(getattr(logging, settings.LOG_LEVEL, logging.INFO))

# Create formatters
detailed_formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(detailed_formatter)
logger.addHandler(console_handler)

# File handler
log_file = settings.LOGS_DIR / "app.log"
file_handler = logging.FileHandler(log_file)
file_handler.setFormatter(detailed_formatter)
logger.addHandler(file_handler)

# Betterstack handler (if configured)
if settings.BETTERSTACK_SOURCE_TOKEN:
    try:
        betterstack_handler = LogtailHandler(source_token=settings.BETTERSTACK_SOURCE_TOKEN)
        betterstack_handler.setFormatter(detailed_formatter)
        logger.addHandler(betterstack_handler)
        logger.info("Betterstack logging enabled")
    except Exception as e:
        logger.warning(f"Failed to initialize Betterstack logging: {e}")
else:
    logger.info("Betterstack logging not configured (BETTERSTACK_SOURCE_TOKEN not set)")

# Disable propagation to root logger
logger.propagate = False

