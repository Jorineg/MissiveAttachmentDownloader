"""Spool-directory based queue."""
import os
import re
import time
from pathlib import Path
from typing import Optional, List

from src import settings
from src.logging_conf import logger
from src.queue.models import QueueItem


class SpoolQueue:
    """A minimal spool-based queue implementation."""

    def __init__(self):
        self.base_dir: Path = settings.SPOOL_BASE_DIR
        self.missive_dir: Path = settings.SPOOL_MISSIVE_DIR
        self.retry_seconds: int = settings.SPOOL_RETRY_SECONDS

        # Ensure directories exist
        self.missive_dir.mkdir(parents=True, exist_ok=True)

        # Track the currently dequeued file
        self._current_file: Optional[Path] = None
        self._current_item: Optional[QueueItem] = None
        
        # Track batch operations
        self._current_batch_files: List[Path] = []
        self._current_batch_items: List[QueueItem] = []

    def enqueue(self, item: QueueItem) -> None:
        """Enqueue an item by creating a file named with its external ID."""
        try:
            filename = f"{self._safe_id(item.external_id)}.evt"
            path = self.missive_dir / filename

            # Exclusive create to naturally deduplicate
            try:
                with open(path, "x") as f:
                    f.write("")
                logger.info(
                    f"Spool enqueued {item.source}:{item.external_id}",
                    extra={"source": item.source, "event_id": item.external_id}
                )
            except FileExistsError:
                logger.debug(
                    f"Spool item already present {item.source}:{item.external_id}",
                    extra={"source": item.source, "event_id": item.external_id}
                )
        except Exception as e:
            logger.error(f"Failed to spool enqueue: {e}", exc_info=True)
            raise

    def dequeue(self) -> Optional[QueueItem]:
        """Return the next item by scanning for `.evt` or eligible `.retry` files."""
        batch = self.dequeue_batch(max_items=1)
        return batch[0] if batch else None

    def dequeue_batch(self, max_items: int = 10) -> List[QueueItem]:
        """Return up to max_items from the queue."""
        try:
            items = []
            claimed_files = []
            
            # Process ready `.evt` first, then eligible `.retry`
            # Ready files
            evt_files = self._list_files(self.missive_dir, ".evt")
            for file_path in evt_files:
                if len(items) >= max_items:
                    break
                item = self._claim_file(file_path)
                items.append(item)
                claimed_files.append(file_path)

            # Retry files eligible by age
            if len(items) < max_items:
                retry_files = self._list_files(self.missive_dir, ".retry")
                eligible = [p for p in retry_files if self._is_retry_eligible(p)]
                for file_path in eligible:
                    if len(items) >= max_items:
                        break
                    item = self._claim_file(file_path)
                    items.append(item)
                    claimed_files.append(file_path)

            # Store claimed files for batch operations
            if items:
                self._current_batch_files = claimed_files
                self._current_batch_items = items
            
            return items
        except Exception as e:
            logger.error(f"Failed to dequeue batch from spool: {e}", exc_info=True)
            return []

    def mark_processed(self) -> None:
        """Acknowledge current item by deleting its file."""
        if not self._current_file:
            return
        try:
            self._current_file.unlink(missing_ok=True)
        except Exception as e:
            logger.error(f"Failed to delete spool file {self._current_file}: {e}")
        finally:
            self._current_file = None
            self._current_item = None

    def mark_batch_processed(self) -> None:
        """Acknowledge all items in current batch by deleting their files."""
        if not self._current_batch_files:
            return
        for file_path in self._current_batch_files:
            try:
                file_path.unlink(missing_ok=True)
            except Exception as e:
                logger.error(f"Failed to delete spool file {file_path}: {e}")
        self._current_batch_files = []
        self._current_batch_items = []

    def mark_failed(self, item: QueueItem, error: str) -> None:
        """Rename current file to `.retry` and update its mtime to now."""
        if not self._current_file:
            return
        try:
            retry_path = self._current_file.with_suffix(".retry")
            if self._current_file.suffix != ".retry":
                try:
                    os.replace(self._current_file, retry_path)
                except FileNotFoundError:
                    pass
            else:
                retry_path = self._current_file

            try:
                now = time.time()
                os.utime(retry_path, (now, now))
            except Exception:
                pass

            logger.info(
                f"Spool mark_failed; will retry in ~{self.retry_seconds}s: {item.external_id}",
                extra={"source": item.source, "event_id": item.external_id}
            )
        except Exception as e:
            logger.error(f"Failed to mark spool item failed: {e}", exc_info=True)
        finally:
            self._current_file = None
            self._current_item = None

    def size(self) -> int:
        """Approximate number of queued files."""
        try:
            total = len(self._list_files(self.missive_dir, ".evt"))
            total += len(self._list_files(self.missive_dir, ".retry"))
            return total
        except Exception:
            return 0

    def _safe_id(self, value: str) -> str:
        """Make a safe filename from an ID."""
        return re.sub(r"[^A-Za-z0-9._-]", "_", value)[:200]

    def _list_files(self, directory: Path, suffix: str) -> List[Path]:
        """List files with a given suffix."""
        try:
            files = [p for p in directory.iterdir() if p.is_file() and p.suffix == suffix]
            files.sort(key=lambda p: p.stat().st_mtime)
            return files
        except FileNotFoundError:
            return []

    def _is_retry_eligible(self, path: Path) -> bool:
        """Check if a retry file is old enough to retry."""
        try:
            age = time.time() - path.stat().st_mtime
            return age >= self.retry_seconds
        except FileNotFoundError:
            return False

    def _claim_file(self, file_path: Path) -> QueueItem:
        """Claim a file and create a QueueItem."""
        self._current_file = file_path
        external_id = file_path.stem
        item = QueueItem.create(
            source="missive",
            event_type="conversation",
            external_id=external_id,
            payload={}
        )
        self._current_item = item
        return item


