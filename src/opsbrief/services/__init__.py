"""Services: the logic behind the routers."""

from opsbrief.services.brief_reporting import report_daily_brief
from opsbrief.services.dashboard import build_dashboard_view
from opsbrief.services.incident_reporting import (
    declare_incident,
    get_incident,
    list_incidents,
    resolve_incident,
)
from opsbrief.services.incident_summary_reporting import report_incident_summary
from opsbrief.services.ingestion import record_event, record_events
from opsbrief.services.retrieval import get_event, list_events
from opsbrief.services.risk_reporting import list_risks

__all__ = [
    "build_dashboard_view",
    "declare_incident",
    "get_event",
    "get_incident",
    "list_events",
    "list_incidents",
    "list_risks",
    "record_event",
    "record_events",
    "report_daily_brief",
    "report_incident_summary",
    "resolve_incident",
]
