"""Tests for seeding synthetic demo data into the stores."""

from collections.abc import Iterator

import pytest

from opsbrief.incidents import IncidentStatus
from opsbrief.samples import build_sample_qc_incident, load_sample_match_stored_events
from opsbrief.samples.seed import seed_demo_data
from opsbrief.storage import EventStore, IncidentStore


@pytest.fixture
def stores() -> Iterator[tuple[EventStore, IncidentStore]]:
    """Return a fresh event store and incident store on throwaway databases."""
    with (
        EventStore.open("sqlite:///:memory:") as events,
        IncidentStore.open("sqlite:///:memory:") as incidents,
    ):
        yield events, incidents


def test_seeding_populates_empty_stores(stores: tuple[EventStore, IncidentStore]) -> None:
    events, incidents = stores

    seeded = seed_demo_data(events, incidents)

    assert seeded is True
    assert events.count() == len(load_sample_match_stored_events())
    incident = incidents.get(build_sample_qc_incident().id)
    assert incident is not None
    assert incident.status is IncidentStatus.RESOLVED


def test_seeded_incident_cites_a_seeded_event(stores: tuple[EventStore, IncidentStore]) -> None:
    events, incidents = stores

    seed_demo_data(events, incidents)

    incident = incidents.get(build_sample_qc_incident().id)
    assert incident is not None
    for event_id in incident.event_ids:
        assert events.get(event_id) is not None


def test_seeding_is_skipped_when_events_already_exist(
    stores: tuple[EventStore, IncidentStore],
) -> None:
    events, incidents = stores
    existing = load_sample_match_stored_events()[0]
    events.add(existing)

    seeded = seed_demo_data(events, incidents)

    assert seeded is False
    assert events.count() == 1
    assert incidents.get(build_sample_qc_incident().id) is None


def test_seeding_is_idempotent(stores: tuple[EventStore, IncidentStore]) -> None:
    events, incidents = stores

    assert seed_demo_data(events, incidents) is True
    first_count = events.count()

    assert seed_demo_data(events, incidents) is False
    assert events.count() == first_count
    assert incidents.count() == 1
