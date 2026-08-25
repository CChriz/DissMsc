"""
KVStore state machine for Raft — key-value store.

Supports Put/Get operations.
"""
from typing import Any, Dict, Optional


class KVStore:
    """Simple key-value store state machine."""

    def __init__(self):
        self._store: Dict[str, Any] = {}

    def apply(self, command: Any) -> Any:
        """Apply a log command to the state machine and return the result."""
        if command is None:
            return None
        op = command.get("op")
        key = command.get("key")
        if op == "put":
            self._store[key] = command.get("value")
            return True
        elif op == "get":
            return self._store.get(key)
        elif op == "delete":
            return self._store.pop(key, None)
        return None

    def snapshot(self) -> dict:
        """Return a copy of the current state."""
        return dict(self._store)

    def restore(self, snapshot: dict) -> None:
        """Restore state from a snapshot."""
        self._store = dict(snapshot)
