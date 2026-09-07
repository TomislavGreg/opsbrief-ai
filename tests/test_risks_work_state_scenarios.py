"""Behavioural scenarios for work-state evaluation (AI-092, finding F01).

Each case feeds a sequence of events for a stable work entity through the whole
risk-reporting path (and, for one case, a generated brief) and asserts which
rules fire on the entity's current state. These guard the contract that a later
state change for the same entity clears the obsolete risk, which the per-event
rules did not honour before work was grouped by entity.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from opsbrief.ai import FakeAIProvider
from opsbrief.events import Event, EventInput
from opsbrief.services import list_risks, report_daily_brief
from opsbrief.storage import EventStore

NOW = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
PAST_DUE = NOW - timedelta(hours=3)
FUTURE_DUE = NOW + timedelta(days=1)

#: An entity all events in a scenario share, so they describe one piece of work.
ENTITY = {"entity_type": "task", "entity_id": "M-3301"}


@pytest.fixture
def store() -> Iterator[EventStore]:
    """Return a throwaway in-memory event store."""
    with EventStore.open("sqlite:///:memory:") as opened:
        yield opened


def _event(event_id: str, *, hours_ago: float, **overrides: object) -> Event:
    """Build one stored event for the shared entity at ``hours_ago`` before NOW."""
    payload: dict[str, object] = {
        "source": "tasks",
        "event_type": "task.update",
        "subject": "Pre-match pitch inspection",
        "occurred_at": NOW - timedelta(hours=hours_ago),
        **ENTITY,
    }
    payload.update(overrides)
    event = Event.from_input(EventInput(**payload))
    return event.model_copy(update={"id": event_id})


def _rules_firing(store: EventStore) -> set[str]:
    """Return the set of rule ids that raise a risk over the store at NOW."""
    return {risk.rule for risk in list_risks(store, NOW).risks}


# Each scenario: a name, the ordered events for one entity, and the rule ids that
# should fire on the entity's current state.
SCENARIOS: list[tuple[str, list[Event], set[str]]] = [
    (
        "blocked then resolved clears the block",
        [
            _event("a", hours_ago=5, status="blocked"),
            _event("b", hours_ago=1, status="resolved"),
        ],
        set(),
    ),
    (
        "overdue then resolved clears the overdue",
        [
            _event("a", hours_ago=5, status="overdue", due_at=PAST_DUE),
            _event("b", hours_ago=1, status="resolved"),
        ],
        set(),
    ),
    (
        "overdue then cancelled clears the overdue",
        [
            _event("a", hours_ago=5, status="overdue", due_at=PAST_DUE),
            _event("b", hours_ago=1, status="cancelled"),
        ],
        set(),
    ),
    (
        "a task-completed resolution clears the block",
        [
            _event("a", hours_ago=5, status="blocked"),
            _event("b", hours_ago=1, event_type="task.completed", status="resolved"),
        ],
        set(),
    ),
    (
        "still blocked keeps the block",
        [
            _event("a", hours_ago=5, status="blocked"),
            _event("b", hours_ago=1, status="blocked"),
        ],
        {"blocked_work"},
    ),
    (
        "resolved then reopened blocked raises again",
        [
            _event("a", hours_ago=6, status="blocked"),
            _event("b", hours_ago=4, status="resolved"),
            _event("c", hours_ago=1, status="blocked"),
        ],
        {"blocked_work"},
    ),
    (
        "a later deadline in the future clears the overdue",
        [
            _event("a", hours_ago=5, status="open", due_at=PAST_DUE),
            _event("b", hours_ago=1, status="in_progress", due_at=FUTURE_DUE),
        ],
        set(),
    ),
    (
        "a still-past changed deadline stays overdue",
        [
            _event("a", hours_ago=5, status="open", due_at=NOW - timedelta(hours=5)),
            _event("b", hours_ago=1, status="in_progress", due_at=PAST_DUE),
        ],
        {"overdue_work"},
    ),
    (
        "blocked and past due raises both rules",
        [
            _event("a", hours_ago=2, status="blocked", due_at=PAST_DUE),
        ],
        {"blocked_work", "overdue_work"},
    ),
    (
        "repeated blocked reports raise a single risk",
        [
            _event("a", hours_ago=5, status="blocked"),
            _event("b", hours_ago=3, status="blocked"),
            _event("c", hours_ago=1, status="blocked"),
        ],
        {"blocked_work"},
    ),
]


@pytest.mark.parametrize(
    ("name", "events", "expected"),
    SCENARIOS,
    ids=[name for name, _, _ in SCENARIOS],
)
def test_current_state_decides_the_risks(
    store: EventStore, name: str, events: list[Event], expected: set[str]
) -> None:
    for event in events:
        store.add(event)

    assert _rules_firing(store) == expected


def test_repeated_blocked_reports_yield_one_risk_citing_the_run_start(
    store: EventStore,
) -> None:
    for event in [
        _event("first", hours_ago=5, status="blocked"),
        _event("again", hours_ago=1, status="blocked"),
    ]:
        store.add(event)

    risks = list_risks(store, NOW).risks

    assert len(risks) == 1
    assert risks[0].event_ids == ["first"]


def test_same_id_from_a_different_source_is_isolated(store: EventStore) -> None:
    # One source resolves its work; a different source sharing the id stays blocked.
    store.add(_event("a", hours_ago=5, status="blocked"))
    store.add(_event("b", hours_ago=1, status="resolved"))
    store.add(
        _event("c", hours_ago=2, source="rostering", status="blocked").model_copy(
            update={"id": "c"}
        )
    )

    risks = list_risks(store, NOW).risks

    assert [risk.event_ids for risk in risks] == [["c"]]


def test_a_resolved_entity_drops_out_of_the_generated_brief(store: EventStore) -> None:
    store.add(_event("a", hours_ago=5, status="blocked", due_at=PAST_DUE))
    store.add(_event("b", hours_ago=1, status="resolved"))

    brief = report_daily_brief(store, NOW, FakeAIProvider(responses=["All clear."]))

    # No risk fires, but the history stays retrievable as evidence in the brief.
    assert brief.risks == []
    assert set(brief.source_event_ids) == {"a", "b"}


def test_an_unresolved_entity_reaches_the_generated_brief(store: EventStore) -> None:
    store.add(_event("a", hours_ago=2, status="blocked"))

    brief = report_daily_brief(store, NOW, FakeAIProvider(responses=["One task is blocked."]))

    assert [risk.rule for risk in brief.risks] == ["blocked_work"]
    assert brief.source_event_ids == ["a"]
