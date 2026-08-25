"""
Event Queue Consumer — Proto3-style message schema.

This module defines the structured messages that Service B consumes.
Field semantics follow proto3 rules:
  - int64 fields hold arbitrary-precision Python ints
  - bytes fields hold raw bytes (NOT base64 strings)
  - oneof fields allow exactly one variant to be set
  - enum fields use integer codes, not string names
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional


class EventStatus(IntEnum):
    """Proto3 enum — integer codes only."""
    STATUS_UNKNOWN = 0
    STATUS_ACTIVE = 1
    STATUS_INACTIVE = 2
    STATUS_PENDING = 3


class ErrorCode(IntEnum):
    """gRPC-style error codes."""
    OK = 0
    CANCELLED = 1
    UNKNOWN = 2
    INVALID_ARGUMENT = 3
    NOT_FOUND = 5
    ALREADY_EXISTS = 6
    RESOURCE_EXHAUSTED = 8
    INTERNAL = 13


@dataclass
class EventMessage:
    """Proto3-style message for Event Queue Consumer."""
    event_id: int = 0          # int64: must hold values > 2^32
    event_type: str = ""
    payload: bytes = b""        # bytes: base64-decoded from JSON
    status: int = 0             # EventStatus integer code (not string)
    occurred_at: int = 0          # int64 unix timestamp

    # oneof content { text_content, binary_content }
    text_content: str = ""        # set this OR content_binary, not both
    binary_content: bytes = b""   # set this OR content_text, not both

    def validate_oneof(self) -> bool:
        """Exactly one of text_content or binary_content must be set."""
        set_fields = []
        if self.text_content:
            set_fields.append("text_content")
        if self.binary_content:
            set_fields.append("binary_content")
        if len(set_fields) > 1:
            raise ValueError(
                f"oneof violation: multiple variants set: {set_fields}"
            )
        return True


@dataclass
class StatusMessage:
    """Error/status response for Service B."""
    code: int = 0
    message: str = ""
