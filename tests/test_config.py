"""Tests for application settings."""

import pytest

from opsbrief.config import Settings
from opsbrief.redaction import DEFAULT_SENSITIVE_KEYS


def test_sensitive_keys_default_to_the_built_in_set() -> None:
    settings = Settings(redact_metadata_keys="")

    assert settings.sensitive_metadata_keys() == DEFAULT_SENSITIVE_KEYS


def test_configured_terms_extend_the_defaults() -> None:
    settings = Settings(redact_metadata_keys="seat, badge")

    keys = settings.sensitive_metadata_keys()
    assert keys >= DEFAULT_SENSITIVE_KEYS
    assert keys >= {"seat", "badge"}


def test_blank_configured_terms_are_dropped() -> None:
    settings = Settings(redact_metadata_keys=" , ,")

    assert settings.sensitive_metadata_keys() == DEFAULT_SENSITIVE_KEYS


def test_excluded_ai_context_fields_default_to_nothing() -> None:
    settings = Settings(ai_context_excluded_fields="")

    assert settings.excluded_ai_context_fields() == frozenset()


def test_configured_excluded_fields_are_parsed() -> None:
    settings = Settings(ai_context_excluded_fields="subject, source")

    assert settings.excluded_ai_context_fields() == {"subject", "source"}


def test_an_unknown_excluded_field_is_refused() -> None:
    settings = Settings(ai_context_excluded_fields="subject, nope")

    with pytest.raises(ValueError, match="unknown AI context field 'nope'"):
        settings.excluded_ai_context_fields()
