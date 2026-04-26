"""quiet_asyncio - suppress benign asyncio transport-disconnect noise.

uvicorn on vanilla asyncio logs ``socket.send() raised exception.`` (and a
couple of related transport errors) at ERROR whenever a client disconnects
mid-response. These are harmless. This module installs a custom exception
handler on the running event loop that downgrades those specific errors to
DEBUG and delegates everything else to the default handler.
"""

from __future__ import annotations

import asyncio
import logging
from functools import wraps

log = logging.getLogger(__name__)
_PATCHED_ATTR = "_ta_quiet_asyncio_patched"

_BENIGN_EXC_TYPES = (
    BrokenPipeError,
    ConnectionResetError,
    ConnectionAbortedError,
)

_BENIGN_MESSAGES = frozenset(
    {
        "socket.send() raised exception.",
        "Fatal write error on socket transport",
        "Fatal error on SSL transport",
    }
)


def _is_benign_disconnect(context: dict) -> bool:
    exc = context.get("exception")
    msg = context.get("message", "")
    return isinstance(exc, _BENIGN_EXC_TYPES) or msg in _BENIGN_MESSAGES


def _log_suppressed(context: dict) -> None:
    exc = context.get("exception")
    msg = context.get("message", "")
    log.debug("suppressed asyncio transport error: %s (%r)", msg, exc)


def _handler(loop: asyncio.AbstractEventLoop, context: dict) -> None:
    if _is_benign_disconnect(context):
        _log_suppressed(context)
        return
    _ORIGINAL_DEFAULT_HANDLER(loop, context)


_ORIGINAL_DEFAULT_HANDLER = asyncio.BaseEventLoop.default_exception_handler


def _patch_default_handler() -> None:
    current_handler = asyncio.BaseEventLoop.default_exception_handler
    if getattr(current_handler, _PATCHED_ATTR, False):
        return

    @wraps(current_handler)
    def quiet_default_handler(
        self: asyncio.AbstractEventLoop, context: dict
    ) -> None:
        if _is_benign_disconnect(context):
            _log_suppressed(context)
            return
        current_handler(self, context)

    setattr(quiet_default_handler, _PATCHED_ATTR, True)
    asyncio.BaseEventLoop.default_exception_handler = quiet_default_handler


def install() -> None:
    """Attach the quiet handler to the current and future event loops."""
    _patch_default_handler()

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.set_exception_handler(_handler)
