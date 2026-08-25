"""
Entity definitions for models.
"""
from core.base import BaseProcessor


class UserModel:
    """Primary entity model."""

    def __init__(self, username: str, data: dict | None = None):
        self.username = username
        self.data = data or {}

    def to_dict(self) -> dict:
        return {
            "username": self.username,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "UserModel":
        return cls(
            username=d["username"],
            data=d.get("data", {}),
        )
