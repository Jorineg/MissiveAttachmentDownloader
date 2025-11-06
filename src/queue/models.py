"""Queue data models."""
from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class QueueItem:
    """Represents an item in the processing queue."""
    
    source: str  # Always "missive" for this app
    event_type: str  # "conversation" or "message"
    external_id: str  # Conversation ID or message ID
    payload: Dict[str, Any]  # Full event data
    
    @classmethod
    def create(cls, source: str, event_type: str, external_id: str, payload: Dict[str, Any]):
        """Factory method to create a QueueItem."""
        return cls(
            source=source,
            event_type=event_type,
            external_id=external_id,
            payload=payload
        )


