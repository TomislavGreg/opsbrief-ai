"""Tests for the command-line brief rendering and generation."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from opsbrief.brief import DailyBrief
from opsbrief.cli import build_parser, render_json, render_text, run
from opsbrief.config import get_settings
from opsbrief.events import Event, EventInput
from opsbrief.risks import Risk, RiskSeverity
from opsbrief.storage import EventStore


def make_brief(**overrides: object) -> DailyBrief:
    """Return a daily brief with sensible defaults, overridable per test."""
    fields: dict[str, object] = {
        "generated_at": datetime(2026, 8, 11, 9, 30, tzinfo=UTC),
        "summary": "One integration keeps failing; deal with it first.",
        "model": "fake-1",
        "risks": [
            Risk(
                rule="repeated_integration_failure",
                title="Integration ticketing has failed 5 times",
                detail="Integration ticketing has failed 5 times without recovering.",
                severity=RiskSeverity.CRITICAL,
                event_ids=["e17", "e18", "e19"],
            )
        ],
        "notes": [],
        "source_event_ids": ["e17", "e18", "e19"],
    }
    fields.update(overrides)
    return DailyBrief(**fields)


def test_text_shows_the_summary_model_and_risks() -> None:
    text = render_text(make_brief())

    assert "Daily operations brief" in text
    assert "2026-08-11T09:30:00+00:00 by fake-1" in text
    assert "One integration keeps failing; deal with it first." in text
    assert "[critical] Integration ticketing has failed 5 times" in text
    assert "rule: repeated_integration_failure" in text
    assert "events: e17, e18, e19" in text
    assert "Source events: e17, e18, e19" in text


def test_text_records_the_prompt_and_output_versions() -> None:
    text = render_text(make_brief())

    assert "Prompt version brief-prompt/1; output version daily-brief/3" in text


def test_text_states_the_confidence() -> None:
    # A brief with no warnings reads as full confidence.
    assert "Confidence: high" in render_text(make_brief())


def test_text_marks_empty_sections_rather_than_dropping_them() -> None:
    text = render_text(make_brief(risks=[], notes=[], source_event_ids=[], summary=""))

    assert "Risks (most urgent first): none." in text
    assert "Notes: none." in text
    assert "Source events: none." in text
    assert "(none)" in text


def test_text_lists_notes_when_the_picture_is_incomplete() -> None:
    text = render_text(make_brief(notes=["No events recorded."]))

    assert "Notes:" in text
    assert "- No events recorded." in text


def test_json_is_the_briefs_exact_serialisation() -> None:
    brief = make_brief()

    rendered = render_json(brief)
    parsed = json.loads(rendered)

    assert parsed == json.loads(brief.model_dump_json())
    assert parsed["model"] == "fake-1"
    assert parsed["source_event_ids"] == ["e17", "e18", "e19"]
    assert parsed["risks"][0]["rule"] == "repeated_integration_failure"


@pytest.fixture
def database_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Point the settings at a throwaway file database the CLI will open."""
    url = f"sqlite:///{tmp_path / 'cli.db'}"
    monkeypatch.setenv("OPSBRIEF_DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        yield url
    finally:
        get_settings.cache_clear()


def store_overdue_event(url: str) -> str:
    """Store one overdue event in the CLI's database and return its identifier."""
    now = datetime.now(UTC).replace(microsecond=0)
    payload = {
        "source": "tasks",
        "event_type": "task.update",
        "subject": "Safety inspection for North Stand",
        "occurred_at": (now - timedelta(hours=6)).isoformat(),
        "due_at": (now - timedelta(hours=2)).isoformat(),
    }
    event = Event.from_input(EventInput(**payload))
    with EventStore.open(url) as store:
        store.add(event)
    return event.id


def test_default_format_is_a_text_brief_over_the_stored_events(
    database_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    event_id = store_overdue_event(database_url)

    exit_code = run([])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Daily operations brief" in out
    assert "overdue_work" in out
    assert event_id in out


def test_json_format_emits_the_briefs_serialisation(
    database_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    event_id = store_overdue_event(database_url)

    exit_code = run(["--format", "json"])

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["risks"][0]["rule"] == "overdue_work"
    assert event_id in parsed["source_event_ids"]
    assert parsed["model"] == "fake-1"


def test_empty_store_still_produces_a_brief_that_says_so(
    database_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = run([])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Risks (most urgent first): none." in out
    assert "Source events: none." in out


def store_plain_event(url: str, subject: str) -> str:
    """Store one event that raises no risk and return its identifier."""
    now = datetime.now(UTC).replace(microsecond=0)
    payload = {
        "source": "tasks",
        "event_type": "task.update",
        "subject": subject,
        "occurred_at": (now - timedelta(hours=6)).isoformat(),
    }
    event = Event.from_input(EventInput(**payload))
    with EventStore.open(url) as store:
        store.add(event)
    return event.id


def test_configured_excluded_fields_are_held_back_from_the_model(
    database_url: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The unscripted fake provider echoes the material it is shown, so the summary
    # reveals what the model saw. An excluded field is held back from it.
    store_plain_event(database_url, subject="Steward Jane Doe did not report")
    monkeypatch.setenv("OPSBRIEF_AI_CONTEXT_EXCLUDED_FIELDS", "subject")
    get_settings.cache_clear()

    exit_code = run([])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Steward Jane Doe did not report" not in out
    assert "[excluded]" in out


def test_an_unknown_format_is_rejected() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--format", "yaml"])
