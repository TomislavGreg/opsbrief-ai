"""Daily-brief assembly: the deterministic material a brief is built from.

A daily brief is phrased by a language model, but the material behind it is
assembled here, deterministically, from the stored events and the instant the
brief is judged against. No model takes part in that assembly: the context is a
pure function of the evidence, so the model is only ever asked to phrase a
picture the service has already decided.
"""

from opsbrief.brief.actions import (
    DEFAULT_ACTION,
    RECOMMENDED_ACTIONS,
    NextAction,
    suggest_next_actions,
)
from opsbrief.brief.context import DEFAULT_RECENT_EVENTS, build_brief_context
from opsbrief.brief.generate import DEFAULT_INSTRUCTIONS, generate_brief, render_context
from opsbrief.brief.schema import (
    BRIEF_OUTPUT_VERSION,
    BRIEF_PROMPT_VERSION,
    MAX_SUMMARY_LENGTH,
    BriefContext,
    DailyBrief,
    EventDigest,
)
from opsbrief.warnings import Confidence, GenerationWarning, WarningCode

__all__ = [
    "BRIEF_OUTPUT_VERSION",
    "BRIEF_PROMPT_VERSION",
    "DEFAULT_ACTION",
    "DEFAULT_INSTRUCTIONS",
    "DEFAULT_RECENT_EVENTS",
    "MAX_SUMMARY_LENGTH",
    "RECOMMENDED_ACTIONS",
    "BriefContext",
    "Confidence",
    "DailyBrief",
    "EventDigest",
    "GenerationWarning",
    "NextAction",
    "WarningCode",
    "build_brief_context",
    "generate_brief",
    "render_context",
    "suggest_next_actions",
]
