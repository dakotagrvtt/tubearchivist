"""fork_features.streaming – Range-aware file serving helper.

Django's FileResponse does not handle HTTP Range requests, which means the
browser's video seek bar cannot jump to an arbitrary position without
re-downloading the entire file from byte 0.  This helper adds proper
206 Partial Content support so that the native <video> seek bar works.

Usage (in an upstream view):
    from fork_features.streaming import serve_file_with_range
    return serve_file_with_range(request, "/absolute/path/to/file.mp4")
"""

import asyncio
import os
import re

from django.http import HttpResponse, StreamingHttpResponse

_CHUNK_SIZE = 64 * 1024


def serve_file_with_range(request, file_path: str, content_type: str = "video/mp4"):
    """Return an HTTP response for *file_path* that honours the Range header.

    When the client sends ``Range: bytes=start-end`` (as all modern browsers
    do when seeking in a ``<video>`` element) this function returns a
    ``206 Partial Content`` response containing only the requested slice.
    When no Range header is present the full file is returned as ``200 OK``.
    The ``Accept-Ranges: bytes`` header is always included so the browser
    knows that byte-range requests are supported.
    """
    file_size = os.path.getsize(file_path)
    range_header = request.META.get("HTTP_RANGE", "").strip()

    if range_header:
        # Only single byte ranges are supported (RFC 7233). Reject malformed
        # or unsupported values with 416 so clients can retry correctly.
        if "," in range_header:
            return _range_not_satisfiable(file_size)

        match = re.match(r"^bytes=(\d*)-(\d*)$", range_header)
        if not match:
            return _range_not_satisfiable(file_size)

        start_str, end_str = match.groups()
        if not start_str and not end_str:
            return _range_not_satisfiable(file_size)

        if start_str:
            first_byte = int(start_str)
            if first_byte >= file_size:
                return _range_not_satisfiable(file_size)
            last_byte = int(end_str) if end_str else file_size - 1
        else:
            suffix_len = int(end_str)
            if suffix_len <= 0:
                return _range_not_satisfiable(file_size)
            first_byte = max(file_size - suffix_len, 0)
            last_byte = file_size - 1

        last_byte = min(last_byte, file_size - 1)
        if first_byte > last_byte:
            return _range_not_satisfiable(file_size)

        length = last_byte - first_byte + 1
        response = StreamingHttpResponse(
            _iter_file_range(file_path, first_byte, length),
            status=206,
            content_type=content_type,
        )
        response["Content-Range"] = f"bytes {first_byte}-{last_byte}/{file_size}"
        response["Content-Length"] = length
        response["Accept-Ranges"] = "bytes"
        return response

    # No (or unparseable) Range header – serve the full file.
    response = StreamingHttpResponse(
        _iter_file_range(file_path, 0, file_size),
        content_type=content_type,
    )
    response["Content-Length"] = file_size
    response["Accept-Ranges"] = "bytes"
    return response


async def _iter_file_range(file_path: str, start: int, length: int):
    """Yield a file byte range without blocking the ASGI event loop."""
    with open(file_path, "rb") as handle:
        await asyncio.to_thread(handle.seek, start)
        remaining = length
        while remaining > 0:
            chunk_size = min(_CHUNK_SIZE, remaining)
            chunk = await asyncio.to_thread(handle.read, chunk_size)
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def _range_not_satisfiable(file_size: int) -> HttpResponse:
    """Return 416 response for malformed or unsupported range requests."""
    response = HttpResponse(status=416)
    response["Content-Range"] = f"bytes */{file_size}"
    response["Accept-Ranges"] = "bytes"
    return response
