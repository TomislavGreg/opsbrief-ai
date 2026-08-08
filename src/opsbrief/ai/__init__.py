"""AI providers: the seam between the service and a language model.

Language models are used only to turn material the service has already assembled
into prose. They never decide what counts as a risk or how urgent it is — that
stays with the deterministic rules — and their output is treated as untrusted
data, validated before use.
"""

from opsbrief.ai.errors import AIProviderError
from opsbrief.ai.factory import create_provider
from opsbrief.ai.fake import FakeAIProvider
from opsbrief.ai.provider import AIProvider
from opsbrief.ai.schema import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    MAX_OUTPUT_TOKENS_LIMIT,
    MAX_PROMPT_LENGTH,
    CompletionRequest,
    CompletionResponse,
)

__all__ = [
    "DEFAULT_MAX_OUTPUT_TOKENS",
    "MAX_OUTPUT_TOKENS_LIMIT",
    "MAX_PROMPT_LENGTH",
    "AIProvider",
    "AIProviderError",
    "CompletionRequest",
    "CompletionResponse",
    "FakeAIProvider",
    "create_provider",
]
