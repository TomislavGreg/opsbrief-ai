"""Tests for the deterministic fake AI provider."""

from opsbrief.ai import AIProvider, CompletionRequest, FakeAIProvider


def test_fake_provider_satisfies_the_protocol() -> None:
    assert isinstance(FakeAIProvider(), AIProvider)


def test_scripted_responses_are_returned_in_order() -> None:
    provider = FakeAIProvider(responses=["first", "second"])

    request = CompletionRequest(instructions="anything")
    assert provider.complete(request).text == "first"
    assert provider.complete(request).text == "second"


def test_scripted_responses_are_returned_verbatim() -> None:
    provider = FakeAIProvider(responses=["  Exactly this, untouched.  "])

    assert (
        provider.complete(CompletionRequest(instructions="x")).text
        == "  Exactly this, untouched.  "
    )


def test_response_reports_the_configured_model() -> None:
    provider = FakeAIProvider(model="fake-briefs")

    response = provider.complete(CompletionRequest(instructions="x"))

    assert response.model == "fake-briefs"


def test_default_model_name() -> None:
    assert FakeAIProvider().complete(CompletionRequest(instructions="x")).model == "fake-1"


def test_echo_falls_back_to_the_input() -> None:
    provider = FakeAIProvider()

    response = provider.complete(
        CompletionRequest(instructions="Summarise.", input="Two integrations failed.")
    )

    assert response.text == "Two integrations failed."


def test_echo_uses_instructions_when_there_is_no_input() -> None:
    provider = FakeAIProvider()

    response = provider.complete(CompletionRequest(instructions="Say hello."))

    assert response.text == "Say hello."


def test_echo_condenses_whitespace_to_one_line() -> None:
    provider = FakeAIProvider()

    response = provider.complete(
        CompletionRequest(instructions="x", input="one\n\n  two   three\tfour")
    )

    assert response.text == "one two three four"


def test_echo_is_bounded_by_max_output_tokens() -> None:
    provider = FakeAIProvider()

    response = provider.complete(
        CompletionRequest(instructions="x", input="y" * 100, max_output_tokens=1)
    )

    # One token maps to roughly four characters.
    assert response.text == "y" * 4


def test_echo_is_deterministic() -> None:
    provider = FakeAIProvider()
    request = CompletionRequest(instructions="Summarise.", input="Same material.")

    first = provider.complete(request)
    second = provider.complete(request)

    assert first.text == second.text


def test_scripted_responses_give_way_to_the_echo_when_exhausted() -> None:
    provider = FakeAIProvider(responses=["scripted"])

    request = CompletionRequest(instructions="x", input="echoed material")
    assert provider.complete(request).text == "scripted"
    assert provider.complete(request).text == "echoed material"


def test_requests_are_recorded_in_order() -> None:
    provider = FakeAIProvider(responses=["a"])
    first = CompletionRequest(instructions="first")
    second = CompletionRequest(instructions="second")

    provider.complete(first)
    provider.complete(second)

    assert provider.requests == [first, second]


def test_scripted_responses_are_copied_from_the_caller() -> None:
    responses = ["first"]
    provider = FakeAIProvider(responses=responses)
    responses.append("sneaked in")

    request = CompletionRequest(instructions="x", input="echoed")
    assert provider.complete(request).text == "first"
    # The later append must not have been picked up.
    assert provider.complete(request).text == "echoed"
