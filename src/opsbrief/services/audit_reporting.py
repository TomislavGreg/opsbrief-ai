"""Projecting a generated brief or incident summary into an audit record.

The router hands this module the same stores and provider the brief and
incident-summary endpoints use; it generates the output through the existing
reporting path and projects it into a :class:`~opsbrief.audit.GenerationAudit`.
The audit is a pure projection of an already-generated output, so it holds no
model involvement of its own beyond the summary the output already carried, and
never disagrees with the brief or summary it describes. Reads never mutate either
store.
"""

from collections.abc import Container
from datetime import datetime

from opsbrief.ai import AIProvider
from opsbrief.audit import GenerationAudit, audit_daily_brief, audit_incident_summary
from opsbrief.services.brief_reporting import report_daily_brief
from opsbrief.services.incident_summary_reporting import report_incident_summary
from opsbrief.storage import EventStore, IncidentStore


def report_brief_audit(
    store: EventStore,
    now: datetime,
    provider: AIProvider,
    *,
    excluded_fields: Container[str] = frozenset(),
) -> GenerationAudit:
    """Return the provenance of the current daily brief as a :class:`GenerationAudit`.

    The brief is generated over the whole event history at ``now`` through the same
    path ``GET /brief`` uses, then projected into an audit record. What the brief
    was produced from (its source event ids, and any cited id that no longer
    resolved) and by (its model and prompt and output versions), together with the
    confidence and warning codes it reported, are carried straight over, so the
    audit never disagrees with the brief it describes.
    """
    brief = report_daily_brief(store, now, provider, excluded_fields=excluded_fields)
    return audit_daily_brief(brief)


def report_incident_summary_audit(
    incident_store: IncidentStore,
    event_store: EventStore,
    incident_id: str,
    provider: AIProvider,
    *,
    excluded_fields: Container[str] = frozenset(),
) -> GenerationAudit | None:
    """Return the provenance of a tracked incident's summary as a :class:`GenerationAudit`.

    The incident's summary is generated through the same path
    ``GET /incidents/{incident_id}/summary`` uses, then projected into an audit
    record naming the incident as its subject. Returns ``None`` when no incident
    carries the identifier, so the caller can report a missing incident. What the
    summary was produced from and by, and the confidence and warning codes it
    reported, are carried straight over, so the audit never disagrees with the
    summary it describes.
    """
    summary = report_incident_summary(
        incident_store,
        event_store,
        incident_id,
        provider,
        excluded_fields=excluded_fields,
    )
    if summary is None:
        return None
    return audit_incident_summary(summary)
