"""Tests for the risk-rule interface and the detector."""

from collections.abc import Sequence
from datetime import UTC, datetime

from opsbrief.events import Event, EventInput
from opsbrief.risks import Risk, RiskRule, RiskSeverity, detect_risks

OCCURRED_AT = datetime(2026, 7, 29, 9, 30, tzinfo=UTC)


def make_event(event_id: str, **overrides: object) -> Event:
    """Return a stored event with the given id and fields replaced."""
    payload: dict[str, object] = {
        "source": "tasks",
        "event_type": "task.overdue",
        "subject": f"Event {event_id}",
        "occurred_at": OCCURRED_AT,
    }
    payload.update(overrides)
    return Event.from_input(EventInput(**payload)).model_copy(update={"id": event_id})


class RecordingRule:
    """A rule that raises one risk per event, remembering what it was given."""

    def __init__(self, rule_id: str, severity: RiskSeverity = RiskSeverity.LOW) -> None:
        self.rule_id = rule_id
        self._severity = severity
        self.seen: list[Sequence[Event]] = []

    def evaluate(self, events: Sequence[Event]) -> list[Risk]:
        self.seen.append(events)
        return [
            Risk(
                rule=self.rule_id,
                title=f"{self.rule_id} on {event.id}",
                detail=f"{self.rule_id} raised by {event.id}",
                severity=self._severity,
                event_ids=[event.id],
            )
            for event in events
        ]


class SilentRule:
    """A rule that never raises anything."""

    rule_id = "silent"

    def evaluate(self, events: Sequence[Event]) -> list[Risk]:
        return []


def test_recording_rule_satisfies_the_protocol() -> None:
    assert isinstance(RecordingRule("overdue_work"), RiskRule)
    assert isinstance(SilentRule(), RiskRule)


def test_no_rules_finds_no_risks() -> None:
    assert detect_risks([make_event("e1")], []) == []


def test_a_rule_that_finds_nothing_contributes_nothing() -> None:
    assert detect_risks([make_event("e1")], [SilentRule()]) == []


def test_risks_are_collected_across_rules_in_rule_order() -> None:
    events = [make_event("e1"), make_event("e2")]

    risks = detect_risks(events, [RecordingRule("first"), RecordingRule("second")])

    assert [risk.rule for risk in risks] == ["first", "first", "second", "second"]
    assert [risk.event_ids[0] for risk in risks] == ["e1", "e2", "e1", "e2"]


def test_each_rule_sees_the_same_events() -> None:
    events = [make_event("e1"), make_event("e2")]
    first, second = RecordingRule("first"), RecordingRule("second")

    detect_risks(events, [first, second])

    assert list(first.seen[0]) == events
    assert list(second.seen[0]) == events


def test_detection_is_deterministic() -> None:
    events = [make_event("e1"), make_event("e2")]
    rule = RecordingRule("overdue_work", severity=RiskSeverity.HIGH)

    first = detect_risks(events, [rule])
    second = detect_risks(events, [rule])

    assert first == second


def test_raised_risks_carry_the_rule_id_and_evidence() -> None:
    risks = detect_risks([make_event("e1")], [RecordingRule("overdue_work")])

    assert len(risks) == 1
    assert risks[0].rule == "overdue_work"
    assert risks[0].event_ids == ["e1"]
