"""
API endpoint definitions.
"""
from core.base import BaseProcessor
from models.entities import UserModel
from api.formatters import format_response


def get_entity(entity_id: str) -> dict:
    """Retrieve and format an entity."""
    entity = UserModel(username=entity_id)
    raw = entity.to_dict()
    return format_response(raw)


def list_entities() -> list[dict]:
    """List all entities (stub)."""
    return []
