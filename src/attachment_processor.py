"""Process attachments from Missive messages."""
import re
from pathlib import Path
from typing import Dict, Any, Optional

from src import settings
from src.logging_conf import logger
from src.missive_client import MissiveClient


class AttachmentProcessor:
    """Handles downloading and naming attachments."""
    
    def __init__(self, client: MissiveClient):
        self.client = client
        self.storage_path = Path(settings.ATTACHMENT_STORAGE_PATH)
        self.storage_path.mkdir(parents=True, exist_ok=True)
    
    def process_conversation(self, conversation_id: str) -> None:
        """Process all attachments in a conversation."""
        try:
            # Get all messages in the conversation
            messages = self.client.get_conversation_messages(conversation_id)
            
            if not messages:
                logger.debug(f"No messages found in conversation {conversation_id}")
                return
            
            for message in messages:
                self.process_message(message)
        
        except Exception as e:
            logger.error(f"Error processing conversation {conversation_id}: {e}", exc_info=True)
            raise
    
    def process_message(self, message: Dict[str, Any]) -> None:
        """Process all attachments in a message."""
        try:
            # Get message ID and fetch fresh message data to get current attachment URLs
            message_id = message.get("id")
            if message_id:
                # Fetch fresh message details to get valid attachment URLs
                full_message = self.client.get_message(message_id)
                if full_message:
                    message = full_message
            
            attachments = message.get("attachments", [])
            
            if not attachments:
                return
            
            # Parse sender info (from_field can be dict or string)
            from_field = message.get("from_field", message.get("from", {}))
            from_address = "unknown@unknown.com"
            if isinstance(from_field, dict):
                from_address = from_field.get("address") or from_field.get("email", "unknown@unknown.com")
            elif isinstance(from_field, str):
                from_address = from_field
            
            # Parse recipient info (to_fields is the correct field name, with fallback to to)
            to_fields = message.get("to_fields", message.get("to", []))
            to_address = "unknown@unknown.com"
            
            if to_fields and len(to_fields) > 0:
                if isinstance(to_fields[0], dict):
                    to_address = to_fields[0].get("address") or to_fields[0].get("email", "unknown@unknown.com")
                elif isinstance(to_fields[0], str):
                    to_address = to_fields[0]
            
            # Debug: log structure if to_address is still unknown
            if to_address == "unknown@unknown.com":
                logger.debug(f"Message {message_id} has unknown recipient. to_fields: {to_fields}")
            
            # Process each attachment
            for attachment in attachments:
                self.download_attachment(
                    attachment=attachment,
                    from_address=from_address,
                    to_address=to_address
                )
        
        except Exception as e:
            logger.error(f"Error processing message attachments: {e}", exc_info=True)
            raise
    
    def download_attachment(
        self,
        attachment: Dict[str, Any],
        from_address: str,
        to_address: str
    ) -> Optional[Path]:
        """Download and save an attachment with the proper filename."""
        try:
            # Check for both 'download_url' and 'url' fields (Missive uses 'url')
            attachment_url = attachment.get("download_url") or attachment.get("url")
            attachment_name = attachment.get("filename") or attachment.get("name", "unknown")
            
            if not attachment_url:
                logger.warning(f"No download URL for attachment: {attachment_name}")
                logger.debug(f"Attachment data keys: {list(attachment.keys())}")
                return None
            
            # Generate filename
            filename = self.generate_filename(
                from_address=from_address,
                to_address=to_address,
                attachment_name=attachment_name
            )
            
            file_path = self.storage_path / filename
            
            # Skip if file already exists
            if file_path.exists():
                logger.info(f"Attachment already exists, skipping: {filename}")
                return file_path
            
            # Download attachment
            logger.info(f"Downloading attachment: {filename}")
            content = self.client.download_attachment(attachment_url)
            
            if content is None:
                logger.error(f"Failed to download attachment: {attachment_name}")
                return None
            
            # Save to file
            with open(file_path, "wb") as f:
                f.write(content)
            
            logger.info(f"Successfully saved attachment: {filename} ({len(content)} bytes)")
            return file_path
        
        except Exception as e:
            logger.error(f"Error downloading attachment: {e}", exc_info=True)
            raise
    
    def generate_filename(
        self,
        from_address: str,
        to_address: str,
        attachment_name: str
    ) -> str:
        """
        Generate filename in format:
        FROM_email_at_domain.tld_TO_email_at_domain.tld_NAME_attachmentname
        """
        # Convert email addresses to safe format
        from_email_safe = self._email_to_safe_format(from_address)
        to_email_safe = self._email_to_safe_format(to_address)
        
        # Clean attachment name
        attachment_name_safe = self._clean_filename(attachment_name)
        
        # Build filename without names, only emails
        filename = f"FROM_{from_email_safe}_TO_{to_email_safe}_NAME_{attachment_name_safe}"
        
        # Ensure reasonable length (Windows has 260 char path limit)
        if len(filename) > 200:
            # Truncate the emails but keep the attachment name intact
            max_email_len = (200 - len(attachment_name_safe) - 20) // 2  # 20 for prefixes
            from_email_safe = from_email_safe[:max_email_len]
            to_email_safe = to_email_safe[:max_email_len]
            filename = f"FROM_{from_email_safe}_TO_{to_email_safe}_NAME_{attachment_name_safe}"
        
        return filename
    
    def _email_to_safe_format(self, email: str) -> str:
        """Convert email@domain.com to email_at_domain.com format."""
        if not email:
            return "unknown_at_unknown.com"
        # Replace @ with _at_
        safe_email = email.replace("@", "_at_")
        # Remove any other unsafe characters
        safe_email = re.sub(r"[^A-Za-z0-9._-]", "_", safe_email)
        return safe_email
    
    def _clean_filename(self, filename: str) -> str:
        """Clean an attachment filename."""
        # Replace spaces with underscores
        clean = filename.replace(" ", "_")
        # Remove unsafe characters but preserve file extension
        clean = re.sub(r"[^A-Za-z0-9._-]", "_", clean)
        # Remove multiple consecutive underscores
        clean = re.sub(r"_+", "_", clean)
        return clean


