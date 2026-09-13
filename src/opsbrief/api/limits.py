"""Request body size limiting.

Pydantic models and the event contract only constrain a request body after it has
been parsed into Python objects, so on their own they do not bound how many bytes
are read into memory first. A body sent without a ``Content-Length`` header, or one
whose declared length understates the bytes that follow, would otherwise be read in
full before any limit applied.

:class:`MaxBodySizeMiddleware` closes that gap for every route uniformly. It refuses
a body whose declared length already exceeds the bound before reading anything, and
it counts the bytes of a streamed body as they arrive, stopping at the bound plus at
most the one chunk that crossed it rather than reading to the end. Either way an
over-limit request is answered with 413 and the application never sees the body, so
nothing is parsed or stored.

The bound is on the encoded request bytes. It is a separate limit from the
event-count and field-character limits the event contract enforces after parsing: a
batch of at most 500 events, each with its own bounded fields, fits well under the
byte bound, which exists to stop an oversized or endless body rather than to shape a
valid one.
"""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

#: Largest request body accepted, in encoded bytes, before parsing. A full
#: 500-event batch of maximal events fits comfortably under this bound; it exists to
#: refuse an oversized or unbounded body, not to constrain a valid request.
MAX_REQUEST_BODY_BYTES = 8 * 1024 * 1024

_TOO_LARGE_BODY = b'{"detail":"request body exceeds the maximum size"}'


class RequestBodyTooLarge(Exception):
    """Raised while streaming a request body once it exceeds the byte bound."""


def _declared_content_length(scope: Scope) -> int | None:
    """Return the request's declared ``Content-Length``, or ``None`` if unusable.

    A missing or malformed header returns ``None``, so the byte count of the body
    as it streams, not the client's claim about it, decides whether the bound holds.
    """
    for name, value in scope.get("headers", []):
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


async def _send_too_large(send: Send) -> None:
    """Answer the request with a 413 and a short JSON body."""
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(_TOO_LARGE_BODY)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": _TOO_LARGE_BODY})


class MaxBodySizeMiddleware:
    """Bound the bytes read from a request body before the application parses it.

    ``max_bytes`` fixes the bound for this instance; left as ``None`` the middleware
    reads :data:`MAX_REQUEST_BODY_BYTES` afresh on each request, so the module-level
    bound can be adjusted (in tests, for example) without rebuilding the application.
    """

    def __init__(self, app: ASGIApp, max_bytes: int | None = None) -> None:
        self.app = app
        self._max_bytes = max_bytes

    @property
    def max_bytes(self) -> int:
        """The current byte bound, read live from the module default when unset."""
        return self._max_bytes if self._max_bytes is not None else MAX_REQUEST_BODY_BYTES

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = self.max_bytes
        declared = _declared_content_length(scope)
        if declared is not None and declared > limit:
            await _send_too_large(send)
            return

        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise RequestBodyTooLarge
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except RequestBodyTooLarge:
            # The over-limit body was refused before the handler could act on it, so
            # nothing was parsed or stored. If the handler had already begun its
            # response the error is genuine and must propagate.
            if response_started:
                raise
            await _send_too_large(send)
