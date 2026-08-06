"""Tests for the repeated-integration-failure risk rule."""

from datetime import UTC, datetime, timedelta

from opsbrief.events import Event, EventInput, EventStatus
from opsbrief.risks import RepeatedIntegrationFailureRule, RiskRule, RiskSeverity, detect_risks
from opsbrief.risks.rules.integration import (
    ESCALATION_COUNT,
    FAILURE_THRESHOLD,
    WINDOW,
)

NOW = datetime(2026, 7, 29, 18, 0, tzinfo=UTC)


def failure(
    event_id: str, *, ago: timedelta, entity_id: str = "ticketing-webhook", **overrides: object
) -> Event:
    """Return a stored integration-failure event ``ago`` before NOW."""
    payload: dict[str, object] = {
        "source": "integrations",
        "event_type": "integration.failed",
        "subject": f"Ticketing webhook attempt {event_id}",
        "occurred_at": NOW - ago,
        "status": EventStatus.FAILED,
        "entity_type": "integration",
        "entity_id": entity_id,
    }
    payload.update(overrides)
    return Event.from_input(EventInput(**payload)).model_copy(update={"id": event_id})


def recovery(event_id: str, *, ago: timedelta, entity_id: str = "ticketing-webhook") -> Event:
    """Return a stored integration-recovery event ``ago`` before NOW."""
    return failure(
        event_id,
        ago=ago,
        entity_id=entity_id,
        event_type="integration.recovered",
        status=EventStatus.RESOLVED,
        subject="Ticketing webhook recovered",
    )


def make_run(count: int, *, spacing_hours: int = 1) -> list[Event]:
    """Return ``count`` failures of one integration, most recent last."""
    return [
        failure(f"f{i}", ago=timedelta(hours=spacing_hours * (count - i))) for i in range(count)
    ]


def test_rule_satisfies_the_protocol() -> None:
    assert isinstance(RepeatedIntegrationFailureRule(NOW), RiskRule)
    assert RepeatedIntegrationFailureRule(NOW).rule_id == "repeated_integration_failure"


def test_repeated_failures_raise_a_traceable_risk() -> None:
    events = make_run(FAILURE_THRESHOLD)

    risks = RepeatedIntegrationFailureRule(NOW).evaluate(events)

    assert len(risks) == 1
    assert risks[0].rule == "repeated_integration_failure"
    assert len(risks[0].event_ids) == FAILURE_THRESHOLD
    assert "ticketing-webhook" in risks[0].title


def test_below_the_threshold_raises_nothing() -> None:
    events = make_run(FAILURE_THRESHOLD - 1)

    assert RepeatedIntegrationFailureRule(NOW).evaluate(events) == []


def test_a_single_failure_raises_nothing() -> None:
    assert (
        RepeatedIntegrationFailureRule(NOW).evaluate([failure("one", ago=timedelta(hours=1))]) == []
    )


def test_no_events_raises_nothing() -> None:
    assert RepeatedIntegrationFailureRule(NOW).evaluate([]) == []


def test_failures_without_an_entity_are_ignored() -> None:
    events = [
        failure(f"f{i}", ago=timedelta(hours=i + 1), entity_type=None, entity_id=None)
        for i in range(FAILURE_THRESHOLD)
    ]

    assert RepeatedIntegrationFailureRule(NOW).evaluate(events) == []


def test_failures_across_integrations_do_not_combine() -> None:
    events = [
        failure("a1", ago=timedelta(hours=1), entity_id="ticketing-webhook"),
        failure("a2", ago=timedelta(hours=2), entity_id="ticketing-webhook"),
        failure("b1", ago=timedelta(hours=3), entity_id="payments-webhook"),
    ]

    assert RepeatedIntegrationFailureRule(NOW).evaluate(events) == []


def test_recovery_after_the_run_clears_the_risk() -> None:
    events = make_run(FAILURE_THRESHOLD) + [recovery("rec", ago=timedelta(minutes=10))]

    assert RepeatedIntegrationFailureRule(NOW).evaluate(events) == []


