"""fork_features.streaming – Range-aware file serving helper.

Django's FileResponse does not handle HTTP Range requests, which means the
browser's video seek bar cannot jump to an arbitrary position without
re-downloading the entire file from byte 0.  This helper adds proper
206 Partial Content support so that the native <video> seek bar works.

Usage (in an upstream view):
    from fork_features.streaming import serve_file_with_range
    return serve_file_with_range(request, "/absolute/path/to/file.mp4")
"""

import os
import re

from django.http import FileResponse, HttpResponse


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
        match = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if match:
            first_byte = int(match.group(1))
            last_byte = int(match.group(2)) if match.group(2) else file_size - 1
            last_byte = min(last_byte, file_size - 1)
            length = last_byte - first_byte + 1

            f = open(file_path, "rb")  # noqa: WPS515  – closed by StreamingHttpResponse
            f.seek(first_byte)

            response = FileResponse(f, status=206, content_type=content_type)
            response["Content-Range"] = f"bytes {first_byte}-{last_byte}/{file_size}"
            response["Content-Length"] = length
            response["Accept-Ranges"] = "bytes"
            return response

    # No (or unparseable) Range header – serve the full file.
    response = FileResponse(open(file_path, "rb"), content_type=content_type)
    response["Content-Length"] = file_size
    response["Accept-Ranges"] = "bytes"
    return response
