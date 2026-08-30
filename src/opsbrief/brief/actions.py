"""Deterministic suggested next actions.

A daily brief states the current picture and the risks in it. A suggested next
action goes one step further and names, for each risk, what to do about it. Like
the risks themselves, next actions are deterministic and rule-based: a language
model has no part in deciding them. Each risk maps to a canonical recommended
action by the rule that raised it, and the action carries the same source event
IDs as the risk, so a suggestion traces back to the same evidence.

There is exactly one action per risk, in the order the risks are given, which is
their priority order, so the most pressing action comes first. A rule with no
canonical action falls back to a generic review step rather than being dropped,
so a new rule always yields a usable, if plain, suggestion until a specific one
is written for it.
"""

from pydantic import BaseModel, ConfigDict, Field

from opsbrief.risks import Risk, RiskSeverity
from opsbrief.risks.rules.blocked import RULE_ID as BLOCKED_WORK_RULE
from opsbrief.risks.rules.integration import RULE_ID as REPEATED_INTEGRATION_FAILURE_RULE
from opsbrief.risks.rules.overdue import RULE_ID as OVERDUE_WORK_RULE

#: Canonical recommended action for each risk rule, keyed by the rule's
#: identifier. The text is deterministic operational guidance, not model output,
#: so the same risk always yields the same suggestion.
RECOMMENDED_ACTIONS: dict[str, str] = {
    OVERDUE_WORK_RULE: "Escalate the overdue work and agree a new completion time with its owner.",
    BLOCKED_WORK_RULE: "Clear the blocker: confirm who owns it and what the work is waiting on.",
    REPEATED_INTEGRATION_FAILURE_RULE: (
        "Investigate the failing integration and restore it before dependent work is affected."
    ),
}

#: Fallback action for a risk whose rule has no canonical recommendation yet, so a
#: new rule still yields a usable suggestion rather than none.
DEFAULT_ACTION = "Review this risk, assign an owner and decide the next step."


class NextAction(BaseModel):
    """A recommended action for one risk, traceable to the same evidence.

    Every field is derived from the risk it addresses, never from a model. ``rule``
    names the rule behind the risk, ``event_ids`` carries the risk's source events
    unchanged so the suggestion traces to the same evidence, and ``severity`` is the
    risk's severity so a reader sees how pressing the action is.
    """

    model_config = ConfigDict(extra="forbid")

    action: str = Field(
        min_length=1,
        max_length=500,
        description="The recommended action, deterministic guidance rather than model output.",
    )
    rule: str = Field(
        min_length=1,
        max_length=64,
        description="Identifier of the rule behind the risk this action addresses.",
    )
    title: str = Field(
        min_length=1,
        max_length=200,
        description="The risk this action addresses, so the suggestion reads on its own.",
    )
    severity: RiskSeverity = Field(
        description="Severity of the risk this action addresses, so its urgency is visible.",
    )
    event_ids: list[str] = Field(
        min_length=1,
        description="Source event IDs behind the risk, carried over so the action traces to them.",
    )


def suggest_next_actions(risks: list[Risk]) -> list[NextAction]:
    """Return one suggested next action per risk, in the given order.

    The risks are expected in priority order (most urgent first), and the actions
    follow it, so the most pressing action comes first. Each action is looked up
    from :data:`RECOMMENDED_ACTIONS` by the risk's rule, falling back to
    :data:`DEFAULT_ACTION` for a rule with no canonical action, and carries the
    risk's title, severity and source event IDs so it stays traceable.
    """
    return [
        NextAction(
            action=RECOMMENDED_ACTIONS.get(risk.rule, DEFAULT_ACTION),
            rule=risk.rule,
            title=risk.title,
            severity=risk.severity,
            event_ids=list(risk.event_ids),
        )
        for risk in risks
    ]


__all__ = [
    "DEFAULT_ACTION",
    "RECOMMENDED_ACTIONS",
    "NextAction",
    "suggest_next_actions",
]
