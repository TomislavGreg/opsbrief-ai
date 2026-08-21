"""Confidence and missing-data warnings for generated output.

A daily brief and an incident summary are only as trustworthy as the material
behind them. Some of the picture may be missing (a cited event that no longer
resolves, older events omitted because the view is bounded) or unphrased (the
model was unavailable, or returned nothing). Rather than leave a reader to infer
that from prose, a generated output states it plainly: a structured list of
:class:`GenerationWarning`, each naming a machine-readable :class:`WarningCode`
alongside the same human message the notes already carry, and a single
:class:`Confidence` level summarising how much of the picture stands.

Both are deterministic and hold no model involvement, exactly like the evidence
they describe: the same material always yields the same warnings and the same
confidence. Confidence is a pure function of the warnings present, so it never
disagrees with them, and a consumer can branch on a code or a level instead of
matching text.
"""

from collections.abc import Iterable
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class WarningCode(StrEnum):
    """A machine-readable kind of gap in a generated output's picture.

    Each code names one way the picture is incomplete or unphrased, so a consumer
    can act on the specific gap rather than parse the human message beside it.
    """

    #: No operational events were recorded, so a brief has no source data at all.
    NO_EVENTS = "no_events"
    #: No risks were detected across the events considered. Informational: an
    #: all-clear picture, so it does not lower confidence on its own.
    NO_RISKS = "no_risks"
    #: The recent-events view is bounded, so older events are omitted from it.
    EVENTS_OMITTED = "events_omitted"
    #: One or more cited events no longer resolve to a stored record.
    MISSING_EVENTS = "missing_events"
    #: No cited event resolved, so an incident summary has no timeline to describe.
    NO_TIMELINE = "no_timeline"
    #: The provider was unavailable, so the output carries the deterministic
    #: picture with no model-phrased summary.
    MODEL_UNAVAILABLE = "model_unavailable"
    #: The provider returned no usable summary, so the output carries the
    #: deterministic picture with an empty summary.
    EMPTY_SUMMARY = "empty_summary"


class Confidence(StrEnum):
    """How much of a generated output's picture stands, at a glance.

    The level is derived from the warnings present, so it always agrees with them:
    a picture with no gaps is ``HIGH``, one merely partial or unphrased is
    ``MEDIUM``, one missing cited evidence is ``LOW``, and one with no source data
    to describe at all is ``NONE``.
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class GenerationWarning(BaseModel):
    """One structured warning about a gap in a generated output's picture.

    A warning pairs a machine-readable ``code`` with the same human ``message`` the
    output's notes carry, so a consumer can branch on the code while a reader still
    sees the explanation. It is produced deterministically from the material, never
    by a model.
    """

    model_config = ConfigDict(extra="forbid")

    code: WarningCode = Field(
        description="Machine-readable kind of the gap the warning reports.",
    )
    message: str = Field(
        min_length=1,
        max_length=500,
        description="Human-readable explanation of the gap, the same text the notes carry.",
    )


#: Codes that leave no source data to describe: confidence is then ``NONE``.
_NO_DATA_CODES = frozenset({WarningCode.NO_EVENTS, WarningCode.NO_TIMELINE})
#: Codes that mean the cited evidence itself has a gap: confidence is then ``LOW``.
_MISSING_EVIDENCE_CODES = frozenset({WarningCode.MISSING_EVENTS})
#: Codes that mean the picture stands but is partial or unphrased: ``MEDIUM``.
_PARTIAL_CODES = frozenset(
    {
        WarningCode.EVENTS_OMITTED,
        WarningCode.MODEL_UNAVAILABLE,
        WarningCode.EMPTY_SUMMARY,
    }
)


def assess_confidence(warnings: Iterable[GenerationWarning]) -> Confidence:
    """Return the confidence a set of warnings implies, most severe gap winning.

    The assessment is a pure function of the warning codes, so it never disagrees
    with the warnings a reader sees. A code that leaves no source data at all
    (:data:`WarningCode.NO_EVENTS`, :data:`WarningCode.NO_TIMELINE`) yields
    ``NONE``; a gap in the cited evidence (:data:`WarningCode.MISSING_EVENTS`)
    yields ``LOW``; a picture that stands but is bounded or unphrased yields
    ``MEDIUM``; and a picture with no gap at all yields ``HIGH``. An informational
    code such as :data:`WarningCode.NO_RISKS` does not lower confidence, so an
    all-clear brief stays ``HIGH``.
    """
    codes = {warning.code for warning in warnings}
    if codes & _NO_DATA_CODES:
        return Confidence.NONE
    if codes & _MISSING_EVIDENCE_CODES:
        return Confidence.LOW
    if codes & _PARTIAL_CODES:
        return Confidence.MEDIUM
    return Confidence.HIGH
