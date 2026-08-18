"""Redacting sensitive values from operational-event metadata.

Producing systems put free-form detail in an event's ``metadata``, and some of
it may be sensitive: a contact address, a phone number, a credential. This is a
public project that must never hold private or personal data, so such values are
masked before an event is stored rather than kept and hoped to stay unseen.

Redaction is deterministic and rule-based, like risk detection: a metadata key
is sensitive when its name matches a configured term, and its value is then
replaced by :data:`REDACTION_PLACEHOLDER`. No language model takes part, and the
key itself is kept so a reader can still see that the field was present and
masked rather than silently dropped.
"""

from collections.abc import Iterable

from opsbrief.events import Event, EventInput, MetadataValue

#: What a redacted value is replaced with. It is visible on purpose: a reader
#: sees the field was present and masked rather than absent.
REDACTION_PLACEHOLDER = "[redacted]"

#: Metadata key terms treated as sensitive out of the box. A key is matched when
#: one of these appears anywhere in its lowercased name, so ``customer_email`` is
#: caught by ``email`` and ``password_hash`` by ``password``. The set errs on the
#: side of masking, since leaking a value is worse than masking a harmless one.
DEFAULT_SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "email",
        "phone",
        "ssn",
        "credit_card",
    }
)


def _is_sensitive(key: str, terms: Iterable[str]) -> bool:
    """Return whether ``key`` names a sensitive field for the given ``terms``."""
    lowered = key.lower()
    return any(term in lowered for term in terms)


def _normalise_terms(sensitive_keys: Iterable[str]) -> frozenset[str]:
    """Return the sensitive terms lowercased and stripped, blanks dropped."""
    return frozenset(term.strip().lower() for term in sensitive_keys if term.strip())


def redact_metadata(
    metadata: dict[str, MetadataValue],
    sensitive_keys: Iterable[str] = DEFAULT_SENSITIVE_KEYS,
) -> dict[str, MetadataValue]:
    """Return a copy of ``metadata`` with sensitive values masked.

    A key is sensitive when one of ``sensitive_keys`` appears in its lowercased
    name. Its value is replaced by :data:`REDACTION_PLACEHOLDER`, unless it is
    already ``None``: an absent value carries nothing to hide, so it is left as
    ``None``. Every key is kept and its order preserved, so redaction masks
    values without changing the shape of the metadata.
    """
    terms = _normalise_terms(sensitive_keys)
    if not terms:
        return dict(metadata)
    return {
        key: REDACTION_PLACEHOLDER if value is not None and _is_sensitive(key, terms) else value
        for key, value in metadata.items()
    }


def redact_event_input(
    payload: EventInput,
    sensitive_keys: Iterable[str] = DEFAULT_SENSITIVE_KEYS,
) -> EventInput:
    """Return ``payload`` with its metadata redacted, leaving the rest untouched.

    Redaction touches only ``metadata``: the fields the service reasons over,
    such as ``subject`` or ``entity_id``, are the producer's own operational
    description and are left as submitted. The returned model is a copy, so the
    submitted payload is not mutated.
    """
    redacted = redact_metadata(payload.metadata, sensitive_keys)
    if redacted == payload.metadata:
        return payload
    return payload.model_copy(update={"metadata": redacted})


def redact_event(
    event: Event,
    sensitive_keys: Iterable[str] = DEFAULT_SENSITIVE_KEYS,
) -> Event:
    """Return ``event`` with its metadata redacted, leaving the rest untouched.

    The stored-event counterpart of :func:`redact_event_input`, for masking an
    event that already carries its service-assigned identifier.
    """
    redacted = redact_metadata(event.metadata, sensitive_keys)
    if redacted == event.metadata:
        return event
    return event.model_copy(update={"metadata": redacted})
