"""
Event Streaming API — JSON data models.

These models define the JSON structure that Service A returns.
Note: binary data is base64-encoded as strings; large IDs are plain numbers.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import base64


class EventRecord:
    """JSON response model from Event Streaming API."""

    VALID_STATUSES = ["STATUS_UNKNOWN", "STATUS_ACTIVE", "STATUS_INACTIVE", "STATUS_PENDING"]

    def __init__(
        self,
        event_id: int,
        event_type: str,
        payload: str,          # base64-encoded binary
        status: str,           # string enum name
        occurred_at: int,        # unix timestamp (int64)
        text_content: str = "",  # optional text content (oneof)
        binary_content: str = "",# optional binary content as base64 (oneof)
    ):
        self.event_id = event_id
        self.event_type = event_type
        self.payload = payload
        self.status = status
        self.occurred_at = occurred_at
        self.text_content = text_content
        self.binary_content = binary_content

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "payload": self.payload,
            "status": self.status,
            "occurred_at": self.occurred_at,
            "text_content": self.text_content,
            "binary_content": self.binary_content,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EventRecord":
        return cls(
            event_id=data["event_id"],
            event_type=data.get("event_type", ""),
            payload=data.get("payload", ""),
            status=data.get("status", "STATUS_UNKNOWN"),
            occurred_at=data.get("occurred_at", 0),
            text_content=data.get("text_content", ""),
            binary_content=data.get("binary_content", ""),
        )


# --- User model for translator tests (Bug 1-4) ---

from dataclasses import dataclass as _dataclass


@_dataclass
class UserResponse:
    """Service A 返回的用户 JSON 响应 — 供测试使用"""
    user_id: int          # int64 — JSON number，可能 > 2^31
    avatar_data: str      # base64 编码的字符串
    contact_type: str     # oneof 判别字段："email" 或 "phone"
    contact_value: str    # oneof 的值
    user_role: str        # enum 名称字符串，如 "ADMIN", "USER", "GUEST"
