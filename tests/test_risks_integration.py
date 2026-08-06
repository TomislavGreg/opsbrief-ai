"""Tests for identifying integration failures and recoveries."""

from datetime import UTC, datetime, timedelta

from opsbrief.events import Event, EventInput, EventStatus
from opsbrief.risks.rules.integration import (
    integration_key,
    is_integration_failure,
    is_integration_recovery,
)

NOW = datetime(2026, 7, 29, 18, 0, tzinfo=UTC)


def make_event(event_id: str = "e1", **overrides: object) -> Event:
    """Return a stored integration event with the given id and fields replaced."""
    payload: dict[str, object] = {
        "source": "integrations",
        "event_type": "integration.failed",
        "subject": f"Ticketing webhook attempt {event_id}",
        "occurred_at": NOW - timedelta(hours=1),
        "status": EventStatus.FAILED,
        "entity_type": "integration",
        "entity_id": "ticketing-webhook",
    }
    payload.update(overrides)
    return Event.from_input(EventInput(**payload)).model_copy(update={"id": event_id})


def test_failed_event_with_an_entity_is_a_failure() -> None:
    assert is_integration_failure(make_event()) is True


def test_failed_event_without_an_entity_is_not_a_failure() -> None:
    # Without an entity id the failure cannot be attributed to an integration.
    event = make_event(entity_type=None, entity_id=None)

    assert is_integration_failure(event) is False


def test_non_failed_event_is_not_a_failure() -> None:
    assert is_integration_failure(make_event(status=EventStatus.OPEN)) is False
    assert is_integration_failure(make_event(status=None)) is False


def test_resolved_event_with_an_entity_is_a_recovery() -> None:
    event = make_event(event_type="integration.recovered", status=EventStatus.RESOLVED)

    assert is_integration_recovery(event) is True


def test_resolved_event_without_an_entity_is_not_a_recovery() -> None:
    event = make_event(status=EventStatus.RESOLVED, entity_type=None, entity_id=None)

    assert is_integration_recovery(event) is False


def test_failure_and_recovery_are_distinct() -> None:
    failure = make_event()
    recovery = make_event(status=EventStatus.RESOLVED)

    assert is_integration_failure(failure) and not is_integration_recovery(failure)
    assert is_integration_recovery(recovery) and not is_integration_failure(recovery)


def test_same_integration_shares_a_key() -> None:
    first = make_event("a")
    second = make_event("b")

    assert integration_key(first) == integration_key(second)


def test_different_integrations_have_different_keys() -> None:
    ticketing = make_event(entity_id="ticketing-webhook")
    payments = make_event(entity_id="payments-webhook")

    assert integration_key(ticketing) != integration_key(payments)


def test_same_entity_from_different_sources_does_not_collide() -> None:
    one = make_event(source="integrations")
    other = make_event(source="platform")

    assert integration_key(one) != integration_key(other)
