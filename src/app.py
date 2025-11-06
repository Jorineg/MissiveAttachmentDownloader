"""Main application entry point."""
import signal
import sys
import time

from src.logging_conf import logger
from src import settings
from src.poller import Poller
from src.worker import Worker


class Application:
    """Main application that coordinates poller and worker."""
    
    def __init__(self):
        self.poller = Poller()
        self.worker = Worker()
        self.running = False
    
    def start(self):
        """Start the application."""
        logger.info("=" * 60)
        logger.info("Missive Attachment Downloader")
        logger.info("=" * 60)
        logger.info(f"Storage path: {settings.ATTACHMENT_STORAGE_PATH}")
        logger.info(f"Polling interval: {settings.POLLING_INTERVAL}s")
        logger.info(f"Timezone: {settings.TIMEZONE}")
        logger.info("=" * 60)
        
        # Validate configuration
        try:
            settings.validate_config()
            logger.info("Configuration validated successfully")
        except ValueError as e:
            logger.error(f"Configuration error: {e}")
            sys.exit(1)
        
        # Start components
        self.running = True
        self.worker.start()
        self.poller.start()
        
        logger.info("Application started successfully")
        logger.info("Press Ctrl+C to stop")
    
    def stop(self):
        """Stop the application."""
        if not self.running:
            return
        
        logger.info("Shutting down...")
        self.running = False
        
        self.poller.stop()
        self.worker.stop()
        
        logger.info("Application stopped")
    
    def run(self):
        """Run the application until interrupted."""
        self.start()
        
        # Wait for interrupt
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        finally:
            self.stop()


def main():
    """Main entry point."""
    app = Application()
    
    # Handle signals
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}")
        app.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run application
    app.run()


if __name__ == "__main__":
    main()


