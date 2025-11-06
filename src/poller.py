"""Polling service for fetching new conversations from Missive."""
import time
import threading
from datetime import datetime
from typing import Dict, Any

from src.logging_conf import logger
from src import settings
from src.missive_client import MissiveClient
from src.queue.spool_queue import SpoolQueue
from src.queue.models import QueueItem
from src.checkpoint import CheckpointManager


class Poller:
    """Polls Missive API for new conversations."""
    
    def __init__(self):
        self.client = MissiveClient()
        self.queue = SpoolQueue()
        self.checkpoint = CheckpointManager()
        self.running = False
        self.thread = None
        self.polling_interval = settings.POLLING_INTERVAL
    
    def start(self):
        """Start the poller in a background thread."""
        if self.running:
            logger.warning("Poller is already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        logger.info(f"Poller started (interval: {self.polling_interval}s)")
    
    def stop(self):
        """Stop the poller."""
        if not self.running:
            return
        
        self.running = False
        if self.thread:
            self.thread.join(timeout=10)
        logger.info("Poller stopped")
    
    def _run(self):
        """Main poller loop."""
        logger.info("Poller thread started")
        
        while self.running:
            try:
                self._poll_once()
            except Exception as e:
                logger.error(f"Poller error: {e}", exc_info=True)
            
            # Sleep for polling interval
            for _ in range(self.polling_interval):
                if not self.running:
                    break
                time.sleep(1)
        
        logger.info("Poller thread stopped")
    
    def _poll_once(self):
        """Perform one polling cycle."""
        try:
            # Get last sync time from checkpoint
            last_sync = self.checkpoint.get_last_sync_time()
            logger.info(f"Polling for conversations updated since: {last_sync.isoformat()}")
            
            # Fetch conversations
            conversations = self.client.get_conversations_updated_since(last_sync)
            
            logger.info(f"Found {len(conversations)} conversations to process")
            
            # Filter conversations with attachments and enqueue them
            queued_count = 0
            for conversation in conversations:
                if self._has_attachments(conversation):
                    conversation_id = conversation.get("id")
                    if conversation_id:
                        item = QueueItem.create(
                            source="missive",
                            event_type="conversation",
                            external_id=conversation_id,
                            payload=conversation
                        )
                        self.queue.enqueue(item)
                        queued_count += 1
            
            logger.info(f"Queued {queued_count} conversations with attachments")
            
            # Update checkpoint to now
            self.checkpoint.save_sync_time(datetime.now())
        
        except Exception as e:
            logger.error(f"Error during polling: {e}", exc_info=True)
            raise
    
    def _has_attachments(self, conversation: Dict[str, Any]) -> bool:
        """Check if a conversation has any attachments."""
        try:
            # Check the attachments_count field if available
            attachments_count = conversation.get("attachments_count", 0)
            if attachments_count > 0:
                return True
            
            # Check the latest_message for attachments
            latest_message = conversation.get("latest_message", {})
            attachments = latest_message.get("attachments", [])
            
            if attachments and len(attachments) > 0:
                return True
            
            # Log first conversation for debugging (only once)
            if not hasattr(self, '_logged_sample'):
                self._logged_sample = True
                logger.debug(f"Sample conversation keys: {list(conversation.keys())}")
                if latest_message:
                    logger.debug(f"Sample latest_message keys: {list(latest_message.keys())}")
            
            return False
        except Exception as e:
            logger.debug(f"Error checking for attachments: {e}")
            return False

