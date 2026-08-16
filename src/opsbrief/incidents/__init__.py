"""Incident intelligence: stateful records assembled from related events."""

from opsbrief.incidents.declaration import (
    RISK_TO_INCIDENT_SEVERITY,
    declare_incident_from_risk,
    declare_incidents_from_events,
)
from opsbrief.incidents.lifecycle import (
    ACTIVE_STATUSES,
    ALLOWED_TRANSITIONS,
    INACTIVE_STATUSES,
    TERMINAL_STATUSES,
    IncidentStatus,
    InvalidIncidentTransition,
    can_transition,
)
from opsbrief.incidents.linking import IncidentEvents, resolve_incident_events
from opsbrief.incidents.schema import (
    DEFAULT_INCIDENT_PAGE_SIZE,
    MAX_INCIDENT_PAGE_SIZE,
    Incident,
    IncidentClosedError,
    IncidentDeclaration,
    IncidentPage,
    IncidentQuery,
    IncidentSeverity,
)
from opsbrief.incidents.summary import (
    INCIDENT_SUMMARY_OUTPUT_VERSION,
    INCIDENT_SUMMARY_PROMPT_VERSION,
    MAX_INCIDENT_SUMMARY_LENGTH,
    IncidentSummary,
    generate_incident_summary,
)
from opsbrief.incidents.timeline import (
    IncidentTimeline,
    TimelineEntry,
    build_incident_timeline,
)

__all__ = [
    "ACTIVE_STATUSES",
    "ALLOWED_TRANSITIONS",
    "DEFAULT_INCIDENT_PAGE_SIZE",
    "INACTIVE_STATUSES",
    "INCIDENT_SUMMARY_OUTPUT_VERSION",
    "INCIDENT_SUMMARY_PROMPT_VERSION",
    "MAX_INCIDENT_PAGE_SIZE",
    "MAX_INCIDENT_SUMMARY_LENGTH",
    "RISK_TO_INCIDENT_SEVERITY",
    "TERMINAL_STATUSES",
    "Incident",
    "IncidentClosedError",
    "IncidentDeclaration",
    "IncidentEvents",
    "IncidentPage",
    "IncidentQuery",
    "IncidentSeverity",
    "IncidentStatus",
    "IncidentSummary",
    "IncidentTimeline",
    "InvalidIncidentTransition",
    "TimelineEntry",
    "build_incident_timeline",
    "can_transition",
    "declare_incident_from_risk",
    "declare_incidents_from_events",
    "generate_incident_summary",
    "resolve_incident_events",
]
