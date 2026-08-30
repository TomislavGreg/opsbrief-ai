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


def test_demo_data_is_off_by_default() -> None:
    assert Settings().demo_data is False


def test_demo_data_can_be_enabled() -> None:
    assert Settings(demo_data="true").demo_data is True


def test_the_webhook_is_disabled_without_a_secret() -> None:
    settings = Settings(webhook_secret="")

    assert settings.webhook_enabled() is False


def test_a_configured_secret_enables_the_webhook() -> None:
    settings = Settings(webhook_secret="a-long-enough-webhook-secret")

    assert settings.webhook_enabled() is True


def test_a_short_secret_is_refused() -> None:
    with pytest.raises(ValueError, match="at least 16 characters"):
        Settings(webhook_secret="too-short")


def test_the_timestamp_tolerance_defaults_to_five_minutes() -> None:
    assert Settings().webhook_timestamp_tolerance_seconds == 300


def test_a_non_positive_timestamp_tolerance_is_refused() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        Settings(webhook_timestamp_tolerance_seconds=0)
