"""The AI provider interface.

A provider is the seam between the service and a language model. The service
hands it a :class:`~opsbrief.ai.schema.CompletionRequest` and gets back a
:class:`~opsbrief.ai.schema.CompletionResponse`; everything about a particular
model — its SDK, its authentication, its wire format — lives behind the seam.
Keeping the interface this small means the rest of the codebase depends on the
contract, not on any one model, and a deterministic fake can stand in for a real
provider in tests.

This module defines the contract, not a provider. Concrete providers — a
deterministic fake for tests, and real model-backed ones later — implement
:class:`AIProvider` in their own modules.
"""

from typing import Protocol, runtime_checkable

from opsbrief.ai.schema import CompletionRequest, CompletionResponse


@runtime_checkable
class AIProvider(Protocol):
    """A language model the service can ask to turn material into prose.

    A provider carries a stable :attr:`name`, so a generated statement can record
    which provider produced it, and a single :meth:`complete` method. It is used
    only for phrasing: it never decides what counts as a risk or how urgent
    something is. A provider treats the request as given and returns what the
    model produced; it does not judge the result, because the caller treats that
    result as untrusted and validates it.
    """

    #: Stable identifier for the provider, for example 'fake' or 'anthropic'.
    name: str

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Turn ``request`` into a completion.

        Return a :class:`CompletionResponse` carrying the produced text and the
        model that produced it. Raise :class:`~opsbrief.ai.errors.AIProviderError`
        when no usable completion can be produced — a transport failure, a
        timeout, an unparseable reply — rather than returning an empty or
        made-up one.
        """
        ...
