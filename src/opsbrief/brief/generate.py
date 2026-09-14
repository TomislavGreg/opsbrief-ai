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
from collections.abc import Callable, Container

from opsbrief.ai import AIProvider, AIProviderError, CompletionRequest
from opsbrief.brief.schema import (
    BRIEF_OUTPUT_VERSION,
    BRIEF_PROMPT_VERSION,
    MAX_SUMMARY_LENGTH,
    BriefContext,
    DailyBrief,
    EventDigest,
)
from opsbrief.exclusion import shown_risk_title, shown_value
from opsbrief.prompt_budget import BudgetedMaterial, Section, render_budgeted
from opsbrief.risks import Risk
from opsbrief.warnings import GenerationWarning, WarningCode

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


def _render_risk(risk: Risk, excluded_fields: Container[str]) -> str:
    """Render one risk as a single deterministic line of material.

    The risk title is phrased from the event subject behind it, so it is held back
    with a visible placeholder when ``subject`` is excluded; the rule and the cited
    event ids, which carry no event field value, are always shown so the model
    still knows a risk of that kind stands over those events. The severity shown is
    the rule's own judgement, not the event's ``severity`` field, so it is not
    affected by excluding that field.
    """
    events = ", ".join(risk.event_ids)
    title = shown_risk_title(risk.title, excluded_fields)
    return f"- [{risk.severity.value}] {title} ({risk.rule}; events: {events})"


def _render_event(digest: EventDigest, excluded_fields: Container[str]) -> str:
    """Render one recent event as a single deterministic line of material.

    Fields named in ``excluded_fields`` are shown as a visible placeholder rather
    than their value, so a deployment can hold a field back from the model without
    changing the layout of the line.
    """
    occurred = shown_value("occurred_at", digest.occurred_at.isoformat(), excluded_fields)
    severity = shown_value("severity", digest.severity.value, excluded_fields)
    source = shown_value("source", digest.source, excluded_fields)
    event_type = shown_value("event_type", digest.event_type, excluded_fields)
    subject = shown_value("subject", digest.subject, excluded_fields)
    status_value = digest.status.value if digest.status is not None else "unknown"
    status = shown_value("status", status_value, excluded_fields)
    return f"- {occurred} [{severity}] {source} {event_type}: {subject} (status: {status})"


def _omission_note(label: str) -> Callable[[int, int], str]:
    """Build the line that discloses how many ``label`` items the budget dropped."""

    def note(shown: int, total: int) -> str:
        return (
            f"({total - shown} more {label} omitted to fit the prompt budget; "
            f"showing {shown} of {total}.)"
        )

    return note


#: The human noun for each budget-fillable section, for the truncation message.
_SECTION_LABELS = {"risks": "risks", "recent_events": "recent events"}


def _truncation_message(material: BudgetedMaterial) -> str:
    """Phrase which sections the prompt budget trimmed, for a note and a warning."""
    parts = [
        f"{fit.shown} of {fit.total} {_SECTION_LABELS.get(fit.key, fit.key)}"
        for fit in material.fits
        if fit.truncated
    ]
    shown = " and ".join(parts)
    return (
        f"The picture was too large for the prompt budget, so the model was shown only "
        f"{shown}; the brief's risks, source events and references remain complete."
    )


def build_brief_material(
    context: BriefContext, *, excluded_fields: Container[str] = frozenset()
) -> BudgetedMaterial:
    """Render a brief context into the material shown to the model, within budget.

    The rendering is deterministic and bounded: the risks and the recent-events
    view are filled into the prompt budget in that priority order, most urgent
    first, dropping whole lines only rather than slicing the text, so an oversized
    picture never reaches the model as a half-written record. A section that had to
    drop lines says so in the material and in the returned fit, so the caller can
    warn that the model saw only part of the picture. Event fields named in
    ``excluded_fields`` are held back with a visible placeholder wherever they
    appear: in the recent-events view, and, for ``subject``, in the risk titles
    phrased from it. The risks, the notes and the source event IDs a reader acts on
    are unchanged: only the model's view is bounded.
    """
    preamble = [
        f"Operational picture as of {context.generated_at.isoformat()}.",
        f"{context.event_count} events recorded.",
    ]
    sections = [
        Section(
            key="risks",
            header="Risks (most urgent first):",
            items=[_render_risk(r, excluded_fields) for r in context.risks],
            none_line="Risks (most urgent first): none.",
            omission_note=_omission_note("risks"),
        ),
        Section(
            key="recent_events",
            header="Recent events (newest first):",
            items=[_render_event(e, excluded_fields) for e in context.recent_events],
            none_line="Recent events (newest first): none.",
            omission_note=_omission_note("recent events"),
        ),
    ]
    trailer_blocks: list[list[str]] = []
    if context.notes:
        trailer_blocks.append(["Notes:", *[f"- {note}" for note in context.notes]])
    return render_budgeted(preamble, sections, trailer_blocks)


