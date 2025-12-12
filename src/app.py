"""Main application - polls DB for pending attachments and downloads them."""
import signal
import sys
import time

from src.logging_conf import logger
from src import settings
from src.db import Database
from src.attachment_processor import AttachmentProcessor


class Application:
    """Main application that polls DB and processes attachments."""
    
    def __init__(self):
        self.db = Database()
        self.processor = AttachmentProcessor()
        self.running = False
    
    def start(self):
        """Start the application."""
        logger.info("=" * 50)
        logger.info("Missive Attachment Downloader")
        logger.info("=" * 50)
        logger.info(f"Storage: {settings.ATTACHMENT_STORAGE_PATH}")
        logger.info(f"Poll interval: {settings.POLL_INTERVAL}s")
        logger.info("=" * 50)
        
        settings.validate_config()
        self.running = True
        logger.info("Started - watching for pending attachments")
    
    def stop(self):
        """Stop the application."""
        if not self.running:
            return
        self.running = False
        self.db.close()
        logger.info("Stopped")
    
    def run(self):
        """Main loop."""
        self.start()
        
        # Reset any stuck downloads on startup
        self.db.reset_stuck_downloads()
        
        while self.running:
            try:
                processed = self._process_batch()
                
                # If no work, sleep before next poll
                if not processed:
                    time.sleep(settings.POLL_INTERVAL)
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                time.sleep(5)
        
        self.stop()
    
    # Always skip these (media_type, sub_type) combinations
    SKIP_TYPES = {
        ('application', 'pgp-signature'),
        ('application', 'pkcs7-signature'),
        ('text', 'calendar'),
        ('application', 'ics'),
    }
    
    def _should_skip(self, attachment: dict) -> str | None:
        """Check if attachment should be skipped. Returns skip reason or None."""
        media_type = attachment.get('media_type')
        sub_type = attachment.get('sub_type')
        
        # Skip signatures and calendar invites
        if (media_type, sub_type) in self.SKIP_TYPES:
            return f"skip type: {media_type}/{sub_type}"
        
        # Image-specific checks
        if media_type == 'image':
            file_size = attachment.get('file_size')
            width = attachment.get('width')
            height = attachment.get('height')
            
            # Skip small images (likely icons/logos)
            if file_size and file_size < settings.SKIP_IMAGE_MIN_SIZE:
                return f"image too small: {file_size} bytes"
            
            # Skip tiny dimensions
            if width and height:
                if width < settings.SKIP_IMAGE_MIN_DIMENSION or height < settings.SKIP_IMAGE_MIN_DIMENSION:
                    return f"image too small: {width}x{height}px"
        
        return None
    
    def _process_batch(self) -> int:
        """Process a batch of pending attachments. Returns count processed."""
        attachments = self.db.get_pending_attachments(settings.BATCH_SIZE)
        
        if not attachments:
            return 0
        
        processed = 0
        for attachment in attachments:
            if not self.running:
                break
            
            attachment_id = attachment['missive_attachment_id']
            
            # Try to claim this attachment
            if not self.db.mark_downloading(attachment_id):
                continue  # Already claimed by another worker
            
            # Check if should be skipped
            skip_reason = self._should_skip(attachment)
            if skip_reason:
                self.db.mark_skipped(attachment_id, skip_reason)
                processed += 1
                continue
            
            try:
                local_filename = self.processor.process(attachment, db=self.db)
                self.db.mark_completed(attachment_id, local_filename)
                processed += 1
                
            except Exception as e:
                self.db.mark_failed(attachment_id, str(e)[:500])
        
        return processed


def main():
    """Entry point."""
    app = Application()
    
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}")
        app.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        app.run()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
