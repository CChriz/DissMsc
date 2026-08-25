"""
Bridge error mapper: converts HTTP status codes to Service B error codes.

Fixes applied (per plan_errors):
  - Bug 5: HTTP 404 → NOT_FOUND (5), was INVALID_ARGUMENT (3)
  - Bug 6: HTTP 429 → RESOURCE_EXHAUSTED (8), was INTERNAL (13)
  - Enhancement: Propagate Retry-After header for HTTP 429 responses
"""
from __future__ import annotations
from service_b.schema import ErrorCode, StatusMessage
from typing import Optional


def map_http_error(status_code: int, message: str = "") -> StatusMessage:
    """Map HTTP status code from Service A to a Service B error code."""
    if status_code == 200:
        return StatusMessage(code=ErrorCode.OK)
    elif status_code == 400:
        return StatusMessage(code=ErrorCode.INVALID_ARGUMENT, message=message)
    elif status_code in (401, 403):
        return StatusMessage(code=ErrorCode.INVALID_ARGUMENT, message=message)
    elif status_code == 404:
        # Bug 5 fixed: NOT_FOUND (5) — "resource does not exist" semantics,
        # not "invalid argument" semantics. NOT_FOUND is idempotent/retryable.
        return StatusMessage(code=ErrorCode.NOT_FOUND, message=message)
    elif status_code == 429:
        # Bug 6 fixed: RESOURCE_EXHAUSTED (8) — "back off and retry" semantics,
        # not "internal server error" semantics which would trigger blind retries.
        return StatusMessage(code=ErrorCode.RESOURCE_EXHAUSTED, message=message)
    elif 500 <= status_code < 600:
        return StatusMessage(code=ErrorCode.INTERNAL, message=message)
    else:
        return StatusMessage(code=ErrorCode.UNKNOWN, message=message)


def map_http_error_with_headers(
    status_code: int,
    headers: Optional[dict] = None,
    message: str = "",
) -> StatusMessage:
    """
    Map HTTP status code with headers for enhanced error propagation.

    Extends map_http_error with Retry-After extraction for HTTP 429 responses.
    This enables Service B consumers to implement intelligent backoff.

    Args:
        status_code: HTTP response status code from Service A
        headers: Optional HTTP response headers dict. Used to extract
                 Retry-After for HTTP 429 responses.
        message: Human-readable error detail

    Returns:
        StatusMessage with retry_delay_seconds set when available
    """
    status_msg = map_http_error(status_code, message)

    # Propagate Retry-After for HTTP 429 (RESOURCE_EXHAUSTED)
    if status_code == 429 and headers:
        retry_after = headers.get("Retry-After") or headers.get("retry-after")
        if retry_after is not None:
            try:
                status_msg.retry_delay_seconds = int(retry_after)
            except (ValueError, TypeError):
                # Non-integer format (e.g. HTTP-date) — skip gracefully
                pass

    return status_msg
