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

__all__ = [
    "ACTIVE_STATUSES",
    "ALLOWED_TRANSITIONS",
    "INACTIVE_STATUSES",
    "TERMINAL_STATUSES",
    "Incident",
    "IncidentClosedError",
    "IncidentEvents",
    "IncidentSeverity",
    "IncidentStatus",
    "InvalidIncidentTransition",
    "can_transition",
    "resolve_incident_events",
]
