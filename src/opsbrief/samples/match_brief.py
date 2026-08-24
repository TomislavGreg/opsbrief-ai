"""A worked match-operations daily brief example.

This builds on the sports-operations match-day fixture: it turns those events
into stored events, assembles the deterministic brief context at a fixed
match-day instant and phrases it with a scripted fake provider, so the whole
risk-to-brief pipeline can be shown over realistic match-operations material
without a database, a running server or a real model.

The example is deterministic. The reference instant is fixed at
:data:`SAMPLE_MATCH_BRIEF_AT`, the events carry stable ids, and the default
provider returns :data:`SAMPLE_MATCH_BRIEF_SUMMARY` verbatim, so the same call
always yields the same brief. The summary is illustrative phrasing of the kind a
duty manager would read; the risks, the source event ids and the confidence
underneath it are the real deterministic picture the service decides.
"""

from datetime import UTC, datetime

from opsbrief.ai import AIProvider, FakeAIProvider
from opsbrief.brief import DailyBrief, build_brief_context, generate_brief
from opsbrief.samples import load_sample_match_stored_events

#: The instant the example brief is judged against: early afternoon on the match
#: day the fixture describes. Every fixture event has occurred by now, and the
#: risk rules recognise the overdue pitch inspection, the blocked scoreboard
#: calibration and the repeatedly failing broadcast feed at this moment.
SAMPLE_MATCH_BRIEF_AT = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)

#: An illustrative one-line summary for the example brief, in a duty manager's
#: voice. It is returned verbatim by the default fake provider so the example
#: reads naturally and stays deterministic; the deterministic picture a reader
#: acts on comes from the context, not this text.
SAMPLE_MATCH_BRIEF_SUMMARY = (
    "The broadcast feed to the host truck has failed four times without recovering "
    "and the pre-match pitch inspection is overdue, while the giant screen scoreboard "
    "calibration is blocked on a vendor engineer and crowd density is building at the "
    "north turnstiles. Restore the broadcast feed and clear the pitch sign-off before "
    "kickoff."
)


def build_sample_match_brief(
    provider: AIProvider | None = None,
    *,
    at: datetime = SAMPLE_MATCH_BRIEF_AT,
) -> DailyBrief:
    """Build the worked match-operations daily brief over the match-day fixture.

    The fixture is loaded as stored events, the deterministic context is
    assembled at ``at`` and the brief is phrased by ``provider``. When no provider
    is given a fake one scripted with :data:`SAMPLE_MATCH_BRIEF_SUMMARY` is used,
    so the example is fully offline and reproducible; pass a provider to phrase the
    same deterministic picture differently. The risks, the source event ids and
    the confidence come from the context regardless of the provider, so the
    example always traces back to the fixture's events.
    """
    events = load_sample_match_stored_events()
    context = build_brief_context(events, at)
    if provider is None:
        provider = FakeAIProvider(responses=[SAMPLE_MATCH_BRIEF_SUMMARY])
    return generate_brief(context, provider)


__all__ = [
    "SAMPLE_MATCH_BRIEF_AT",
    "SAMPLE_MATCH_BRIEF_SUMMARY",
    "build_sample_match_brief",
]
