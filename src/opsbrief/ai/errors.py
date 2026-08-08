"""Errors raised by AI providers."""


class AIProviderError(RuntimeError):
    """A provider could not produce a completion.

    This covers the ways a real model call fails — a transport error, a timeout,
    a refusal, a response the provider cannot parse — so callers can catch one
    exception type rather than each provider's own. It signals that no usable
    completion came back, never that a completion came back and was unsatisfactory:
    judging the returned text is the caller's job, not the provider's.
    """
