"""Tests for the daily-brief reporting service."""

from datetime import UTC, datetime, timedelta

from opsbrief.ai import FakeAIProvider
from opsbrief.events import Event, EventInput
from opsbrief.services import report_daily_brief
from opsbrief.storage import EventStore


def store_event(store: EventStore, **overrides: object) -> str:
    """Store one event and return the identifier it was stored under."""
    now = datetime.now(UTC).replace(microsecond=0)
    payload: dict[str, object] = {
        "source": "tasks",
        "event_type": "task.update",
        "subject": "A work item",
        "occurred_at": (now - timedelta(hours=6)).isoformat(),
    }
    payload.update(overrides)
    event = Event.from_input(EventInput(**payload))
    store.add(event)
    return event.id


def test_no_events_gives_a_brief_that_says_so() -> None:
    provider = FakeAIProvider(responses=["All quiet."])
    with EventStore.open("sqlite:///:memory:") as store:
        brief = report_daily_brief(store, datetime.now(UTC), provider)

    assert brief.risks == []
    assert brief.source_event_ids == []
    assert brief.model == "fake-1"
    assert any("no source data" in note.lower() for note in brief.notes)


def test_brief_traces_to_the_events_behind_its_risks() -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    provider = FakeAIProvider(responses=["One task is overdue."])
    with EventStore.open("sqlite:///:memory:") as store:
        overdue_id = store_event(store, due_at=(now - timedelta(hours=2)).isoformat())

        brief = report_daily_brief(store, now, provider)

    assert brief.summary == "One task is overdue."
    assert [risk.rule for risk in brief.risks] == ["overdue_work"]
    assert brief.risks[0].event_ids == [overdue_id]
    assert overdue_id in brief.source_event_ids
    assert brief.generated_at == now


def test_summary_is_phrased_by_the_provider_and_constrained() -> None:
    # An unscripted fake echoes the material it is shown; the summary is still a
    # bounded single line, because the model's output is treated as untrusted.
    now = datetime.now(UTC).replace(microsecond=0)
    provider = FakeAIProvider()
    with EventStore.open("sqlite:///:memory:") as store:
        store_event(store)

        brief = report_daily_brief(store, now, provider)

    assert "\n" not in brief.summary
    assert len(brief.summary) <= 1_000
    assert len(provider.requests) == 1


def test_missing_summary_is_noted_rather_than_invented() -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    provider = FakeAIProvider(responses=["   "])
    with EventStore.open("sqlite:///:memory:") as store:
        store_event(store)

        brief = report_daily_brief(store, now, provider)

    assert brief.summary == ""
    assert any("no summary" in note.lower() for note in brief.notes)
