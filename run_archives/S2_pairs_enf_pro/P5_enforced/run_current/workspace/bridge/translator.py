"""
Bridge translator: converts Service A JSON dicts into Service B messages.

FIXED: All 4 bugs resolved — see inline comments for details.
"""
import base64
from service_b.schema import EventMessage, EventStatus
from service_a.models import UserResponse
from service_b.schema import UserMessage, ROLE_ENUM_MAP

STATUS_MAP = {
    "STATUS_UNKNOWN": 0,
    "STATUS_ACTIVE": 1,
    "STATUS_INACTIVE": 2,
    "STATUS_PENDING": 3,
}


def translate_event_streaming(data: dict) -> EventMessage:
    """Translate JSON data from Service A to EventMessage for Service B."""
    msg = EventMessage()

    # Bug 1 FIXED: int64 — no bitmask truncation, Python int handles arbitrary precision
    msg.event_id = int(data.get("event_id", 0))

    msg.event_type = data.get("event_type", "")
    msg.occurred_at = int(data.get("occurred_at", 0))

    # Bug 2 FIXED: base64-decode payload string to raw bytes
    msg.payload = base64.b64decode(data.get("payload", ""))

    # Bug 3 FIXED: oneof — set exactly one of text_content / binary_content
    text_content = data.get("text_content", "")
    binary_content = data.get("binary_content", "")
    if binary_content:
        msg.binary_content = base64.b64decode(binary_content)
    elif text_content:
        msg.text_content = text_content

    # Bug 4 FIXED: map enum string to integer code via STATUS_MAP
    raw_status = data.get("status", "STATUS_UNKNOWN")
    msg.status = STATUS_MAP.get(raw_status, 0)

    return msg


# Alias used by tests
translate_event = translate_event_streaming


def translate_user(response: UserResponse) -> UserMessage:
    """将 Service A 的 UserResponse 翻译为 Service B 的 UserMessage 格式。

    测试接口 — 验证 int64/bytes/oneof/enum 四个翻译修复。
    """

    # Bug 1 修复：int64 — 不截断，Python int 原生支持任意精度
    user_id = int(response.user_id)

    # Bug 2 修复：base64 解码
    avatar_data = base64.b64decode(response.avatar_data)

    # Bug 3 修复：oneof — 只设置一个变体
    email = None
    phone = None
    if response.contact_type == "email":
        email = response.contact_value
    elif response.contact_type == "phone":
        phone = response.contact_value

    # Bug 4 修复：enum 字符串 → 整数
    user_role = ROLE_ENUM_MAP.get(response.user_role, 0)

    return UserMessage(
        user_id=user_id,
        avatar_data=avatar_data,
        email=email,
        phone=phone,
        user_role=user_role,
    )
