"""Assessing whether the service is ready to serve, not just alive.

Liveness (``GET /health``) reports that the process is up and which build is
deployed; it never touches the database, so it stays cheap and never fails for a
reason outside the process. Readiness is the stronger question a deployment's
orchestrator asks before routing traffic: are the dependencies the service needs
actually reachable? The one dependency OpsBrief AI has is its SQLite database,
opened as the event store and the incident store, so readiness probes both with a
cheap schema-aware query (a single row read, not a whole-table count) and reports
whether each answered.

The probe turns any failure into a "not ready" result rather than propagating it,
so a readiness check reports a degraded dependency as a structured answer instead
of a 500. The reported ``detail`` is a fixed, safe category, never the raw
exception text, so a database path, a credential or an arbitrary driver message
cannot leak through a public probe. Reads never mutate a store.
"""

import sqlite3
from collections.abc import Callable

from pydantic import BaseModel, Field

from opsbrief.storage import EventStore, IncidentStore

#: Safe, fixed readiness details. A probe never reports the raw exception text,
#: so no path, credential or driver message reaches a public readiness response.
_SCHEMA_UNAVAILABLE = "storage schema is unavailable"
_STORAGE_UNAVAILABLE = "storage is unavailable"


class DependencyReadiness(BaseModel):
    """Whether one dependency answered a readiness probe."""

    name: str = Field(description="The dependency probed, for example 'event_store'.")
    ready: bool = Field(description="Whether the dependency answered the probe.")
    detail: str | None = Field(
        default=None,
        description="Why the dependency was not ready, when it was not; absent when ready.",
    )


class Readiness(BaseModel):
    """The readiness of the service and each dependency behind it."""

    ready: bool = Field(description="Whether every probed dependency answered.")
    checks: list[DependencyReadiness] = Field(
        description="One result per dependency, in a stable order.",
    )


def _safe_detail(error: Exception) -> str:
    """Return a fixed, safe category for a probe failure, never the raw message.

    A missing table (the schema was never created) is distinguished from any
    other failure so an operator can tell an uninitialised database from an
    unreachable one, but the raw exception text, which can carry a database path
    or a driver's internal detail, is never returned.
    """
    if isinstance(error, sqlite3.OperationalError) and "no such table" in str(error).lower():
        return _SCHEMA_UNAVAILABLE
    return _STORAGE_UNAVAILABLE


def _probe(name: str, probe: Callable[[], object]) -> DependencyReadiness:
    """Run one dependency ``probe``, turning any failure into a not-ready result.

    A readiness probe must never raise: a dependency that cannot answer is the
    thing readiness is meant to report, so any exception is captured as a
    not-ready result rather than propagated. The captured ``detail`` is a fixed
    safe category, so the raw exception text never reaches a public response.
    """
    try:
        probe()
    except Exception as error:  # noqa: BLE001 - readiness turns any failure into "not ready"
        return DependencyReadiness(name=name, ready=False, detail=_safe_detail(error))
    return DependencyReadiness(name=name, ready=True)


def check_readiness(event_store: EventStore, incident_store: IncidentStore) -> Readiness:
    """Return whether the service's stores are reachable, probing each in turn.

    Each store is probed with a cheap schema-aware query (a single row read, not a
    whole-table count), which exercises the same connection a real request uses
    without depending on any stored data or scanning the table. The overall result
    is ready only when every dependency answered, so an orchestrator can gate
    traffic on it; the per-dependency checks name which one is degraded with a safe
    category rather than a raw error.
    """
    checks = [
        _probe("event_store", event_store.ping),
        _probe("incident_store", incident_store.ping),
    ]
    return Readiness(ready=all(check.ready for check in checks), checks=checks)
