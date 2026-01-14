"""Download and save email attachments."""
import re
import requests
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any, Optional, Tuple

from src import settings
from src.logging_conf import logger
from src.missive_client import MissiveClient


class AttachmentProcessor:
    """Downloads attachments and saves them with proper naming."""
    
    def __init__(self):
        self.storage_path = Path(settings.ATTACHMENT_STORAGE_PATH)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.missive = MissiveClient()
    
    def process(self, attachment: Dict[str, Any], db=None) -> str:
        """
        Download attachment and return the local filename (relative to storage root).
        
        Args:
            attachment: Dict with attachment info including project_name, delivered_at, sender_email
            db: Database instance for updating URL if refreshed
            
        Returns:
            The relative path: {project}/{filename}
            
        Raises:
            Exception on download failure
        """
        attachment_id = attachment['missive_attachment_id']
        message_id = attachment['missive_message_id']
        original_filename = attachment['original_filename']
        url = attachment['original_url']
        project_name = attachment.get('project_name') or 'Unknown'
        delivered_at = attachment.get('delivered_at')
        sender_email = attachment.get('sender_email') or 'unknown'
        
        # Generate filename: {dd-mm-yyyy}_{sender}_{name}_{uuid}.{ext}
        local_filename = self._generate_filename(original_filename, attachment_id, delivered_at, sender_email)
        
        # Project folder (sanitized)
        project_folder = self._sanitize_folder(project_name)
        folder_path = self.storage_path / project_folder
        folder_path.mkdir(parents=True, exist_ok=True)
        
        file_path = folder_path / local_filename
        relative_path = f"{project_folder}/{local_filename}"
        
        # Skip if already exists
        if file_path.exists():
            logger.info(f"Already exists: {relative_path}")
            return relative_path
        
        # Check if URL is expired, refresh preemptively
        if self._is_url_expired(url):
            logger.info(f"URL expired for {attachment_id}, fetching fresh URL")
            url = self._refresh_url(attachment_id, message_id, db)
        
        # Download with retry on 403
        logger.info(f"Downloading: {relative_path}")
        content, url_refreshed = self._download_with_refresh(url, attachment_id, message_id, db)
        
        # Save
        with open(file_path, 'wb') as f:
            f.write(content)
        
        logger.info(f"Saved: {relative_path} ({len(content)} bytes)")
        return relative_path
    
    def _is_url_expired(self, url: str, buffer_seconds: int = 60) -> bool:
        """Check if signed URL is expired or will expire soon."""
        try:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            expires = params.get('Expires', [None])[0]
            if expires:
                expires_ts = int(expires)
                now_ts = int(datetime.now(timezone.utc).timestamp())
                return now_ts >= (expires_ts - buffer_seconds)
        except (ValueError, TypeError):
            pass
        return False
    
    def _refresh_url(self, attachment_id: str, message_id: str, db=None) -> str:
        """Fetch fresh URL from Missive API and update DB."""
        fresh_url = self.missive.get_fresh_attachment_url(message_id, attachment_id)
        if not fresh_url:
            raise Exception(f"Could not get fresh URL for attachment {attachment_id}")
        
        if db:
            db.update_url(attachment_id, fresh_url)
        
        return fresh_url
    
    def _download_with_refresh(self, url: str, attachment_id: str, message_id: str, db=None) -> Tuple[bytes, bool]:
        """Download with automatic URL refresh on 403."""
        try:
            return self._download(url), False
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 403:
                logger.info(f"Got 403 for {attachment_id}, refreshing URL")
                fresh_url = self._refresh_url(attachment_id, message_id, db)
                return self._download(fresh_url), True
            raise
    
    def _generate_filename(self, original_filename: str, attachment_id: str, 
                           delivered_at: Optional[str], sender_email: str) -> str:
        """
        Generate filename: {dd-mm-yyyy}_{sender}_{name}_{uuid}.{ext}
        
        Example: 14-01-2025_john@example.com_Invoice_0001f0d0-0c46-4036-84c7-c493a226a993.pdf
        """
        # Parse delivered_at date
        if delivered_at:
            try:
                dt = datetime.fromisoformat(str(delivered_at).replace('Z', '+00:00'))
                date_str = dt.strftime("%d-%m-%Y")
            except (ValueError, TypeError):
                date_str = "00-00-0000"
        else:
            date_str = "00-00-0000"
        
        # Sanitize sender email (keep @ and .)
        sender = re.sub(r'[^A-Za-z0-9@._-]', '_', sender_email)[:50]
        
        # Split into name and extension
        if '.' in original_filename:
            name, ext = original_filename.rsplit('.', 1)
            ext = ext.lower()
        else:
            name = original_filename
            ext = ''
        
        # Sanitize name
        name = self._sanitize(name)
        
        # Build filename
        base = f"{date_str}_{sender}_{name}_{attachment_id}"
        if ext:
            return f"{base}.{ext}"
        return base
    
    def _sanitize(self, name: str) -> str:
        """Sanitize filename component."""
        # Replace spaces and unsafe chars
        name = name.replace(' ', '-')
        name = re.sub(r'[^A-Za-z0-9._-]', '_', name)
        # Remove multiple underscores/dashes
        name = re.sub(r'[-_]+', '-', name)
        # Trim
        name = name.strip('-_')
        # Limit length
        return name[:100] if name else 'attachment'
    
    def _sanitize_folder(self, name: str) -> str:
        """Sanitize folder name (more permissive than filename)."""
        # Keep spaces, replace only truly unsafe chars
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
        name = name.strip(' .')
        return name[:200] if name else 'Unknown'
    
    def _download(self, url: str) -> bytes:
        """Download file from URL."""
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        return response.content
