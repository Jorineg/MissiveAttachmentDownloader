"""Logging configuration with Betterstack support."""
import logging
import sys
from logging.handlers import RotatingFileHandler
from logtail import LogtailHandler

from src import settings


def setup_logging():
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL, logging.INFO))
    root_logger.handlers = []

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, settings.LOG_LEVEL, logging.INFO))
    console_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # File handler
    log_file = settings.LOGS_DIR / "app.log"
    file_handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(console_formatter)
    root_logger.addHandler(file_handler)

    # BetterStack handler
    if settings.BETTERSTACK_SOURCE_TOKEN:
        try:
            handler_kwargs = {"source_token": settings.BETTERSTACK_SOURCE_TOKEN}
            if settings.BETTERSTACK_INGEST_HOST:
                handler_kwargs["host"] = settings.BETTERSTACK_INGEST_HOST
            betterstack_handler = LogtailHandler(**handler_kwargs)
            betterstack_handler.setLevel(logging.DEBUG)
            betterstack_handler.setFormatter(console_formatter)
            root_logger.addHandler(betterstack_handler)
            host_info = settings.BETTERSTACK_INGEST_HOST or "default (in.logs.betterstack.com)"
            root_logger.info(f"BetterStack logging enabled (host: {host_info})")
        except Exception as e:
            root_logger.warning(f"Failed to initialize BetterStack logging: {e}")

    logging.getLogger("urllib3").setLevel(logging.WARNING)
    return root_logger


logger = setup_logging()
