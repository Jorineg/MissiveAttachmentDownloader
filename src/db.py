"""Database operations for email attachment downloads."""
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import List, Optional, Dict, Any
from contextlib import contextmanager

from src import settings
from src.logging_conf import logger


class Database:
    """Database connection and operations for attachment downloads."""
    
    def __init__(self):
        self._conn = None
    
    @property
    def conn(self):
        """Get or create database connection."""
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(settings.DATABASE_URL)
        return self._conn
    
    def close(self):
        """Close database connection."""
        if self._conn and not self._conn.closed:
            self._conn.close()
            self._conn = None
    
    @contextmanager
    def cursor(self):
        """Context manager for cursor with auto-commit/rollback."""
        cur = self.conn.cursor(cursor_factory=RealDictCursor)
        try:
            yield cur
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        finally:
            cur.close()
    
    def get_pending_attachments(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch pending attachments for download."""
        with self.cursor() as cur:
            cur.execute("""
                SELECT 
                    missive_attachment_id,
                    missive_message_id,
                    original_filename,
                    original_url,
                    file_size,
                    retry_count
                FROM email_attachment_files
                WHERE status = 'pending'
                  AND (retry_count < %s)
                ORDER BY created_at ASC
                LIMIT %s
            """, (settings.MAX_RETRIES, limit))
            return cur.fetchall()
    
    def mark_downloading(self, attachment_id: str) -> bool:
        """Mark attachment as currently downloading (atomic claim)."""
        with self.cursor() as cur:
            cur.execute("""
                UPDATE email_attachment_files
                SET status = 'downloading', updated_at = NOW()
                WHERE missive_attachment_id = %s AND status = 'pending'
                RETURNING missive_attachment_id
            """, (attachment_id,))
            return cur.fetchone() is not None
    
    def mark_completed(self, attachment_id: str, local_filename: str) -> None:
        """Mark attachment as successfully downloaded."""
        with self.cursor() as cur:
            cur.execute("""
                UPDATE email_attachment_files
                SET status = 'completed',
                    local_filename = %s,
                    downloaded_at = NOW(),
                    updated_at = NOW(),
                    error_message = NULL
                WHERE missive_attachment_id = %s
            """, (local_filename, attachment_id))
        logger.info(f"Completed: {local_filename}")
    
    def mark_failed(self, attachment_id: str, error: str) -> None:
        """Mark attachment as failed, increment retry count."""
        with self.cursor() as cur:
            cur.execute("""
                UPDATE email_attachment_files
                SET status = 'pending',
                    retry_count = retry_count + 1,
                    error_message = %s,
                    updated_at = NOW()
                WHERE missive_attachment_id = %s
            """, (error, attachment_id))
            
            # Check if max retries exceeded
            cur.execute("""
                UPDATE email_attachment_files
                SET status = 'failed'
                WHERE missive_attachment_id = %s AND retry_count >= %s
            """, (attachment_id, settings.MAX_RETRIES))
        logger.warning(f"Failed: {attachment_id} - {error}")
    
    def reset_stuck_downloads(self, minutes: int = 30) -> int:
        """Reset downloads stuck in 'downloading' state."""
        with self.cursor() as cur:
            cur.execute("""
                UPDATE email_attachment_files
                SET status = 'pending', updated_at = NOW()
                WHERE status = 'downloading'
                  AND updated_at < NOW() - INTERVAL '%s minutes'
                RETURNING missive_attachment_id
            """, (minutes,))
            count = len(cur.fetchall())
            if count > 0:
                logger.warning(f"Reset {count} stuck downloads")
            return count

