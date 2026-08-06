"""Recognising an integration that keeps failing.

A single integration failure is noise; the same integration failing again and
again is a risk. This rule groups failure events by the integration they concern
and raises a risk once one integration has failed enough times inside a recent
window, without recovering since.

Which events count is decided from the schema the producer already fills in. A
failure is an event whose ``status`` is ``failed``; a recovery is one whose
``status`` is ``resolved``. Both must name the integration they are about through
``entity_id`` — the rule cannot say "the same integration failed repeatedly"
without an identifier to group by, so failures that name no entity are left to
other rules. A recovery that lands after a run of failures clears them, the same
way a resolved status clears overdue work: the manager is shown integrations that
are failing now, not ones that already came back.

The window and the recovery comparison are judged against a reference instant
rather than the wall clock, so the same events and the same instant always
classify the same way, and a test can pin the boundary exactly.
"""

from opsbrief.events import Event, EventStatus

#: An integration's grouping key: the producer, the kind of thing, and its id.
IntegrationKey = tuple[str, str | None, str]


def is_integration_failure(event: Event) -> bool:
    """Return whether ``event`` reports an identifiable integration failure.

    An event counts when its ``status`` is ``failed`` and it names the
    integration it concerns through ``entity_id``. A failure that names no entity
    cannot be attributed to a specific integration, so this rule leaves it alone.
    """
    return event.status == EventStatus.FAILED and event.entity_id is not None


def is_integration_recovery(event: Event) -> bool:
    """Return whether ``event`` reports an identifiable integration recovery.

    An event counts when its ``status`` is ``resolved`` and it names the
    integration it concerns through ``entity_id``, so a recovery can be matched to
    the failures it clears.
    """
    return event.status == EventStatus.RESOLVED and event.entity_id is not None


def integration_key(event: Event) -> IntegrationKey:
    """Return the key identifying the integration ``event`` is about.

    Events sharing a key are treated as the same integration: the same producing
    ``source``, ``entity_type`` and ``entity_id``. The caller is expected to have
    checked that ``entity_id`` is present, which every failure and recovery this
    rule considers has.
    """
    assert event.entity_id is not None  # guaranteed by the failure/recovery checks
    return (event.source, event.entity_type, event.entity_id)
