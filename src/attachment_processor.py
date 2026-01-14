"""Download and save email attachments."""
import re
import requests
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any, Tuple

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
        Download attachment and return the local path (relative to storage root).
        
        Path structure: {project}/IBH-INBOX/{yyyymmdd}-{sender}-{subject}/{filename}(_{idx}).{ext}
        """
        attachment_id = attachment['missive_attachment_id']
        message_id = attachment['missive_message_id']
        original_filename = attachment['original_filename']
        url = attachment['original_url']
        project_name = attachment.get('project_name') or 'Unknown'
        delivered_at = attachment.get('delivered_at')
        sender_email = attachment.get('sender_email') or 'unknown'
        email_subject = attachment.get('email_subject') or 'no-subject'
        
        # Build folder path: {project}/IBH-INBOX/{yyyymmdd}-{sender}-{subject}
        project_folder = self._sanitize_folder(project_name)
        email_folder = self._build_email_folder(delivered_at, sender_email, email_subject)
        folder_path = self.storage_path / project_folder / "IBH-INBOX" / email_folder
        folder_path.mkdir(parents=True, exist_ok=True)
        
        # Generate filename with collision handling
        local_filename = self._generate_unique_filename(folder_path, original_filename)
        file_path = folder_path / local_filename
        relative_path = f"{project_folder}/IBH-INBOX/{email_folder}/{local_filename}"
        
        # Skip if already exists (exact match)
        if file_path.exists():
            logger.info(f"Already exists: {relative_path}")
            return relative_path
        
        # Check if URL is expired, refresh preemptively
        if self._is_url_expired(url):
            logger.info(f"URL expired for {attachment_id}, fetching fresh URL")
            url = self._refresh_url(attachment_id, message_id, db)
        
        # Download with retry on 403
        logger.info(f"Downloading: {relative_path}")
        content, _ = self._download_with_refresh(url, attachment_id, message_id, db)
        
        # Save
        with open(file_path, 'wb') as f:
            f.write(content)
        
        logger.info(f"Saved: {relative_path} ({len(content)} bytes)")
        return relative_path
    
    def _build_email_folder(self, delivered_at, sender_email: str, subject: str) -> str:
        """Build email folder name: {yyyymmdd}-{sender}-{subject}"""
        # Parse date
        if delivered_at:
            try:
                dt = datetime.fromisoformat(str(delivered_at).replace('Z', '+00:00'))
                date_str = dt.strftime("%Y%m%d")
            except (ValueError, TypeError):
                date_str = "00000000"
        else:
            date_str = "00000000"
        
        # Sanitize sender (extract just the email, keep simple)
        sender = re.sub(r'[^A-Za-z0-9@._-]', '_', sender_email)[:50]
        
        # Sanitize subject with max length
        subject = self._sanitize_subject(subject)
        
        return f"{date_str}-{sender}-{subject}"
    
    def _sanitize_subject(self, subject: str) -> str:
        """Sanitize email subject for use in folder name."""
        # Replace unsafe chars
        subject = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', subject)
        # Replace multiple spaces/underscores
        subject = re.sub(r'[\s_]+', '_', subject)
        # Trim
        subject = subject.strip(' ._')
        # Limit length
        max_len = settings.MAX_SUBJECT_LENGTH
        if len(subject) > max_len:
            subject = subject[:max_len].rstrip(' ._')
        return subject if subject else 'no-subject'
    
    def _generate_unique_filename(self, folder_path: Path, original_filename: str) -> str:
        """Generate unique filename, adding _{idx} if collision exists."""
        # Split name and extension
        if '.' in original_filename:
            name, ext = original_filename.rsplit('.', 1)
            ext = ext.lower()
        else:
            name = original_filename
            ext = ''
        
        # Sanitize name
        name = self._sanitize_filename(name)
        
        # Build base filename
        if ext:
            base_filename = f"{name}.{ext}"
        else:
            base_filename = name
        
        # Check for collision
        file_path = folder_path / base_filename
        if not file_path.exists():
            return base_filename
        
        # Add index suffix
        idx = 1
        while True:
            if ext:
                indexed_filename = f"{name}_{idx}.{ext}"
            else:
                indexed_filename = f"{name}_{idx}"
            
            if not (folder_path / indexed_filename).exists():
                return indexed_filename
            idx += 1
    
    def _sanitize_filename(self, name: str) -> str:
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
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
        name = name.strip(' .')
        return name[:200] if name else 'Unknown'
    
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
    
    def _download(self, url: str) -> bytes:
        """Download file from URL."""
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        return response.content
