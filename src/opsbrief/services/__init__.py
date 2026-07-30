"""Services: the logic behind the routers."""

from opsbrief.services.ingestion import record_event, record_events

__all__ = ["record_event", "record_events"]
