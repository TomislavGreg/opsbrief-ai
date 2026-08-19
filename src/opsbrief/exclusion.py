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
#: changing the deterministic picture behind it.
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


def normalise_excluded_fields(fields: Iterable[str]) -> frozenset[str]:
    """Return ``fields`` lowercased and stripped, with blanks dropped.

    Every remaining name must be one of :data:`EXCLUDABLE_CONTEXT_FIELDS`; an
    unknown field raises :class:`ValueError` rather than being ignored, so a
    misconfiguration fails loudly at wiring time instead of silently leaving a
    field the operator meant to hold back in the model's view.
    """
    normalised: set[str] = set()
    for field in fields:
        name = field.strip().lower()
        if not name:
            continue
        if name not in EXCLUDABLE_CONTEXT_FIELDS:
            allowed = ", ".join(sorted(EXCLUDABLE_CONTEXT_FIELDS))
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
