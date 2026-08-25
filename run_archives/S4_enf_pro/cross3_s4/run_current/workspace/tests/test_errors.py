"""
Tests for bridge/error_mapper.py — tests the 2 HTTP→error code mapping bugs.
"""
import pytest
from bridge.error_mapper import map_http_error
from service_b.schema import ErrorCode


def test_200_maps_to_ok():
    """200 OK must map to ErrorCode.OK (0)."""
    result = map_http_error(200)
    assert result.code == ErrorCode.OK, f"200 -> expected OK(0), got {result.code}"


def test_400_maps_to_invalid_argument():
    """400 must map to INVALID_ARGUMENT (3)."""
    result = map_http_error(400, "bad request")
    assert result.code == ErrorCode.INVALID_ARGUMENT, (
        f"400 -> expected INVALID_ARGUMENT(3), got {result.code}"
    )


def test_404_maps_to_not_found():
    """Bug 5: HTTP 404 must map to NOT_FOUND (5), not INVALID_ARGUMENT (3)."""
    result = map_http_error(404, "resource not found")
    assert result.code == ErrorCode.NOT_FOUND, (
        f"404 must map to NOT_FOUND (5), got {result.code} ({int(result.code)}). "
        "Change ErrorCode.INVALID_ARGUMENT to ErrorCode.NOT_FOUND in error_mapper.py."
    )


def test_429_maps_to_resource_exhausted():
    """Bug 6: HTTP 429 must map to RESOURCE_EXHAUSTED (8), not INTERNAL (13)."""
    result = map_http_error(429, "too many requests")
    assert result.code == ErrorCode.RESOURCE_EXHAUSTED, (
        f"429 must map to RESOURCE_EXHAUSTED (8), got {result.code} ({int(result.code)}). "
        "Change ErrorCode.INTERNAL to ErrorCode.RESOURCE_EXHAUSTED in error_mapper.py."
    )


def test_500_maps_to_internal():
    """500 must map to INTERNAL (13)."""
    result = map_http_error(500, "server error")
    assert result.code == ErrorCode.INTERNAL, (
        f"500 -> expected INTERNAL(13), got {result.code}"
    )
