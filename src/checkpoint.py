"""Checkpoint management for tracking sync progress."""
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src import settings
from src.logging_conf import logger


class CheckpointManager:
    """Manages checkpoints for tracking sync progress."""
    
    def __init__(self):
        self.checkpoint_file: Path = settings.CHECKPOINT_DIR / "missive.json"
        self.checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
    
    def get_last_sync_time(self) -> datetime:
        """
        Get the last sync time from checkpoint.
        
        Returns:
            Last sync datetime with overlap applied, or default based on MISSIVE_PROCESS_AFTER
        """
        try:
            if self.checkpoint_file.exists():
                with open(self.checkpoint_file, "r") as f:
                    data = json.load(f)
                    last_sync = datetime.fromisoformat(data.get("last_sync"))
                    # Apply overlap to prevent missing events
                    overlap = timedelta(seconds=settings.BACKFILL_OVERLAP_SECONDS)
                    return last_sync - overlap
        except Exception as e:
            logger.warning(f"Failed to read checkpoint: {e}")
        
        # First run: use MISSIVE_PROCESS_AFTER or default to 30 days ago
        if settings.MISSIVE_PROCESS_AFTER:
            try:
                # Parse DD.MM.YYYY format
                day, month, year = settings.MISSIVE_PROCESS_AFTER.split(".")
                return datetime(int(year), int(month), int(day))
            except Exception as e:
                logger.error(f"Failed to parse MISSIVE_PROCESS_AFTER: {e}")
        
        # Default to 30 days ago
        return datetime.now() - timedelta(days=30)
    
    def save_sync_time(self, sync_time: datetime) -> None:
        """Save the sync time to checkpoint."""
        try:
            data = {
                "last_sync": sync_time.isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            with open(self.checkpoint_file, "w") as f:
                json.dump(data, f, indent=2)
            logger.debug(f"Saved checkpoint: {sync_time.isoformat()}")
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}", exc_info=True)


