"""Services: the logic behind the routers."""

from opsbrief.services.ingestion import record_event, record_events
from opsbrief.services.retrieval import list_events

__all__ = ["list_events", "record_event", "record_events"]