def test_failures_after_a_recovery_raise_again() -> None:
    events = [
        recovery("rec", ago=timedelta(hours=10)),
        failure("f1", ago=timedelta(hours=3)),
        failure("f2", ago=timedelta(hours=2)),
        failure("f3", ago=timedelta(hours=1)),
    ]

    risks = RepeatedIntegrationFailureRule(NOW).evaluate(events)

    assert len(risks) == 1
    assert risks[0].event_ids == ["f1", "f2", "f3"]


def test_a_recovery_before_the_run_does_not_clear_it() -> None:
    events = [recovery("rec", ago=timedelta(days=2))] + make_run(FAILURE_THRESHOLD)

    assert len(RepeatedIntegrationFailureRule(NOW).evaluate(events)) == 1


def test_failures_outside_the_window_are_ignored() -> None:
    events = [
        failure(f"f{i}", ago=WINDOW + timedelta(hours=i + 1)) for i in range(FAILURE_THRESHOLD)
    ]

    assert RepeatedIntegrationFailureRule(NOW).evaluate(events) == []


def test_the_window_boundary_is_inclusive() -> None:
    events = [
        failure("edge", ago=WINDOW),
        failure("f2", ago=timedelta(hours=2)),
        failure("f3", ago=timedelta(hours=1)),
    ]

    risks = RepeatedIntegrationFailureRule(NOW).evaluate(events)

    assert len(risks) == 1
    assert "edge" in risks[0].event_ids


def test_evidence_is_ordered_oldest_first() -> None:
    events = [
        failure("newest", ago=timedelta(hours=1)),
        failure("oldest", ago=timedelta(hours=5)),
        failure("middle", ago=timedelta(hours=3)),
    ]

    risks = RepeatedIntegrationFailureRule(NOW).evaluate(events)

    assert risks[0].event_ids == ["oldest", "middle", "newest"]


def test_a_run_at_the_threshold_is_high() -> None:
    risks = RepeatedIntegrationFailureRule(NOW).evaluate(make_run(FAILURE_THRESHOLD))

    assert risks[0].severity is RiskSeverity.HIGH


def test_a_large_run_is_critical() -> None:
    risks = RepeatedIntegrationFailureRule(NOW).evaluate(make_run(ESCALATION_COUNT))

    assert risks[0].severity is RiskSeverity.CRITICAL


def test_risks_are_ordered_most_failures_first() -> None:
    events = [
        failure(f"tick{i}", ago=timedelta(hours=i + 1), entity_id="ticketing-webhook")
        for i in range(FAILURE_THRESHOLD)
    ] + [
        failure(f"pay{i}", ago=timedelta(hours=i + 1), entity_id="payments-webhook")
        for i in range(ESCALATION_COUNT)
    ]

    risks = RepeatedIntegrationFailureRule(NOW).evaluate(events)

    assert [len(risk.event_ids) for risk in risks] == [ESCALATION_COUNT, FAILURE_THRESHOLD]


def test_detection_is_deterministic() -> None:
    events = make_run(FAILURE_THRESHOLD)
    rule = RepeatedIntegrationFailureRule(NOW)

    assert rule.evaluate(events) == rule.evaluate(events)


def test_rule_plugs_into_the_detector() -> None:
    risks = detect_risks(make_run(FAILURE_THRESHOLD), [RepeatedIntegrationFailureRule(NOW)])

    assert [risk.rule for risk in risks] == ["repeated_integration_failure"]


def test_matches_the_sample_ticketing_integration() -> None:
    # The synthetic sample day has the ticketing webhook fail three times and
    # then recover. Judged a few hours later the failures are well inside the
    # window, so it is the recovery, not the clock, that must clear the run.
    from opsbrief.samples import load_sample_events

    now = datetime(2026, 7, 29, 18, 0, tzinfo=UTC)
    events = [
        Event.from_input(payload).model_copy(update={"id": f"s{i}"})
        for i, payload in enumerate(load_sample_events())
    ]

    assert RepeatedIntegrationFailureRule(now).evaluate(events) == []

    # Drop the recovery and the same three in-window failures raise a risk,
    # proving the empty result above is the recovery clearing the run.
    without_recovery = [event for event in events if event.status is not EventStatus.RESOLVED]
    risks = RepeatedIntegrationFailureRule(now).evaluate(without_recovery)

    assert len(risks) == 1
    assert risks[0].event_ids == ["s6", "s7", "s8"]
