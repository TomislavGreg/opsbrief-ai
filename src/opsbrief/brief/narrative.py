"""A deterministic offline narrative for a daily brief.

The default build runs offline, with no language model. Rather than echo the prompt
material back (which reads as scaffolding, not a summary) or leave the summary
empty, the service composes a short narrative from the structured picture itself.

The narrative is a pure function of the :class:`~opsbrief.brief.schema.BriefContext`:
the same context always yields the same sentence, and it can never contradict the
risks it stands beside, because it is built from them. It states the actual
prioritised picture, how many risks stand, the most urgent one and the first step
to take, or an all-clear when there are none, and carries no identifiers or prompt
scaffolding. No model takes part, so the summary it produces is trustworthy by
construction, which is what :data:`~opsbrief.verification.SummaryStatus.DETERMINISTIC`
records.
"""

from collections.abc import Container

from opsbrief.brief.schema import BriefContext
from opsbrief.exclusion import shown_risk_title


def _count(n: int, noun: str) -> str:
    """Return ``n`` with ``noun`` pluralised the plain English way."""
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def compose_brief_narrative(
    context: BriefContext, *, excluded_fields: Container[str] = frozenset()
) -> str:
    """Compose a short, deterministic summary of ``context``.

    The sentence restates the structured picture: an empty store, an all-clear when
    no risks stand, or the count of risks with the most urgent one and its first
    suggested action. It is derived only from the context, so equal inputs yield
    equal text and it never disagrees with the risks it summarises. Fields named in
    ``excluded_fields`` are held back the same way they are held back from a model,
    so a deployment that excludes ``subject`` does not see it reappear in the prose.
    """
    if context.event_count == 0:
        return "No operational events have been recorded, so there is nothing to report yet."
    if not context.risks:
        return (
            f"No active risks across {_count(context.event_count, 'event')}; "
            "nothing needs attention right now."
        )

    top = context.risks[0]
    title = shown_risk_title(top.title, excluded_fields)
    sentence = (
        f"{_count(len(context.risks), 'active risk')} across "
        f"{_count(context.event_count, 'event')}, most urgent: "
        f"{title} ({top.severity.value})."
    )
    if context.next_actions:
        sentence += f" Suggested first step: {context.next_actions[0].action}"
    return sentence
