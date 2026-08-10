"""The daily-brief endpoint.

The router stays thin: it fixes the reference instant at request time and hands
the store and the configured provider to the service, which reads the events,
assembles the deterministic context and asks the provider to phrase it. The
division of labour lives in the brief package, not here — the model only phrases
a picture the service has already decided, and its output is treated as
untrusted.
"""

from datetime import UTC, datetime

from fastapi import APIRouter

from opsbrief.api.dependencies import AIProviderDependency, EventStoreDependency
from opsbrief.brief import DailyBrief
from opsbrief.services import report_daily_brief

router = APIRouter(prefix="/brief", tags=["brief"])


@router.get(
    "",
    response_model=DailyBrief,
    summary="Generate the current daily operations brief",
    response_description="The current brief: a model summary over the deterministic picture.",
)
def read_brief(store: EventStoreDependency, provider: AIProviderDependency) -> DailyBrief:
    """Return the daily brief across the stored events, most urgent risks first.

    The canonical risk rules and a bounded recent-events view are assembled over
    the whole event history at the moment of the request, and the configured
    provider phrases that picture into a short summary. The reference instant is
    part of the answer, because the picture is judged against a moment in time.
    Everything a reader acts on — the prioritized risks, the notes on where the
    picture is incomplete, and the source event IDs every claim traces back to —
    comes from the deterministic context; only the summary comes from the model,
    and it is constrained as untrusted output.
    """
    return report_daily_brief(store, datetime.now(UTC), provider)
