"""Tests for the AI provider interface."""

from opsbrief.ai import (
    AIProvider,
    AIProviderError,
    CompletionRequest,
    CompletionResponse,
)


class StubProvider:
    """A minimal provider that echoes its instructions, for interface tests."""

    name = "stub"

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        return CompletionResponse(text=request.instructions, model="stub-1")


def test_a_conforming_class_satisfies_the_protocol() -> None:
    provider = StubProvider()

    assert isinstance(provider, AIProvider)


def test_a_class_missing_complete_does_not_satisfy_the_protocol() -> None:
    class NoComplete:
        name = "broken"

    assert not isinstance(NoComplete(), AIProvider)


def test_a_class_missing_name_does_not_satisfy_the_protocol() -> None:
    class NoName:
        def complete(self, request: CompletionRequest) -> CompletionResponse:
            return CompletionResponse(text="", model="x")

    assert not isinstance(NoName(), AIProvider)


def test_complete_returns_a_response_for_a_request() -> None:
    provider = StubProvider()

    response = provider.complete(CompletionRequest(instructions="Say hello."))

    assert response.text == "Say hello."
    assert response.model == "stub-1"


def test_provider_error_is_an_exception() -> None:
    assert issubclass(AIProviderError, Exception)

    try:
        raise AIProviderError("boom")
    except AIProviderError as error:
        assert str(error) == "boom"
