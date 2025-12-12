"""Minimal Missive API client for fetching fresh attachment URLs."""
import time
from typing import Optional, Dict, Any
import requests

from src import settings
from src.logging_conf import logger


class MissiveClient:
    """Fetches fresh attachment URLs from Missive API."""
    
    def __init__(self):
        self.base_url = "https://public.missiveapp.com/v1"
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {settings.MISSIVE_API_TOKEN}",
            "Accept": "application/json"
        })
    
    def get_fresh_attachment_url(self, message_id: str, attachment_id: str) -> Optional[str]:
        """
        Fetch a message and return the fresh signed URL for a specific attachment.
        
        Args:
            message_id: Missive message ID
            attachment_id: Missive attachment ID
            
        Returns:
            Fresh signed URL or None if not found
        """
        try:
            response = self._request("GET", f"/messages/{message_id}")
            if not response or "messages" not in response:
                return None
            
            message = response["messages"]
            attachments = message.get("attachments", [])
            
            for att in attachments:
                if att.get("id") == attachment_id:
                    url = att.get("url")
                    if url:
                        logger.info(f"Got fresh URL for attachment {attachment_id}")
                        return url
            
            logger.warning(f"Attachment {attachment_id} not found in message {message_id}")
            return None
            
        except Exception as e:
            logger.error(f"Failed to fetch fresh URL for {attachment_id}: {e}")
            return None
    
    def _request(self, method: str, endpoint: str, retry_count: int = 0) -> Optional[Dict[str, Any]]:
        """Make API request with retry logic."""
        url = f"{self.base_url}{endpoint}"
        
        try:
            response = self.session.request(method=method, url=url, timeout=30)
            
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                logger.warning(f"Rate limited. Waiting {retry_after}s...")
                time.sleep(retry_after)
                return self._request(method, endpoint, retry_count)
            
            if response.status_code >= 500 and retry_count < 3:
                wait_time = 2 ** retry_count
                logger.warning(f"Server error {response.status_code}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
                return self._request(method, endpoint, retry_count + 1)
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            if retry_count < 3 and isinstance(e, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
                wait_time = 2 ** retry_count
                time.sleep(wait_time)
                return self._request(method, endpoint, retry_count + 1)
            logger.error(f"Missive API request failed: {e}")
            return None

