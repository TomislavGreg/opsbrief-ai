"""The risk-list endpoint.

The router stays thin: it fixes the reference instant at request time and hands
the store to the service, which reads the events, runs the rules and ranks the
result. Risk detection itself lives in the risk package, not here.
"""

from datetime import UTC, datetime

from fastapi import APIRouter

from opsbrief.api.dependencies import EventStoreDependency
from opsbrief.risks import RiskList
from opsbrief.services import list_risks

router = APIRouter(prefix="/risks", tags=["risks"])


@router.get(
    "",
    response_model=RiskList,
    summary="List the current operational risks",
    response_description="The current risks, most urgent first, and the instant they were judged.",
)
def read_risks(store: EventStoreDependency) -> RiskList:
    """Return the risks recognised across the stored events, most urgent first.

    Every implemented rule is run over the whole event history at the moment of
    the request, and the risks they raise are ranked by priority. The reference
    instant is part of the answer, because a risk is judged against a moment in
    time, and every risk still cites the rule and the source events behind it.
    """
    return list_risks(store, datetime.now(UTC))
