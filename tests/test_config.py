"""Tests for application settings."""

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
