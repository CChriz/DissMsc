import base64
import pytest
from service_a.models import UserResponse
from bridge.translator import translate_user


class TestInt64Translation:
    """Bug 1: int64 不应被截断"""

    def test_int64_within_32bit(self):
        """32-bit 范围内的值应保持不变"""
        resp = UserResponse(
            user_id=42,
            avatar_data="",
            contact_type="email",
            contact_value="a@b.com",
            user_role="ADMIN",
        )
        msg = translate_user(resp)
        assert msg.user_id == 42

    def test_int64_beyond_32bit(self):
        """超过 32-bit 的值应保持完整，不能截断"""
        large_id = 0x100000001  # 4294967297, 超出 32-bit
        resp = UserResponse(
            user_id=large_id,
            avatar_data="",
            contact_type="email",
            contact_value="a@b.com",
            user_role="ADMIN",
        )
        msg = translate_user(resp)
        assert msg.user_id == 4294967297
        assert isinstance(msg.user_id, int)


class TestBytesTranslation:
    """Bug 2: base64 字符串应解码为 bytes"""

    def test_base64_decode(self):
        b64 = base64.b64encode(b"hello world").decode()
        resp = UserResponse(
            user_id=1,
            avatar_data=b64,
            contact_type="email",
            contact_value="a@b.com",
            user_role="USER",
        )
        msg = translate_user(resp)
        assert msg.avatar_data == b"hello world"
        assert isinstance(msg.avatar_data, bytes)


class TestOneofTranslation:
    """Bug 3: oneof 必须恰好设置一个变体"""

    def test_oneof_email(self):
        resp = UserResponse(
            user_id=1,
            avatar_data="",
            contact_type="email",
            contact_value="test@example.com",
            user_role="USER",
        )
        msg = translate_user(resp)
        assert msg.email == "test@example.com"
        assert msg.phone is None

    def test_oneof_phone(self):
        resp = UserResponse(
            user_id=1,
            avatar_data="",
            contact_type="phone",
            contact_value="+1234567890",
            user_role="USER",
        )
        msg = translate_user(resp)
        assert msg.phone == "+1234567890"
        assert msg.email is None


class TestEnumTranslation:
    """Bug 4: enum 字符串名应映射为整数"""

    def test_enum_admin(self):
        resp = UserResponse(
            user_id=1,
            avatar_data="",
            contact_type="email",
            contact_value="a@b.com",
            user_role="ADMIN",
        )
        msg = translate_user(resp)
        assert msg.user_role == 1

    def test_enum_user(self):
        resp = UserResponse(
            user_id=1,
            avatar_data="",
            contact_type="email",
            contact_value="a@b.com",
            user_role="USER",
        )
        msg = translate_user(resp)
        assert msg.user_role == 2

    def test_enum_guest(self):
        resp = UserResponse(
            user_id=1,
            avatar_data="",
            contact_type="email",
            contact_value="a@b.com",
            user_role="GUEST",
        )
        msg = translate_user(resp)
        assert msg.user_role == 3

    def test_enum_unknown_default(self):
        resp = UserResponse(
            user_id=1,
            avatar_data="",
            contact_type="email",
            contact_value="a@b.com",
            user_role="INVALID_ROLE",
        )
        msg = translate_user(resp)
        assert msg.user_role == 0  # 未知枚举默认 0
