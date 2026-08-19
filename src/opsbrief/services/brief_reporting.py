"""Assembling a daily brief from the stored events.

The router fixes the reference instant and hands this module the store and the
provider; it reads the whole event history, assembles the deterministic brief
context over it, and asks the provider to phrase the picture. The division of
labour that the brief package enforces is kept intact here: the context — the
risks, the notes and the source event IDs a reader acts on — is built without a
model, and the provider only phrases it, its output treated as untrusted. Reads
never mutate the store.
"""

from collections.abc import Container
from datetime import datetime

from opsbrief.ai import AIProvider
from opsbrief.brief import DailyBrief, build_brief_context, generate_brief
from opsbrief.services.history import read_all_events
from opsbrief.storage import EventStore


def report_daily_brief(
    store: EventStore,
    now: datetime,
    provider: AIProvider,
    *,
    excluded_fields: Container[str] = frozenset(),
) -> DailyBrief:
    """Return the current daily brief across the stored events, phrased by ``provider``.

    The canonical risk rules and the recent-events view are assembled over the
    full event history at ``now``, so the brief is judged against the whole
    picture; ``provider`` then phrases that picture into a summary, which is
    constrained as untrusted output. The brief records ``now`` as the instant it
    was built for, and every risk, note and source event id in it is carried
    straight from the deterministic context.

    Event fields named in ``excluded_fields`` are held back from the material the
    provider is shown, so a deployment can narrow the model's view of recent
    events without changing the deterministic picture behind the brief.
    """
    context = build_brief_context(read_all_events(store), now)
    return generate_brief(context, provider, excluded_fields=excluded_fields)
