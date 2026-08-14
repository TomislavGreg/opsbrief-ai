"""Incident intelligence: stateful records assembled from related events."""

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
from opsbrief.incidents.schema import Incident, IncidentClosedError, IncidentSeverity
from opsbrief.incidents.summary import (
    INCIDENT_SUMMARY_OUTPUT_VERSION,
    INCIDENT_SUMMARY_PROMPT_VERSION,
    MAX_INCIDENT_SUMMARY_LENGTH,
    IncidentSummary,
)
from opsbrief.incidents.timeline import (
    IncidentTimeline,
    TimelineEntry,
    build_incident_timeline,
)

__all__ = [
    "ACTIVE_STATUSES",
    "ALLOWED_TRANSITIONS",
    "INACTIVE_STATUSES",
    "INCIDENT_SUMMARY_OUTPUT_VERSION",
    "INCIDENT_SUMMARY_PROMPT_VERSION",
    "MAX_INCIDENT_SUMMARY_LENGTH",
    "TERMINAL_STATUSES",
    "Incident",
    "IncidentClosedError",
    "IncidentEvents",
    "IncidentSeverity",
    "IncidentStatus",
    "IncidentSummary",
    "IncidentTimeline",
    "InvalidIncidentTransition",
    "TimelineEntry",
    "build_incident_timeline",
    "can_transition",
    "resolve_incident_events",
]
