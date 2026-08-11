"""Command-line generation of a daily operations brief.

The service already assembles and phrases a daily brief for the HTTP API; this
module renders the same brief for a terminal, so one can be produced without
running the server. Rendering is all this layer does: it does not decide what a
brief contains — that stays with the deterministic context and the rules behind
it — and the model's summary is carried through already constrained. Two shapes
are offered: a human-readable text block and the brief's exact JSON, so the CLI
serves both a reader at a terminal and a script piping the result onward.
"""

from opsbrief.brief import DailyBrief
from opsbrief.risks import Risk


def _render_risk(risk: Risk) -> list[str]:
    """Render one risk as an indented block naming its rule and evidence."""
    return [
        f"  [{risk.severity.value}] {risk.title}",
        f"      rule: {risk.rule}",
        f"      events: {', '.join(risk.event_ids)}",
    ]


def render_text(brief: DailyBrief) -> str:
    """Render a daily brief as a human-readable text block.

    The summary, the prioritized risks, the notes on where the picture is
    incomplete and the source event IDs behind it are all laid out plainly, each
    risk naming the rule and events it traces to. Empty sections say ``none.``
    rather than vanishing, so a reader can tell "nothing to report" from a
    section that was simply left out.
    """
    lines: list[str] = [
        "Daily operations brief",
        f"Generated at {brief.generated_at.isoformat()} by {brief.model}",
        "",
        "Summary:",
        f"  {brief.summary}" if brief.summary else "  (none)",
        "",
    ]

    if brief.risks:
        lines.append("Risks (most urgent first):")
        for risk in brief.risks:
            lines.extend(_render_risk(risk))
    else:
        lines.append("Risks (most urgent first): none.")
    lines.append("")

    if brief.notes:
        lines.append("Notes:")
        lines.extend(f"  - {note}" for note in brief.notes)
    else:
        lines.append("Notes: none.")
    lines.append("")

    if brief.source_event_ids:
        lines.append(f"Source events: {', '.join(brief.source_event_ids)}")
    else:
        lines.append("Source events: none.")

    return "\n".join(lines)


def render_json(brief: DailyBrief) -> str:
    """Render a daily brief as its exact JSON, indented for reading.

    The output is the brief's own serialisation, so a piped consumer sees the
    same fields the HTTP API returns rather than a parallel shape that could
    drift from it.
    """
    return brief.model_dump_json(indent=2)
