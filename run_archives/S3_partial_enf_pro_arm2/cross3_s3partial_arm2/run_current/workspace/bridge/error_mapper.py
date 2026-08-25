"""
Bridge error mapper: converts HTTP status codes to Service B error codes.

Fixes applied:
  - Bug 5: 404 → NOT_FOUND (was INVALID_ARGUMENT)
  - Bug 6: 429 → RESOURCE_EXHAUSTED (was INTERNAL)

Mapping reference:
  | HTTP | gRPC Code          | Int | Retryable |
  |------|--------------------|-----|-----------|
  | 200  | OK                 | 0   | N/A       |
  | 400  | INVALID_ARGUMENT   | 3   | No        |
  | 401  | INVALID_ARGUMENT   | 3   | No        |
  | 403  | INVALID_ARGUMENT   | 3   | No        |
  | 404  | NOT_FOUND          | 5   | No        |
  | 429  | RESOURCE_EXHAUSTED | 8   | Yes       |
  | 5xx  | INTERNAL           | 13  | Yes       |
"""
from service_b.schema import ErrorCode, StatusMessage


# HTTP status → ErrorCode exact-match table
# 404 and 429 are explicitly mapped here — they take priority over fallback rules.
HTTP_TO_GRPC_MAP = {
    200: ErrorCode.OK,
    400: ErrorCode.INVALID_ARGUMENT,
    401: ErrorCode.INVALID_ARGUMENT,
    403: ErrorCode.INVALID_ARGUMENT,
    404: ErrorCode.NOT_FOUND,          # Bug 5 fixed: was INVALID_ARGUMENT
    429: ErrorCode.RESOURCE_EXHAUSTED, # Bug 6 fixed: was INTERNAL
}


def map_http_error(status_code: int, message: str = "") -> StatusMessage:
    """Map HTTP status code from Service A to a Service B error code.

    Uses exact-match mapping table first, then falls back to range-based
    rules for unmatched codes. This ensures 404 and 429 are correctly
    matched before any catch-all 4xx/5xx logic.
    """
    # Step 1: exact match (including 404→NOT_FOUND, 429→RESOURCE_EXHAUSTED)
    if status_code in HTTP_TO_GRPC_MAP:
        return StatusMessage(code=HTTP_TO_GRPC_MAP[status_code], message=message)

    # Step 2: fallback rules for unmatched codes
    if 400 <= status_code < 500:
        return StatusMessage(code=ErrorCode.INVALID_ARGUMENT, message=message)
    if 500 <= status_code < 600:
        return StatusMessage(code=ErrorCode.INTERNAL, message=message)

    # Step 3: ultimate fallback
    return StatusMessage(code=ErrorCode.UNKNOWN, message=message)
