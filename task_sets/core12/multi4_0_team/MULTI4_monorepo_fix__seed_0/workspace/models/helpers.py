"""
Helper functions for models.

Bug 1: Imports format_response from api.formatters,
creating a circular dependency:
  models -> api -> core -> models

Fix: Import from utils.formatters instead (where it should live).
"""
# Bug 1: circular import — models should NOT import from api
from api.formatters import format_response
from models.entities import UserModel


def serialize_entity(entity: UserModel) -> str:
    """Serialize an entity to a formatted string."""
    raw = entity.to_dict()
    return format_response(raw)


def validate_entity(entity: UserModel) -> bool:
    """Validate that an entity has required fields."""
    return bool(entity.username)
