"""Assessing whether the service is ready to serve, not just alive.

Liveness (``GET /health``) reports that the process is up and which build is
deployed; it never touches the database, so it stays cheap and never fails for a
reason outside the process. Readiness is the stronger question a deployment's
orchestrator asks before routing traffic: are the dependencies the service needs
actually reachable? The one dependency OpsBrief AI has is its SQLite database,
opened as the event store and the incident store, so readiness probes both with a
cheap counting query and reports whether each answered.

The probe turns any failure into a "not ready" result rather than propagating it,
so a readiness check reports a degraded dependency as a structured answer instead
of a 500. Reads never mutate a store.
"""

from collections.abc import Callable

from pydantic import BaseModel, Field

from opsbrief.storage import EventStore, IncidentStore


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


def _probe(name: str, probe: Callable[[], object]) -> DependencyReadiness:
    """Run one dependency ``probe``, turning any failure into a not-ready result.

    A readiness probe must never raise: a dependency that cannot answer is the
    thing readiness is meant to report, so any exception is captured as the
    ``detail`` of a not-ready result rather than propagated.
    """
    try:
        probe()
    except Exception as error:  # noqa: BLE001 - readiness turns any failure into "not ready"
        return DependencyReadiness(
            name=name, ready=False, detail=str(error) or type(error).__name__
        )
    return DependencyReadiness(name=name, ready=True)


def check_readiness(event_store: EventStore, incident_store: IncidentStore) -> Readiness:
    """Return whether the service's stores are reachable, probing each in turn.

    Each store is probed with a cheap counting query, which exercises the same
    connection a real request uses without depending on any stored data. The
    overall result is ready only when every dependency answered, so an orchestrator
    can gate traffic on it; the per-dependency checks name which one is degraded.
    """
    checks = [
        _probe("event_store", event_store.count),
        _probe("incident_store", incident_store.count),
    ]
    return Readiness(ready=all(check.ready for check in checks), checks=checks)
