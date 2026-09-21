"""Tests for startup configuration validation and logging setup."""

import logging

import pytest

from opsbrief.config import Settings
from opsbrief.startup import ConfigurationError, configure_logging, validate_settings


def test_default_settings_validate() -> None:
    # A fresh, offline configuration starts without complaint.
    validate_settings(Settings())


def test_an_unknown_provider_fails_validation() -> None:
    with pytest.raises(ConfigurationError) as error:
        validate_settings(Settings(ai_provider="mystery"))

    message = str(error.value)
    assert "mystery" in message
    assert "deterministic" in message
    assert "fake" in message


def test_an_unknown_excluded_field_fails_validation() -> None:
    with pytest.raises(ConfigurationError, match="nope"):
        validate_settings(Settings(ai_context_excluded_fields="subject, nope"))


def test_an_unsupported_database_url_fails_validation() -> None:
    with pytest.raises(ConfigurationError):
        validate_settings(Settings(database_url="postgresql://localhost/opsbrief"))


def test_an_unknown_log_level_fails_validation() -> None:
    with pytest.raises(ConfigurationError, match="verbose"):
        validate_settings(Settings(log_level="verbose"))


def test_a_known_log_level_validates_case_insensitively() -> None:
    validate_settings(Settings(log_level="DEBUG"))
    validate_settings(Settings(log_level="warning"))


def test_valid_settings_make_no_database_or_network_call() -> None:
    # Validation only inspects the URL string; it never opens the database, so a
    # path that does not exist still validates.
    validate_settings(Settings(database_url="sqlite:///./does-not-exist/opsbrief.db"))


def test_configure_logging_applies_the_documented_level() -> None:
    original = logging.getLogger().level
    try:
        configure_logging(Settings(log_level="debug"))
        assert logging.getLogger().level == logging.DEBUG

        configure_logging(Settings(log_level="warning"))
        assert logging.getLogger().level == logging.WARNING
    finally:
        logging.getLogger().setLevel(original)
