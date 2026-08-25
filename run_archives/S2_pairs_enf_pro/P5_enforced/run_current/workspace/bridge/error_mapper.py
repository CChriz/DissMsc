"""
Bridge error mapper: converts HTTP status codes to Service B error codes.

FIXED: Both bugs resolved — see inline comments for details.
"""
from typing import Tuple
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
        # Bug 5 FIXED: now correctly maps to NOT_FOUND (5)
        return StatusMessage(code=ErrorCode.NOT_FOUND, message=message or "Resource not found")
    elif status_code == 429:
        # Bug 6 FIXED: now correctly maps to RESOURCE_EXHAUSTED (8)
        return StatusMessage(code=ErrorCode.RESOURCE_EXHAUSTED, message=message or "Too many requests")
    elif 500 <= status_code < 600:
        return StatusMessage(code=ErrorCode.INTERNAL, message=message)
    else:
        return StatusMessage(code=ErrorCode.UNKNOWN, message=message)


def map_error(http_status: int) -> Tuple[int, str]:
    """测试接口：将 HTTP 状态码映射为 (gRPC error code, message)。

    验证 Bug 5 (404→NOT_FOUND) 和 Bug 6 (429→RESOURCE_EXHAUSTED)。
    """
    MESSAGES = {
        0: "Success",
        3: "Invalid argument",
        5: "Resource not found",
        8: "Too many requests",
        13: "Internal server error",
    }
    result = map_http_error(http_status)
    code = int(result.code)
    msg = result.message or MESSAGES.get(code, "Unknown error")
    return code, msg
