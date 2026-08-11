"""Command-line generation of a daily operations brief.

The service already assembles and phrases a daily brief for the HTTP API; this
module exposes the same generation step on the command line, so a brief can be
produced without running the server. It stays a thin wrapper, exactly as a
router does: it opens the configured event store, hands it and the configured
provider to the reporting service, and renders the resulting brief. Nothing here
decides what a brief contains — that stays with the deterministic context and
the rules behind it — and the model's summary is carried through already
constrained. Two shapes are offered: a human-readable text block and the brief's
exact JSON, so the CLI serves both a reader at a terminal and a script piping
the result onward.
"""

import argparse
from collections.abc import Sequence
from datetime import UTC, datetime

from opsbrief.ai import create_provider
from opsbrief.brief import DailyBrief
from opsbrief.config import get_settings
from opsbrief.risks import Risk
from opsbrief.services import report_daily_brief
from opsbrief.storage import EventStore


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
    risk naming the rule and events it traces to. The header records the model
    that phrased the summary and the prompt and output versions the brief was
    produced with, so a reader can trace it. Empty sections say ``none.`` rather
    than vanishing, so a reader can tell "nothing to report" from a section that
    was simply left out.
    """
    lines: list[str] = [
        "Daily operations brief",
        f"Generated at {brief.generated_at.isoformat()} by {brief.model}",
        f"Prompt version {brief.prompt_version}; output version {brief.output_version}",
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


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser for the ``opsbrief`` command."""
    parser = argparse.ArgumentParser(
        prog="opsbrief",
        description="Generate the current daily operations brief from the stored events.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="How to render the brief: a readable text block (default) or its exact JSON.",
    )
    return parser


def generate() -> DailyBrief:
    """Assemble and phrase the current brief over the configured event store.

    The store and the provider are both taken from the application settings, so
    the CLI reports on the same database the API serves and phrases with the same
    provider. The store is opened for the read and closed again, because a
    command-line run owns no long-lived application to hold it. The reference
    instant is the moment of the run, as it is the moment of the request for the
    API.
    """
    settings = get_settings()
    with EventStore.open(settings.database_url) as store:
        return report_daily_brief(store, datetime.now(UTC), create_provider())


def run(argv: Sequence[str] | None = None) -> int:
    """Generate the brief, print it in the requested format and return an exit code.

    Rendering is chosen by ``--format``; the brief itself is the same one the API
    returns, so the two never disagree. The return value is a process exit code:
    zero, because producing a brief over whatever events are stored is a success
    even when there is nothing to report — that case is a brief that says so, not
    an error.
    """
    args = build_parser().parse_args(argv)
    brief = generate()
    rendered = render_json(brief) if args.format == "json" else render_text(brief)
    print(rendered)
    return 0


def main() -> None:
    """Console-script entry point: run the command and exit with its code."""
    raise SystemExit(run())
