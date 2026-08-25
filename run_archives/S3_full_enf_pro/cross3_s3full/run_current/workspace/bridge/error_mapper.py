"""
Bridge error mapper: converts HTTP status codes to Service B error codes.

Contains 2 bugs — see spec.md for details.
"""
from service_b.schema import ErrorCode, StatusMessage


def map_http_error(status_code: int, message: str = "") -> StatusMessage:
    """Map HTTP status code from Service A to a Service B error code."""
    if status_code == 200:
        return StatusMessage(code=ErrorCode.OK)
    elif status_code == 400:
        return StatusMessage(code=ErrorCode.INVALID_ARGUMENT, message=message)
    elif status_code in (401, 403):
        return StatusMessage(code=ErrorCode.INVALID_ARGUMENT, message=message)
    elif status_code == 404:
        # Bug 5 fix: 404 → NOT_FOUND (5)
        return StatusMessage(code=ErrorCode.NOT_FOUND, message=message)
    elif status_code == 429:
        # Bug 6 fix: 429 → RESOURCE_EXHAUSTED (8)
        return StatusMessage(code=ErrorCode.RESOURCE_EXHAUSTED, message=message)
    elif 500 <= status_code < 600:
        return StatusMessage(code=ErrorCode.INTERNAL, message=message)
    else:
        return StatusMessage(code=ErrorCode.UNKNOWN, message=message)
