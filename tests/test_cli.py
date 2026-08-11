"""Tests for the command-line brief rendering."""

import json
from datetime import UTC, datetime

from opsbrief.brief import DailyBrief
from opsbrief.cli import render_json, render_text
from opsbrief.risks import Risk, RiskSeverity


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
