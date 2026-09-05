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

from opsbrief.api.dependencies import (
    AIProviderDependency,
    EventStoreDependency,
    ExcludedAIContextFieldsDependency,
)
from opsbrief.audit import GenerationAudit
from opsbrief.brief import DailyBrief
from opsbrief.services import report_brief_audit, report_daily_brief

router = APIRouter(prefix="/brief", tags=["brief"])


@router.get(
    "",
    response_model=DailyBrief,
    summary="Generate the current daily operations brief",
    response_description="The current brief: a model summary over the deterministic picture.",
)
def read_brief(
    store: EventStoreDependency,
    provider: AIProviderDependency,
    excluded_fields: ExcludedAIContextFieldsDependency,
) -> DailyBrief:
    """Return the daily brief across the stored events, most urgent risks first.

    The canonical risk rules and a bounded recent-events view are assembled over
    the whole event history at the moment of the request, and the configured
    provider phrases that picture into a short summary. The reference instant is
    part of the answer, because the picture is judged against a moment in time.
    Everything a reader acts on — the prioritized risks, the notes on where the
    picture is incomplete, and the source event IDs every claim traces back to —
    comes from the deterministic context; only the summary comes from the model,
    and it is constrained as untrusted output. Any event fields a deployment holds
    back through ``OPSBRIEF_AI_CONTEXT_EXCLUDED_FIELDS`` are kept out of the
    material the model is shown, without changing that deterministic picture.
    """
    return report_daily_brief(store, datetime.now(UTC), provider, excluded_fields=excluded_fields)


@router.get(
    "/audit",
    response_model=GenerationAudit,
    summary="Audit the current daily operations brief",
    response_description="A provenance record of the current brief: what it came from and by.",
)
def read_brief_audit(
    store: EventStoreDependency,
    provider: AIProviderDependency,
    excluded_fields: ExcludedAIContextFieldsDependency,
) -> GenerationAudit:
    """Return a provenance record of the current daily brief.

    The brief is generated over the whole event history at the moment of the
    request, the same way ``GET /brief`` generates it, and projected into a compact
    audit record: what it was produced from (its source event IDs, and any cited id
    that no longer resolves) and by (the model that phrased it and the prompt and
    output versions), together with the confidence and warning codes it reported.
    The record is a pure projection of the brief, so it holds no model involvement
    of its own beyond the summary the brief already carried and never disagrees with
    the brief it describes. It is meant to be logged or persisted as a small,
    self-contained provenance trail, uniform with the incident-summary audit.
    """
    return report_brief_audit(store, datetime.now(UTC), provider, excluded_fields=excluded_fields)
