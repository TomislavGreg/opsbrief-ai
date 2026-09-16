"""Read-only mode enforcement.

A public demo, or any deployment that should serve reads without taking writes,
needs the whole write surface closed at once rather than route by route. The event,
batch, incident and webhook write paths are all reached with an unsafe HTTP method
(``POST``, ``PUT``, ``PATCH`` or ``DELETE``), and every read is a ``GET`` (with
``HEAD`` and ``OPTIONS`` alongside it), so a single method check refuses every
mutation uniformly while leaving the read endpoints untouched.

:class:`ReadOnlyMiddleware` does exactly that. When read-only mode is on it answers
an unsafe-method request with 403 before the router runs, so nothing is parsed or
stored, and passes every safe-method request through unchanged. When it is off the
middleware is transparent, so an ordinary deployment behaves exactly as before.

This is an application-level switch for closing writes, not a substitute for the
webhook signature or for restricting reads: it is all-or-nothing over writes. A
deployment that needs to expose the signed webhook while hiding the internal write
routes does that at the proxy or ingress (see ``docs/deployment.md``).
"""

from starlette.types import ASGIApp, Receive, Scope, Send

#: HTTP methods that never mutate state and are always allowed.
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

_READ_ONLY_BODY = (
    b'{"detail":"the service is running in read-only mode; write routes are disabled"}'
)


async def _send_read_only(send: Send) -> None:
    """Answer the request with a 403 and a short JSON body."""
    await send(
        {
            "type": "http.response.start",
            "status": 403,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(_READ_ONLY_BODY)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": _READ_ONLY_BODY})


class ReadOnlyMiddleware:
    """Refuse every write request when the application is in read-only mode.

    ``read_only`` fixes the mode for this instance at build time. When it is false
    the middleware forwards every request unchanged; when it is true it answers an
    unsafe-method HTTP request with 403 before the application sees it.
    """

    def __init__(self, app: ASGIApp, read_only: bool = False) -> None:
        self.app = app
        self.read_only = read_only

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self.read_only and scope["type"] == "http" and scope["method"] not in _SAFE_METHODS:
            await _send_read_only(send)
            return
        await self.app(scope, receive, send)
