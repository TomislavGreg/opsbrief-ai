"""Validate configuration and wire logging once, before the service serves.

Several settings are only meaningful if they name something the build knows:
an unknown AI provider, an unknown excluded context field, an unsupported
database URL or an unknown logging level are all misconfigurations that should
fail loudly at startup with an actionable message, rather than surfacing later
as a 500 on the first ``/brief`` or being silently ignored. This module gathers
those checks into :func:`validate_settings`, which touches no network and opens
no database, so a valid offline configuration still starts. :func:`configure_logging`
applies the documented logging level once, so ``OPSBRIEF_LOG_LEVEL`` actually
affects logs.
"""

import logging

from opsbrief.ai import known_provider_names
from opsbrief.config import Settings
from opsbrief.storage import database_path


class ConfigurationError(Exception):
    """Raised when a setting names something this build cannot honour.

    The message is a concise, actionable statement of what is wrong, suitable
    for printing to an operator, and never carries a traceback or a secret.
    """


def _check_provider(settings: Settings) -> None:
    """Refuse a provider name this build cannot construct."""
    known = known_provider_names()
    if settings.ai_provider not in known:
        names = ", ".join(sorted(known))
        raise ConfigurationError(
            f"unknown AI provider {settings.ai_provider!r}; known providers are: {names}"
        )


def _check_excluded_fields(settings: Settings) -> None:
    """Force the excluded-context-field parse so an unknown name fails now."""
    try:
        settings.excluded_ai_context_fields()
    except ValueError as error:
        raise ConfigurationError(str(error)) from error


def _check_database_url(settings: Settings) -> None:
    """Refuse a database URL the storage layer cannot open, without opening it."""
    try:
        database_path(settings.database_url)
    except ValueError as error:
        raise ConfigurationError(str(error)) from error


def _check_log_level(settings: Settings) -> None:
    """Refuse a logging level name the standard library does not know."""
    if settings.log_level.upper() not in logging.getLevelNamesMapping():
        names = ", ".join(name.lower() for name in _log_level_names())
        raise ConfigurationError(
            f"unknown log level {settings.log_level!r}; known levels are: {names}"
        )


def _log_level_names() -> list[str]:
    """Return the named logging levels, most severe first, without the aliases."""
    mapping = logging.getLevelNamesMapping()
    named = {value: name for name, value in mapping.items() if name != "WARN"}
    return [named[value] for value in sorted(named, reverse=True)]


def validate_settings(settings: Settings) -> None:
    """Check every setting this build must be able to honour, or raise.

    Validates the AI provider name, the excluded AI context fields, the database
    URL and the logging level. No network call is made and no database is opened,
    so a valid offline configuration passes; an invalid one raises
    :class:`ConfigurationError` with an actionable message naming the setting at
    fault. The webhook secret and timestamp tolerance are already validated when
    the settings are constructed, so they are not repeated here.
    """
    _check_provider(settings)
    _check_excluded_fields(settings)
    _check_database_url(settings)
    _check_log_level(settings)


def configure_logging(settings: Settings) -> None:
    """Apply the documented logging level, so ``OPSBRIEF_LOG_LEVEL`` takes effect.

    The level name is assumed valid; :func:`validate_settings` checks it. The root
    logger's level is set explicitly so the setting takes effect even when logging
    was already configured elsewhere in the process.
    """
    level = logging.getLevelNamesMapping()[settings.log_level.upper()]
    logging.basicConfig(level=level)
    logging.getLogger().setLevel(level)