def render_context(context: BriefContext, *, excluded_fields: Container[str] = frozenset()) -> str:
    """Render a brief context as the plain-text material shown to the model.

    This is :func:`build_brief_material` reduced to just its text, for callers that
    only need the rendered material and not what the budget had to drop.
    """
    return build_brief_material(context, excluded_fields=excluded_fields).text


def generate_brief(
    context: BriefContext,
    provider: AIProvider,
    *,
    instructions: str = DEFAULT_INSTRUCTIONS,
    max_output_tokens: int = 512,
    excluded_fields: Container[str] = frozenset(),
) -> DailyBrief:
    """Turn an assembled context into a daily brief, phrased by ``provider``.

    The model is shown the rendered context and asked to summarise it; what it
    returns is constrained to a bounded, single-line summary. The brief's
    structured facts — the risks, the notes and the source event IDs — are taken
    from ``context`` unchanged, so the model rephrases the picture but never
    changes what it says. Event fields named in ``excluded_fields`` are held back
    from the material the model is shown, so a deployment can narrow the model's
    view without changing the deterministic picture behind the brief.

    The model is a phrasing layer, not the product, so it is never allowed to
    fail the brief. When it returns no usable summary, or when the provider
    cannot produce one at all (a transport error, a timeout, an unparseable
    reply), the brief is still produced from the deterministic picture and a note
    and a matching warning record which gap occurred. Those warnings, the
    context's own plus any the model added, are summed into the brief's
    ``confidence``, so a reader can weigh a degraded brief at a glance. The brief
    records the prompt and output versions it was produced with, so a summary
    traces to the exact prompt behind it and a consumer can detect a change in
    either.
    """
    material = build_brief_material(context, excluded_fields=excluded_fields)
    request = CompletionRequest(
        instructions=instructions,
        input=material.text,
        max_output_tokens=max_output_tokens,
    )
    notes = list(context.notes)
    warnings = list(context.warnings)
    if material.truncated:
        # The deterministic picture below stays complete; only the model's view was
        # trimmed to fit the prompt budget, so say which parts it did not see.
        message = _truncation_message(material)
        notes.append(message)
        warnings.append(GenerationWarning(code=WarningCode.PROMPT_TRUNCATED, message=message))
    try:
        response = provider.complete(request)
    except AIProviderError:
        # The provider is only a phrasing layer, so an outage degrades the brief
        # to the deterministic picture rather than failing the request. The model
        # is recorded as the provider that was asked, so the gap stays traceable.
        summary = ""
        model = provider.name
        message = "The model was unavailable, so the brief reports the deterministic picture only."
        notes.append(message)
        warnings.append(GenerationWarning(code=WarningCode.MODEL_UNAVAILABLE, message=message))
    else:
        summary = _constrain_summary(response.text)
        model = response.model
        if not summary:
            message = (
                "The model returned no summary; the brief reports the deterministic picture only."
            )
            notes.append(message)
            warnings.append(GenerationWarning(code=WarningCode.EMPTY_SUMMARY, message=message))

    return DailyBrief(
        generated_at=context.generated_at,
        summary=summary,
        model=model,
        output_version=BRIEF_OUTPUT_VERSION,
        prompt_version=BRIEF_PROMPT_VERSION,
        risks=context.risks,
        notes=notes,
        warnings=warnings,
        source_event_ids=context.source_event_ids,
        references=context.references,
        next_actions=context.next_actions,
    )
