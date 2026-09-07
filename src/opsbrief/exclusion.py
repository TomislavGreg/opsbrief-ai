"""Excluding event fields from the material shown to a language model.

Redaction masks sensitive *values* in an event's ``metadata`` before the event
is stored. This is a second, complementary control that narrows what a model may
see once an event is already stored: a deployment can name event fields that are
held back from the plain-text material a provider is shown, without touching the
stored event or the deterministic structured output a reader acts on.

The two controls are deliberately different. Redaction happens once, at
ingestion, and changes what is kept. Exclusion happens every time material is
rendered for a model, and changes only what the model is shown: the risks, the
source event IDs and the digests the service reasons over are unchanged, so a
brief or an incident summary still traces back to the same evidence. Like
redaction, exclusion is deterministic and rule-based, and it keeps the field's
label with a visible :data:`EXCLUSION_PLACEHOLDER` so a reader of the material
sees the field was present and withheld rather than silently dropped.
"""

from collections.abc import Container, Iterable

#: What an excluded field's value is replaced with in rendered material. It is
#: visible on purpose, exactly as a redacted value is: a reader of the prompt
#: sees the field was present and held back rather than absent.
EXCLUSION_PLACEHOLDER = "[excluded]"

#: The event fields a deployment may hold back from the material a model is shown.
#: These are exactly the fields the brief and incident renderers describe an event
#: with; an event's ``id`` and ``metadata`` are never rendered into that material,
#: so they are not listed here. Excluding a field narrows the model's view without
#: changing the deterministic picture behind it, wherever the field appears: not
#: only in a plain event line, but in any prose derived from it, such as a risk
#: title phrased from a ``subject`` or an incident span derived from ``occurred_at``.
EXCLUDABLE_CONTEXT_FIELDS: frozenset[str] = frozenset(
    {
        "source",
        "event_type",
        "subject",
        "severity",
        "status",
        "occurred_at",
    }
)

#: A control, separate from the event fields, that holds an incident's free-form
#: operator text (its title and resolution note) back from the model. Those are
#: authored by an operator rather than derived from an event, so field exclusion
#: does not reach them; a deployment that must keep them out of a model's view names
#: this control. It is an opt-out: by default the free-form text is shown, because
#: it is authorised operational content.
INCIDENT_FREE_TEXT_CONTROL = "incident_free_text"

#: Everything a deployment may name in ``OPSBRIEF_AI_CONTEXT_EXCLUDED_FIELDS``: the
#: event fields plus the free-form-text control.
EXCLUDABLE_CONTEXT_NAMES: frozenset[str] = EXCLUDABLE_CONTEXT_FIELDS | {INCIDENT_FREE_TEXT_CONTROL}


def normalise_excluded_fields(fields: Iterable[str]) -> frozenset[str]:
    """Return ``fields`` lowercased and stripped, with blanks dropped.

    Every remaining name must be one of :data:`EXCLUDABLE_CONTEXT_NAMES` (an event
    field, or the :data:`INCIDENT_FREE_TEXT_CONTROL`); an unknown name raises
    :class:`ValueError` rather than being ignored, so a misconfiguration fails
    loudly at wiring time instead of silently leaving something the operator meant
    to hold back in the model's view.
    """
    normalised: set[str] = set()
    for field in fields:
        name = field.strip().lower()
        if not name:
            continue
        if name not in EXCLUDABLE_CONTEXT_NAMES:
            allowed = ", ".join(sorted(EXCLUDABLE_CONTEXT_NAMES))
            raise ValueError(f"unknown AI context field {name!r}; expected one of: {allowed}")
        normalised.add(name)
    return frozenset(normalised)


def shown_value(field: str, value: str, excluded_fields: Container[str]) -> str:
    """Return ``value`` for ``field``, or the placeholder when it is excluded.

    Renderers call this per field so an excluded field's value is replaced by
    :data:`EXCLUSION_PLACEHOLDER` while the surrounding layout stays the same,
    keeping the rendering deterministic and the omission visible.
    """
    if field in excluded_fields:
        return EXCLUSION_PLACEHOLDER
    return value


def shown_risk_title(title: str, excluded_fields: Container[str]) -> str:
    """Return a risk ``title``, or the placeholder when its subject is excluded.

    A risk title is phrased from the event ``subject`` behind it (for example
    "<subject> is overdue"), so a title carries the subject into the prompt even
    though it is not an event line. When ``subject`` is excluded the whole title is
    held back rather than shown, so the excluded value cannot reach the model
    through the risk section. The title is held back as a unit; its text is never
    scanned and rewritten, which would be brittle and could miss transformed values.
    """
    if "subject" in excluded_fields:
        return EXCLUSION_PLACEHOLDER
    return title


def shown_incident_title(title: str, excluded_fields: Container[str]) -> str:
    """Return an incident ``title``, or the placeholder when it is held back.

    An incident title is free-form operator text, but an incident declared from a
    risk is titled from that risk, which is phrased from an event ``subject``. So
    the title is held back when either the ``subject`` is excluded (closing that
    derived path) or the :data:`INCIDENT_FREE_TEXT_CONTROL` opt-out is set. It is
    held back as a unit rather than scanned and rewritten.
    """
    if "subject" in excluded_fields or INCIDENT_FREE_TEXT_CONTROL in excluded_fields:
        return EXCLUSION_PLACEHOLDER
    return title


def shown_free_text(value: str, excluded_fields: Container[str]) -> str:
    """Return free-form incident ``value``, or the placeholder under the opt-out.

    A resolution note is free-form operator text, not derived from an event, so
    field exclusion does not reach it; the :data:`INCIDENT_FREE_TEXT_CONTROL`
    opt-out holds it back when a deployment must keep operator text out of a
    model's view. It is held back as a unit rather than scanned and rewritten.
    """
    if INCIDENT_FREE_TEXT_CONTROL in excluded_fields:
        return EXCLUSION_PLACEHOLDER
    return value
