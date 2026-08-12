"""Generating a structured daily brief from an assembled context.

This is where a language model earns its narrow keep: it turns the deterministic
:class:`~opsbrief.brief.schema.BriefContext` into a readable summary. It does no
more than that. The risks, the notes and the source event IDs a reader acts on
are carried straight over from the context; the model only phrases the picture,
and its output is treated as untrusted — constrained to a bounded, single-line
summary that carries no authority to invent a risk or an event.

The material the model is shown is rendered here, deterministically, from the
context, so the same context and the same provider always produce the same
request. What the model returns is validated and constrained before it becomes
part of a brief, exactly as any other external data would be.
"""

import re
from collections.abc import Sequence

from opsbrief.ai import AIProvider, AIProviderError, CompletionRequest
from opsbrief.ai.schema import MAX_PROMPT_LENGTH
from opsbrief.brief.schema import (
    BRIEF_OUTPUT_VERSION,
    BRIEF_PROMPT_VERSION,
    MAX_SUMMARY_LENGTH,
    BriefContext,
    DailyBrief,
    EventDigest,
)
from opsbrief.risks import Risk

#: The task the model performs, phrased by the service. It asks only for prose:
#: the model summarises the picture and never decides what it contains. Changing
#: this text, or the context rendering below, is a change of prompt: bump
#: :data:`~opsbrief.brief.schema.BRIEF_PROMPT_VERSION` when it happens.
DEFAULT_INSTRUCTIONS = (
    "You are writing a daily operations brief for a duty manager. Using only the "
    "operational picture provided, write a short, plain summary of the current "
    "situation and what most needs attention. Do not invent events, risks or "
    "numbers beyond those given, and do not include identifiers."
)

_WHITESPACE = re.compile(r"\s+")


def _constrain_summary(text: str) -> str:
    """Reduce untrusted model text to a bounded, single-line summary.

    Whitespace is collapsed so injected line breaks or padding cannot shape the
    brief, and the result is truncated to :data:`MAX_SUMMARY_LENGTH`, so a
    provider can never make a brief's summary grow without bound.
    """
    collapsed = _WHITESPACE.sub(" ", text).strip()
    if len(collapsed) <= MAX_SUMMARY_LENGTH:
        return collapsed
    return collapsed[:MAX_SUMMARY_LENGTH].rstrip()


def _render_risk(risk: Risk) -> str:
    """Render one risk as a single deterministic line of material."""
    events = ", ".join(risk.event_ids)
    return f"- [{risk.severity.value}] {risk.title} ({risk.rule}; events: {events})"


def _render_event(digest: EventDigest) -> str:
    """Render one recent event as a single deterministic line of material."""
    occurred = digest.occurred_at.isoformat()
    status = digest.status.value if digest.status is not None else "unknown"
    return (
        f"- {occurred} [{digest.severity.value}] {digest.source} "
        f"{digest.event_type}: {digest.subject} (status: {status})"
    )


def _render_section(title: str, lines: Sequence[str]) -> list[str]:
    """Render a titled block, or a plain 'none' line when it is empty."""
    if not lines:
        return [f"{title}: none."]
    return [f"{title}:", *lines]


def render_context(context: BriefContext) -> str:
    """Render a brief context as the plain-text material shown to the model.

    The rendering is deterministic and bounded: the context is already bounded,
    and the result is capped at :data:`MAX_PROMPT_LENGTH` so the request the
    provider receives is always well-formed, whatever the context holds.
    """
    lines: list[str] = [
        f"Operational picture as of {context.generated_at.isoformat()}.",
        f"{context.event_count} events recorded.",
        "",
        *_render_section("Risks (most urgent first)", [_render_risk(r) for r in context.risks]),
        "",
        *_render_section(
            "Recent events (newest first)", [_render_event(e) for e in context.recent_events]
        ),
    ]
    if context.notes:
        lines += ["", *_render_section("Notes", [f"- {note}" for note in context.notes])]
    rendered = "\n".join(lines)
    if len(rendered) > MAX_PROMPT_LENGTH:
        return rendered[:MAX_PROMPT_LENGTH].rstrip()
    return rendered


def generate_brief(
    context: BriefContext,
    provider: AIProvider,
    *,
    instructions: str = DEFAULT_INSTRUCTIONS,
    max_output_tokens: int = 512,
) -> DailyBrief:
    """Turn an assembled context into a daily brief, phrased by ``provider``.

    The model is shown the rendered context and asked to summarise it; what it
    returns is constrained to a bounded, single-line summary. The brief's
    structured facts — the risks, the notes and the source event IDs — are taken
    from ``context`` unchanged, so the model rephrases the picture but never
    changes what it says.

    The model is a phrasing layer, not the product, so it is never allowed to
    fail the brief. When it returns no usable summary, or when the provider
    cannot produce one at all (a transport error, a timeout, an unparseable
    reply), the brief is still produced from the deterministic picture and a note
    records which gap occurred. The brief records the prompt and output versions
    it was produced with, so a summary traces to the exact prompt behind it and a
    consumer can detect a change in either.
    """
    request = CompletionRequest(
        instructions=instructions,
        input=render_context(context),
        max_output_tokens=max_output_tokens,
    )
    notes = list(context.notes)
    try:
        response = provider.complete(request)
    except AIProviderError:
        # The provider is only a phrasing layer, so an outage degrades the brief
        # to the deterministic picture rather than failing the request. The model
        # is recorded as the provider that was asked, so the gap stays traceable.
        summary = ""
        model = provider.name
        notes.append(
            "The model was unavailable, so the brief reports the deterministic picture only."
        )
    else:
        summary = _constrain_summary(response.text)
        model = response.model
        if not summary:
            notes.append(
                "The model returned no summary; the brief reports the deterministic picture only."
            )

    return DailyBrief(
        generated_at=context.generated_at,
        summary=summary,
        model=model,
        output_version=BRIEF_OUTPUT_VERSION,
        prompt_version=BRIEF_PROMPT_VERSION,
        risks=context.risks,
        notes=notes,
        source_event_ids=context.source_event_ids,
    )
