"""Download and save email attachments."""
import os
import re
import requests
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any, Tuple, Optional

from src import settings
from src.logging_conf import logger
from src.missive_client import MissiveClient

GENERIC_EMAIL_DOMAINS = {
    'gmail', 'googlemail', 'outlook', 'hotmail', 'live', 'msn',
    'yahoo', 'aol', 'icloud', 'me', 'mac', 'mail', 'gmx', 'web',
    'posteo', 'protonmail', 'proton', 'tutanota', 'tuta', 'zoho',
    't-online', 'freenet', 'arcor',
}


def extract_sender_label(email: str) -> str:
    """Extract a short sender label from an email address.
    
    For company domains: hostname without TLD (siemens.de → siemens)
    For generic providers: username part (user@gmail.com → user)
    Subdomains are stripped (mail.siemens.de → siemens)
    """
    if not email or '@' not in email:
        return 'unknown'
    
    username, domain = email.rsplit('@', 1)
    parts = domain.lower().split('.')
    
    if len(parts) < 2:
        return domain
    
    # Drop TLD (last part), then check if remaining is a generic provider
    # For multi-part TLDs like .co.uk: parts = [company, co, uk]
    # We want the first meaningful part
    hostname = parts[0] if len(parts) <= 2 else parts[-3] if parts[-2] in ('co', 'com', 'org', 'net', 'ac') else parts[0]
    
    if hostname in GENERIC_EMAIL_DOMAINS:
        label = re.sub(r'[^A-Za-z0-9._-]', '_', username)
        return label[:30] if label else 'unknown'
    
    return hostname


class AttachmentProcessor:
    """Downloads attachments and saves them with proper naming."""
    
    def __init__(self):
        self.storage_paths = settings.ATTACHMENT_STORAGE_PATHS
        self.missive = MissiveClient()
    
    def _find_project_base(self, project_folder: str) -> Optional[Path]:
        """Find which storage path contains the project folder."""
        for base in self.storage_paths:
            if (base / project_folder).is_dir():
                return base
        return None
    
    def process(self, attachment: Dict[str, Any], db=None) -> str:
        """
        Download attachment and return the local path (relative to base).
        
        Path structure: {project}/IBH-INBOX/{yyyymmdd}-{sender}-{subject}/{filename}
        Raises FileNotFoundError if project folder not found in any storage path.
        """
        attachment_id = attachment['missive_attachment_id']
        message_id = attachment['missive_message_id']
        original_filename = attachment['original_filename']
        url = attachment['original_url']
        storage_name = attachment.get('storage_folder_name') or attachment.get('project_name') or 'Unknown'
        delivered_at = attachment.get('delivered_at')
        sender_email = attachment.get('sender_email') or 'unknown'
        email_subject = attachment.get('email_subject') or 'no-subject'
        
        project_folder = self._sanitize_folder(storage_name)
        
        base_path = self._find_project_base(project_folder)
        if not base_path:
            searched = ', '.join(str(p) for p in self.storage_paths)
            raise FileNotFoundError(
                f"Project folder '{project_folder}' not found in any storage path: {searched}"
            )
        
        email_folder = self._build_email_folder(delivered_at, sender_email, email_subject)
        folder_path = base_path / project_folder / "IBH-INBOX" / email_folder
        folder_path.mkdir(parents=True, exist_ok=True)
        local_filename = self._generate_unique_filename(folder_path, original_filename)
        file_path = folder_path / local_filename
        relative_path = f"{project_folder}/IBH-INBOX/{email_folder}/{local_filename}"
        
        if file_path.exists():
            logger.info(f"Already exists: {relative_path}")
            return relative_path
        
        if self._is_url_expired(url):
            logger.info(f"URL expired for {attachment_id}, fetching fresh URL")
            url = self._refresh_url(attachment_id, message_id, db)
        
        logger.info(f"Downloading: {relative_path}")
        content, _ = self._download_with_refresh(url, attachment_id, message_id, db)
        
        # Exclusive create — atomic, never overwrites
        fd = os.open(str(file_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        try:
            os.write(fd, content)
        finally:
            os.close(fd)
        
        logger.info(f"Saved: {relative_path} ({len(content)} bytes)")
        return relative_path
    
    def _build_email_folder(self, delivered_at, sender_email: str, subject: str) -> str:
        """Build email folder name: {yyyymmdd}-{sender}-{subject}"""
        if delivered_at:
            try:
                dt = datetime.fromisoformat(str(delivered_at).replace('Z', '+00:00'))
                date_str = dt.strftime("%Y%m%d")
            except (ValueError, TypeError):
                date_str = "00000000"
        else:
            date_str = "00000000"
        
        sender = extract_sender_label(sender_email)
        subject = self._sanitize_subject(subject)
        
        return f"{date_str}-{sender}-{subject}"
    
    def _sanitize_subject(self, subject: str) -> str:
        """Sanitize email subject for use in folder name."""
        subject = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', subject)
        subject = re.sub(r'[\s_]+', '_', subject)
        subject = subject.strip(' ._')
        max_len = settings.MAX_SUBJECT_LENGTH
        if len(subject) > max_len:
            subject = subject[:max_len].rstrip(' ._')
        return subject if subject else 'no-subject'
    
    def _generate_unique_filename(self, folder_path: Path, original_filename: str) -> str:
        """Generate unique filename, adding _{idx} if collision exists."""
        if '.' in original_filename:
            name, ext = original_filename.rsplit('.', 1)
            ext = ext.lower()
        else:
            name = original_filename
            ext = ''
        
        name = self._sanitize_filename(name)
        
        if ext:
            base_filename = f"{name}.{ext}"
        else:
            base_filename = name
        
        file_path = folder_path / base_filename
        if not file_path.exists():
            return base_filename
        
        idx = 1
        while True:
            indexed_filename = f"{name}_{idx}.{ext}" if ext else f"{name}_{idx}"
            if not (folder_path / indexed_filename).exists():
                return indexed_filename
            idx += 1
    
    def _sanitize_filename(self, name: str) -> str:
        """Sanitize filename component."""
        name = name.replace(' ', '-')
        name = re.sub(r'[^A-Za-z0-9._-]', '_', name)
        name = re.sub(r'[-_]+', '-', name)
        name = name.strip('-_')
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
