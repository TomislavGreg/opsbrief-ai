"""A deterministic fake AI provider for tests and demos.

Tests must never call a real language model: real calls are slow, non-free and,
worse, non-deterministic, so a test that asserted on their output would be
flaky. :class:`FakeAIProvider` stands in for a real provider with behaviour that
is fully determined by the request, so the same request always yields the same
completion.

It works two ways. Given a list of ``responses`` it returns them in order, which
lets a test pin exactly what the "model" says — useful for exercising how the
service parses and validates generated text. Once those run out (or when none
were given) it falls back to a deterministic echo of the request, bounded by the
request's ``max_output_tokens``, so a caller that just needs *some* stable output
gets one. Every request it receives is recorded on :attr:`requests`, so a test
can assert what the service actually asked for.
"""

from collections.abc import Sequence

from opsbrief.ai.schema import CompletionRequest, CompletionResponse

#: Rough characters-per-token ratio used to turn a token budget into a length.
_CHARS_PER_TOKEN = 4


class FakeAIProvider:
    """A provider whose output is a pure function of its input.

    Pass ``responses`` to script the completions returned, in order; each is
    returned verbatim, because a test that scripts output has chosen it
    deliberately. When the script is exhausted the provider echoes the request's
    material — its ``input``, or its ``instructions`` when there is no input —
    condensed to a single line and truncated to the request's ``max_output_tokens``,
    so the fallback still honours the same output bound a real provider would.
    """

    name = "fake"

    def __init__(
        self,
        *,
        model: str = "fake-1",
        responses: Sequence[str] | None = None,
    ) -> None:
        """Build the provider, optionally scripting the completions it returns.

        ``model`` is reported on every response so generated text stays traceable
        to a model name. ``responses`` are handed back in order before the echo
        fallback takes over; the list is copied so a later mutation cannot change
        what the provider will return.
        """
        self.model = model
        self._scripted: list[str] = list(responses or [])
        self.requests: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Return the next scripted completion, or a deterministic echo.

        The request is recorded on :attr:`requests` before anything else, so it
        is captured even for a scripted reply. Scripted responses are returned
        untouched; the echo fallback is derived only from the request, so it is
        stable across runs.
        """
        self.requests.append(request)
        text = self._scripted.pop(0) if self._scripted else self._echo(request)
        return CompletionResponse(text=text, model=self.model)

    @staticmethod
    def _echo(request: CompletionRequest) -> str:
        """Condense the request's material to one bounded, deterministic line."""
        material = request.input.strip() or request.instructions.strip()
        condensed = " ".join(material.split())
        budget = request.max_output_tokens * _CHARS_PER_TOKEN
        return condensed[:budget]
