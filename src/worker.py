"""Worker for processing queued conversations."""
import time
import threading
from datetime import datetime

from src.logging_conf import logger
from src.queue.spool_queue import SpoolQueue
from src.missive_client import MissiveClient
from src.attachment_processor import AttachmentProcessor


class Worker:
    """Worker that processes conversations from the queue."""
    
    def __init__(self):
        self.queue = SpoolQueue()
        self.client = MissiveClient()
        self.processor = AttachmentProcessor(self.client)
        self.running = False
        self.thread = None
    
    def start(self):
        """Start the worker in a background thread."""
        if self.running:
            logger.warning("Worker is already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        logger.info("Worker started")
    
    def stop(self):
        """Stop the worker."""
        if not self.running:
            return
        
        self.running = False
        if self.thread:
            self.thread.join(timeout=10)
        logger.info("Worker stopped")
    
    def _run(self):
        """Main worker loop."""
        logger.info("Worker thread started")
        
        while self.running:
            try:
                # Process batch of items
                batch = self.queue.dequeue_batch(max_items=5)
                
                if not batch:
                    # No items, sleep briefly
                    time.sleep(1)
                    continue
                
                # Process each item
                for item in batch:
                    if not self.running:
                        break
                    
                    try:
                        logger.info(f"Processing conversation: {item.external_id}")
                        self.processor.process_conversation(item.external_id)
                        logger.info(f"Successfully processed conversation: {item.external_id}")
                    except Exception as e:
                        logger.error(f"Failed to process conversation {item.external_id}: {e}", exc_info=True)
                        self.queue.mark_failed(item, str(e))
                        continue
                
                # Mark all successfully processed
                self.queue.mark_batch_processed()
            
            except Exception as e:
                logger.error(f"Worker error: {e}", exc_info=True)
                time.sleep(5)
        
        logger.info("Worker thread stopped")

