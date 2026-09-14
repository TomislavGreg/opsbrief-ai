"""Tests for fitting rendered prompt material into a character budget."""

from opsbrief.prompt_budget import Section, render_budgeted


def omission(label: str):
    """Build an omission-note renderer for a section labelled ``label``."""

    def note(shown: int, total: int) -> str:
        return f"({total - shown} of {total} {label} omitted; showing {shown})"

    return note


def section(key: str, items, *, header=None, none_line=None) -> Section:
    """Build a section with sensible default header and none-line for ``key``."""
    return Section(
        key=key,
        header=header or f"{key}:",
        items=list(items),
        none_line=none_line or f"{key}: none.",
        omission_note=omission(key),
    )


def test_a_document_within_budget_is_rendered_whole_and_reports_complete() -> None:
    preamble = ["Header line.", "Second line."]
    sections = [section("risks", ["- a", "- b"]), section("events", ["- x"])]
    trailer = [["Notes:", "- something"]]

    result = render_budgeted(preamble, sections, trailer, budget=10_000)

    assert not result.truncated
    assert result.fit("risks").shown == 2
    assert result.fit("events").shown == 1
    # The blocks are blank-line separated, exactly as an untrimmed render.
    assert result.text == (
        "Header line.\nSecond line.\n\nrisks:\n- a\n- b\n\nevents:\n- x\n\nNotes:\n- something"
    )


def test_an_empty_section_renders_its_none_line() -> None:
    result = render_budgeted(["Head."], [section("risks", [])], budget=10_000)

    assert "risks: none." in result.text
    assert result.fit("risks").total == 0
    assert not result.fit("risks").truncated


def test_oversized_material_is_trimmed_to_whole_items_within_budget() -> None:
    items = [f"- item {i:04d} with some padding text" for i in range(400)]
    result = render_budgeted(["Head."], [section("risks", items)], budget=1_000)

    assert len(result.text) <= 1_000
    fit = result.fit("risks")
    assert fit.truncated
    assert 0 < fit.shown < 400
    # Every kept item line is whole: none was cut mid-line.
    kept = [line for line in result.text.splitlines() if line.startswith("- item ")]
    assert kept == items[: fit.shown]
    assert all(line in items for line in kept)


def test_a_trimmed_section_discloses_the_omission_in_the_material() -> None:
    items = [f"- item {i:04d} padding padding padding" for i in range(400)]
    result = render_budgeted(["Head."], [section("risks", items)], budget=1_000)

    fit = result.fit("risks")
    assert f"({fit.omitted} of {fit.total} risks omitted; showing {fit.shown})" in result.text


def test_the_preamble_and_trailer_survive_a_tight_budget() -> None:
    items = [f"- item {i:04d} padding padding padding" for i in range(400)]
    preamble = ["Incident: something", "Status: open"]
    trailer = [["Resolution: fixed it by restarting the sync"]]
    result = render_budgeted(preamble, [section("timeline", items)], trailer, budget=900)

    assert len(result.text) <= 900
    assert "Incident: something" in result.text
    assert "Status: open" in result.text
    # The trailing resolution note is reserved before the timeline is filled, so it
    # is never the thing that gets dropped.
    assert "Resolution: fixed it by restarting the sync" in result.text
    assert result.fit("timeline").truncated


def test_earlier_sections_keep_priority_over_later_ones() -> None:
    risks = [f"- risk {i:03d} aaaaaaaaaaaaaaaaaaaa" for i in range(200)]
    events = [f"- event {i:03d} bbbbbbbbbbbbbbbbbb" for i in range(200)]
    result = render_budgeted(
        ["Head."], [section("risks", risks), section("events", events)], budget=1_200
    )

    assert len(result.text) <= 1_200
    # Risks come first, so they are filled before events get any room.
    assert result.fit("risks").shown > 0
    assert result.fit("risks").shown >= result.fit("events").shown


def test_exactly_at_the_limit_is_not_trimmed() -> None:
    full = render_budgeted(["Head."], [section("risks", ["- a", "- b"])], budget=10_000)
    exact = len(full.text)

    result = render_budgeted(["Head."], [section("risks", ["- a", "- b"])], budget=exact)

    assert not result.truncated
    assert result.text == full.text


def test_multibyte_unicode_items_stay_within_the_character_budget() -> None:
    items = [f"- {'é中🚀' * 5} {i:03d}" for i in range(300)]
    result = render_budgeted(["Head."], [section("risks", items)], budget=800)

    assert len(result.text) <= 800
    fit = result.fit("risks")
    assert fit.truncated
    kept = [line for line in result.text.splitlines() if line.startswith("- ")]
    assert kept == items[: fit.shown]


def test_many_short_records_are_fit_deterministically() -> None:
    items = [f"- {i}" for i in range(1_000)]
    first = render_budgeted(["Head."], [section("risks", items)], budget=500)
    second = render_budgeted(["Head."], [section("risks", items)], budget=500)

    assert first.text == second.text
    assert len(first.text) <= 500
    assert first.fit("risks").truncated
