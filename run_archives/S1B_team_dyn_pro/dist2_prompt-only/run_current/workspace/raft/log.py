"""
Replicated log for Raft consensus.

The log is 1-indexed. Index 0 is a sentinel (empty entry at term 0).
"""
from typing import Any, List, Optional
from raft.messages import LogEntry


class ReplicatedLog:
    """Thread-safe replicated log with append, truncate, and query operations."""

    def __init__(self):
        # Index 0 is a sentinel; real entries start at index 1
        self._entries: List[LogEntry] = [LogEntry(term=0, index=0, command=None)]

    def append(self, entry: LogEntry) -> None:
        """Append an entry. Entry must have index == last_index() + 1."""
        self._entries.append(entry)

    def last_index(self) -> int:
        """Return the index of the last log entry (0 if log is empty)."""
        return len(self._entries) - 1

    def last_term(self) -> int:
        """Return the term of the last log entry (0 if log is empty)."""
        return self._entries[-1].term

    def term_at(self, index: int) -> int:
        """Return the term of the entry at the given index."""
        if index < 0 or index >= len(self._entries):
            return 0
        return self._entries[index].term

    def entry_at(self, index: int) -> Optional[LogEntry]:
        """Return the entry at the given index, or None if out of range."""
        if index <= 0 or index >= len(self._entries):
            return None
        return self._entries[index]

    def entries_from(self, start_index: int) -> List[LogEntry]:
        """Return all entries with index >= start_index."""
        if start_index >= len(self._entries):
            return []
        return list(self._entries[start_index:])

    def truncate_from(self, index: int) -> None:
        """Remove all entries with index >= the given index."""
        if index > 0 and index < len(self._entries):
            self._entries = self._entries[:index]

    def __len__(self) -> int:
        return len(self._entries) - 1  # Exclude sentinel
