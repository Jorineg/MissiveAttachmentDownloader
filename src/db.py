"""Database operations via Supabase REST API."""
import httpx
from typing import List, Dict, Any
from datetime import datetime, timezone, timedelta

from src import settings
from src.logging_conf import logger


class Database:
    """REST client for email attachment downloads."""
    
    def __init__(self):
        self.base_url = f"{settings.SUPABASE_URL}/rest/v1"
        self.headers = {
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
            "apikey": settings.SUPABASE_SERVICE_KEY,
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        self._client = httpx.Client(timeout=30.0)
    
    def close(self):
        """Close HTTP client."""
        self._client.close()
    
    def get_pending_attachments(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch pending attachments for download."""
        try:
            url = f"{self.base_url}/email_attachment_files"
            params = {
                "select": "missive_attachment_id,missive_message_id,original_filename,original_url,file_size,width,height,media_type,sub_type,retry_count",
                "status": "eq.pending",
                "retry_count": f"lt.{settings.MAX_RETRIES}",
                "order": "created_at.asc",
                "limit": str(limit),
            }
            response = self._client.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch pending attachments: {e}")
            return []
    
    def mark_downloading(self, attachment_id: str) -> bool:
        """Mark attachment as currently downloading (claim it)."""
        try:
            url = f"{self.base_url}/email_attachment_files"
            params = {
                "missive_attachment_id": f"eq.{attachment_id}",
                "status": "eq.pending",
            }
            now = datetime.now(timezone.utc).isoformat()
            data = {"status": "downloading", "updated_at": now}
            
            response = self._client.patch(url, headers=self.headers, params=params, json=data)
            response.raise_for_status()
            result = response.json()
            return len(result) > 0
        except Exception as e:
            logger.error(f"Failed to mark downloading {attachment_id}: {e}")
            return False
    
    def mark_completed(self, attachment_id: str, local_filename: str) -> None:
        """Mark attachment as successfully downloaded."""
        try:
            url = f"{self.base_url}/email_attachment_files"
            params = {"missive_attachment_id": f"eq.{attachment_id}"}
            now = datetime.now(timezone.utc).isoformat()
            data = {
                "status": "completed",
                "local_filename": local_filename,
                "downloaded_at": now,
                "updated_at": now,
                "error_message": None,
            }
            response = self._client.patch(url, headers=self.headers, params=params, json=data)
            response.raise_for_status()
            logger.info(f"Completed: {local_filename}")
        except Exception as e:
            logger.error(f"Failed to mark completed {attachment_id}: {e}")
    
    def mark_skipped(self, attachment_id: str, reason: str) -> None:
        """Mark attachment as skipped (not worth downloading)."""
        try:
            url = f"{self.base_url}/email_attachment_files"
            params = {"missive_attachment_id": f"eq.{attachment_id}"}
            now = datetime.now(timezone.utc).isoformat()
            data = {
                "status": "skipped",
                "skip_reason": reason[:200],
                "updated_at": now,
            }
            response = self._client.patch(url, headers=self.headers, params=params, json=data)
            response.raise_for_status()
            logger.info(f"Skipped: {attachment_id} - {reason}")
        except Exception as e:
            logger.error(f"Failed to mark skipped {attachment_id}: {e}")
    
    def update_url(self, attachment_id: str, new_url: str) -> None:
        """Update the download URL with a fresh signed URL."""
        try:
            url = f"{self.base_url}/email_attachment_files"
            params = {"missive_attachment_id": f"eq.{attachment_id}"}
            now = datetime.now(timezone.utc).isoformat()
            data = {"original_url": new_url, "updated_at": now}
            response = self._client.patch(url, headers=self.headers, params=params, json=data)
            response.raise_for_status()
            logger.debug(f"Updated URL for {attachment_id}")
        except Exception as e:
            logger.error(f"Failed to update URL for {attachment_id}: {e}")
    
    def mark_failed(self, attachment_id: str, error: str) -> None:
        """Mark attachment as failed, increment retry count."""
        try:
            # First get current retry_count
            url = f"{self.base_url}/email_attachment_files"
            params = {
                "missive_attachment_id": f"eq.{attachment_id}",
                "select": "retry_count",
            }
            response = self._client.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            result = response.json()
            
            if not result:
                logger.warning(f"Attachment not found: {attachment_id}")
                return
            
            current_retry = result[0].get("retry_count", 0)
            new_retry = current_retry + 1
            
            # Determine status based on retry count
            status = "failed" if new_retry >= settings.MAX_RETRIES else "pending"
            
            now = datetime.now(timezone.utc).isoformat()
            data = {
                "status": status,
                "retry_count": new_retry,
                "error_message": error[:500],
                "updated_at": now,
            }
            
            response = self._client.patch(
                url, headers=self.headers,
                params={"missive_attachment_id": f"eq.{attachment_id}"},
                json=data
            )
            response.raise_for_status()
            logger.warning(f"Failed: {attachment_id} - {error}")
        except Exception as e:
            logger.error(f"Failed to mark failed {attachment_id}: {e}")
    
    def reset_stuck_downloads(self, minutes: int = 30) -> int:
        """Reset downloads stuck in 'downloading' state."""
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
            url = f"{self.base_url}/email_attachment_files"
            params = {
                "status": "eq.downloading",
                "updated_at": f"lt.{cutoff}",
            }
            now = datetime.now(timezone.utc).isoformat()
            data = {"status": "pending", "updated_at": now}
            
            response = self._client.patch(url, headers=self.headers, params=params, json=data)
            response.raise_for_status()
            result = response.json()
            count = len(result)
            
            if count > 0:
                logger.warning(f"Reset {count} stuck downloads")
            return count
        except Exception as e:
            logger.error(f"Failed to reset stuck downloads: {e}")
            return 0
