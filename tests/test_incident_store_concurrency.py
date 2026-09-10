"""Concurrency regression tests for atomic incident mutations.

These cover AI-096: the incident services read, change and write an incident,
and before the change was routed through :meth:`IncidentStore.mutate` two
callers could read the same row, apply different changes and save, losing one of
them while both saw success. The tests share one store across threads and
release the threads together with a :class:`threading.Barrier`, so the mutations
genuinely contend rather than running one after another, and no sleeps are
needed to expose the race. They use file-backed storage and reopen it to confirm
the persisted outcome, not just the in-memory return value.

The guarantee is scoped to one store (one connection guarded by its lock), which
is how the application runs: a single shared store per process. Separate
connections to the same file are not serialised by that lock and are out of
scope here.
"""

import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from opsbrief.incidents import (
    Incident,
    IncidentClosedError,
    IncidentEventLink,
    IncidentResolution,
    IncidentSeverity,
    IncidentStatus,
    IncidentTransition,
)
from opsbrief.services import (
    link_incident_events,
    resolve_incident,
    transition_incident,
    unlink_incident_event,
)
from opsbrief.storage import IncidentStore

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
LATER = NOW + timedelta(hours=1)


@pytest.fixture
def database_url(tmp_path) -> str:
    """Return a URL for a throwaway file-backed database, so it can be reopened."""
    return f"sqlite:///{tmp_path / 'incidents.db'}"


@pytest.fixture
def store(database_url: str) -> Iterator[IncidentStore]:
    """Return a file-backed store shared across the test's threads."""
    with IncidentStore.open(database_url) as store:
        yield store


def declare(store: IncidentStore, event_ids: list[str]) -> Incident:
    """Declare and store an incident carrying ``event_ids``."""
    incident = Incident.declare(
        title="Ticketing integration failing repeatedly",
        severity=IncidentSeverity.HIGH,
        event_ids=event_ids,
        at=NOW,
    )
    return store.add(incident)


def run_together(operations: list[Callable[[], object]]) -> list[object | BaseException]:
    """Run ``operations`` on separate threads released by one barrier.

    Each entry runs on its own thread, and every thread waits at the barrier
    before starting, so the operations contend rather than running in sequence.
    Returns each operation's result, or the exception it raised, in the order the
    operations were given.
    """
    barrier = threading.Barrier(len(operations))
    results: list[object | BaseException] = [None] * len(operations)

    def worker(index: int, operation: Callable[[], object]) -> None:
        barrier.wait()
        try:
            results[index] = operation()
        except BaseException as error:  # noqa: BLE001 - recorded and re-checked by the test
            results[index] = error

    with ThreadPoolExecutor(max_workers=len(operations)) as pool:
        futures = [pool.submit(worker, index, op) for index, op in enumerate(operations)]
        for future in futures:
            future.result()
    return results


def test_concurrent_links_preserve_every_addition(store: IncidentStore, database_url: str) -> None:
    incident = declare(store, ["e17"])
    new_ids = [f"e{n}" for n in range(20, 28)]

    def link(event_id: str) -> object:
        return link_incident_events(
            store, incident.id, IncidentEventLink(event_ids=[event_id]), LATER
        )

    results = run_together([lambda eid=eid: link(eid) for eid in new_ids])

    assert all(not isinstance(result, BaseException) for result in results)
    stored = store.get(incident.id)
    assert stored is not None
    assert stored.event_ids[0] == "e17"
    assert sorted(stored.event_ids) == sorted(["e17", *new_ids])
    assert len(stored.event_ids) == len(set(stored.event_ids))

    with IncidentStore.open(database_url) as reopened:
        persisted = reopened.get(incident.id)
    assert persisted is not None
    assert sorted(persisted.event_ids) == sorted(["e17", *new_ids])


def test_concurrent_link_and_unlink_both_apply(store: IncidentStore, database_url: str) -> None:
    incident = declare(store, ["e17", "e18"])

    results = run_together(
        [
            lambda: link_incident_events(
                store, incident.id, IncidentEventLink(event_ids=["e30"]), LATER
            ),
            lambda: unlink_incident_event(store, incident.id, "e18", LATER),
        ]
    )

    assert all(not isinstance(result, BaseException) for result in results)
    with IncidentStore.open(database_url) as reopened:
        persisted = reopened.get(incident.id)
    assert persisted is not None
    # Whichever order the two mutations ran in, both are applied to the same row.
    assert set(persisted.event_ids) == {"e17", "e30"}


def test_concurrent_resolve_and_transition_leave_one_coherent_state(
    store: IncidentStore, database_url: str
) -> None:
    incident = declare(store, ["e17"])

    results = run_together(
        [
            lambda: resolve_incident(store, incident.id, IncidentResolution(note="fixed"), LATER),
            lambda: transition_incident(
                store, incident.id, IncidentTransition(status=IncidentStatus.INVESTIGATING), LATER
            ),
        ]
    )

    # From open both moves are legal, and each resulting state can still take the
    # other move (resolved reopens to investigating, investigating resolves), so
    # both apply whichever order they run in. The point under test is that the two
    # writes are serialised into one coherent row, not one clobbering a
    # half-written other: the persisted status is exactly the end of one legal
    # ordering, with resolved_at and note consistent with it.
    assert all(isinstance(result, Incident) for result in results)
    with IncidentStore.open(database_url) as reopened:
        persisted = reopened.get(incident.id)
    assert persisted is not None
    if persisted.status is IncidentStatus.RESOLVED:
        # ...open -> investigating -> resolved: the resolve ran last.
        assert persisted.resolved_at == LATER
        assert persisted.resolution_note == "fixed"
    else:
        # ...open -> resolved -> investigating: reopening clears the resolution.
        assert persisted.status is IncidentStatus.INVESTIGATING
        assert persisted.resolved_at is None
        assert persisted.resolution_note is None


def test_concurrent_close_and_link_respect_the_frozen_rule(
    store: IncidentStore, database_url: str
) -> None:
    resolved = declare(store, ["e17"]).transition_to(IncidentStatus.RESOLVED, at=NOW)
    store.save(resolved)

    results = run_together(
        [
            lambda: transition_incident(
                store, resolved.id, IncidentTransition(status=IncidentStatus.CLOSED), LATER
            ),
            lambda: link_incident_events(
                store, resolved.id, IncidentEventLink(event_ids=["e30"]), LATER
            ),
        ]
    )

    close_result, link_result = results
    assert isinstance(close_result, Incident)
    assert close_result.status is IncidentStatus.CLOSED

    with IncidentStore.open(database_url) as reopened:
        persisted = reopened.get(resolved.id)
    assert persisted is not None
    if isinstance(link_result, IncidentClosedError):
        # The close ran first: the incident is frozen and the link left it untouched.
        assert persisted.status is IncidentStatus.CLOSED
        assert persisted.event_ids == ["e17"]
    else:
        # The link ran first, then the close: the evidence grew and then froze.
        assert not isinstance(link_result, BaseException)
        assert persisted.status is IncidentStatus.CLOSED
        assert persisted.event_ids == ["e17", "e30"]
