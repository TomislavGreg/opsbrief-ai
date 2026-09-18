"""Tests for selecting an AI provider from configuration."""

import pytest

from opsbrief.ai import (
    AIProvider,
    DeterministicNarrativeProvider,
    FakeAIProvider,
    create_provider,
)
from opsbrief.config import Settings


def test_fake_provider_is_selected_by_configuration() -> None:
    provider = create_provider(Settings(ai_provider="fake"))

    assert isinstance(provider, FakeAIProvider)
    assert isinstance(provider, AIProvider)


def test_deterministic_provider_is_selected_by_configuration() -> None:
    provider = create_provider(Settings(ai_provider="deterministic"))

    assert isinstance(provider, DeterministicNarrativeProvider)
    assert isinstance(provider, AIProvider)


def test_unknown_provider_is_refused() -> None:
    with pytest.raises(ValueError) as error:
        create_provider(Settings(ai_provider="mystery"))

    message = str(error.value)
    assert "mystery" in message
    assert "fake" in message
    assert "deterministic" in message


def test_default_settings_select_the_deterministic_provider() -> None:
    # The shipped default runs offline and composes summaries from the structured
    # picture, so a fresh build resolves the deterministic narrative provider.
    provider = create_provider(Settings())

    assert isinstance(provider, DeterministicNarrativeProvider)
