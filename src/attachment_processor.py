"""Download and save email attachments."""
import re
import requests
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

from src import settings
from src.logging_conf import logger


class AttachmentProcessor:
    """Downloads attachments and saves them with proper naming."""
    
    def __init__(self):
        self.storage_path = Path(settings.ATTACHMENT_STORAGE_PATH)
        self.storage_path.mkdir(parents=True, exist_ok=True)
    
    def process(self, attachment: Dict[str, Any]) -> str:
        """
        Download attachment and return the local filename.
        
        Args:
            attachment: Dict with missive_attachment_id, original_filename, original_url
            
        Returns:
            The local_filename (just filename, not full path)
            
        Raises:
            Exception on download failure
        """
        attachment_id = attachment['missive_attachment_id']
        original_filename = attachment['original_filename']
        url = attachment['original_url']
        
        # Generate unique filename: {name}_{attachment_id}.{ext}
        local_filename = self._generate_filename(original_filename, attachment_id)
        
        # Get monthly folder: YYYY-MM
        month_folder = datetime.now().strftime("%Y-%m")
        folder_path = self.storage_path / month_folder
        folder_path.mkdir(parents=True, exist_ok=True)
        
        file_path = folder_path / local_filename
        
        # Skip if already exists
        if file_path.exists():
            logger.info(f"Already exists: {local_filename}")
            return local_filename
        
        # Download
        logger.info(f"Downloading: {local_filename}")
        content = self._download(url)
        
        # Save
        with open(file_path, 'wb') as f:
            f.write(content)
        
        logger.info(f"Saved: {local_filename} ({len(content)} bytes)")
        return local_filename
    
    def _generate_filename(self, original_filename: str, attachment_id: str) -> str:
        """
        Generate filename: {sanitized_name}_{attachment_id}.{ext}
        
        Example: Invoice-December_0001f0d0-0c46-4036-84c7-c493a226a993.pdf
        """
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
        if ext:
            return f"{name}_{attachment_id}.{ext}"
        return f"{name}_{attachment_id}"
    
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
    
    def _download(self, url: str) -> bytes:
        """Download file from URL."""
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        return response.content
