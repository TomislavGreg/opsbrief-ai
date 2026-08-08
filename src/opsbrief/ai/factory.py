"""Selecting an AI provider from configuration.

The provider the service uses is chosen by the ``OPSBRIEF_AI_PROVIDER`` setting,
so nothing downstream has to know which one is active — it asks
:func:`create_provider` and gets whatever the configuration names. Only the
deterministic fake is implemented so far; an unknown name is refused rather than
silently ignored, so a misconfiguration fails loudly at wiring time instead of
producing empty briefs later.
"""

from opsbrief.ai.fake import FakeAIProvider
from opsbrief.ai.provider import AIProvider
from opsbrief.config import Settings, get_settings

#: Provider names this build knows how to build.
_PROVIDERS = {"fake": FakeAIProvider}


def create_provider(settings: Settings | None = None) -> AIProvider:
    """Return the AI provider named by ``settings.ai_provider``.

    Falls back to the cached application settings when none are given. Raises
    :class:`ValueError` when the configured name is not one this build knows, so
    the caller learns about a bad configuration immediately rather than at the
    first generation attempt.
    """
    settings = settings or get_settings()
    name = settings.ai_provider
    try:
        provider_type = _PROVIDERS[name]
    except KeyError:
        known = ", ".join(sorted(_PROVIDERS))
        raise ValueError(f"unknown AI provider {name!r}; known providers are: {known}") from None
    return provider_type()
