"""Tests for the AI completion contract."""

import pytest
from pydantic import ValidationError

from opsbrief.ai import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    MAX_OUTPUT_TOKENS_LIMIT,
    MAX_PROMPT_LENGTH,
    CompletionRequest,
    CompletionResponse,
)


def test_minimal_request_applies_defaults() -> None:
    request = CompletionRequest(instructions="Summarise the operational picture.")

    assert request.instructions == "Summarise the operational picture."
    assert request.input == ""
    assert request.max_output_tokens == DEFAULT_MAX_OUTPUT_TOKENS
    assert request.temperature == 0.0


def test_request_carries_instructions_and_input_apart() -> None:
    request = CompletionRequest(
        instructions="Write a one-line brief.",
        input="Two integrations failed.",
        max_output_tokens=128,
        temperature=0.2,
    )

    assert request.instructions == "Write a one-line brief."
    assert request.input == "Two integrations failed."
    assert request.max_output_tokens == 128
    assert request.temperature == 0.2


def test_instructions_are_required() -> None:
    with pytest.raises(ValidationError):
        CompletionRequest(instructions="")


def test_instructions_are_length_bounded() -> None:
    with pytest.raises(ValidationError):
        CompletionRequest(instructions="x" * (MAX_PROMPT_LENGTH + 1))


def test_input_is_length_bounded() -> None:
    with pytest.raises(ValidationError):
        CompletionRequest(instructions="ok", input="x" * (MAX_PROMPT_LENGTH + 1))


def test_max_output_tokens_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        CompletionRequest(instructions="ok", max_output_tokens=0)


def test_max_output_tokens_is_capped() -> None:
    with pytest.raises(ValidationError):
        CompletionRequest(instructions="ok", max_output_tokens=MAX_OUTPUT_TOKENS_LIMIT + 1)


def test_temperature_is_bounded() -> None:
    with pytest.raises(ValidationError):
        CompletionRequest(instructions="ok", temperature=2.5)
    with pytest.raises(ValidationError):
        CompletionRequest(instructions="ok", temperature=-0.1)


def test_request_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        CompletionRequest(instructions="ok", extra="nope")


def test_response_requires_a_model() -> None:
    with pytest.raises(ValidationError):
        CompletionResponse(text="anything", model="")


def test_response_text_may_be_empty() -> None:
    response = CompletionResponse(text="", model="fake")

    assert response.text == ""
    assert response.model == "fake"


def test_response_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        CompletionResponse(text="hi", model="fake", extra="nope")


def test_response_is_serialisable() -> None:
    response = CompletionResponse(text="Two integrations failed today.", model="fake")

    dumped = response.model_dump()

    assert dumped == {"text": "Two integrations failed today.", "model": "fake"}
