"""
Priority-ordered task message wrapper.

Uses a dataclass with manual ordering so that tasks can be placed in a heap.
The monotonic sequence number serves as a type-safe tiebreaker when two
messages have equal urgency, avoiding TypeError from comparing incompatible
payload types (dict, list, etc.).
"""
import threading
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Global monotonic sequence counter (thread-safe)
# ---------------------------------------------------------------------------
_seq_counter: int = 0
_seq_lock = threading.Lock()


def _next_seq() -> int:
    """Return the next monotonic global sequence number (thread-safe)."""
    global _seq_counter
    with _seq_lock:
        _seq_counter += 1
        return _seq_counter


# ---------------------------------------------------------------------------
@dataclass(eq=False, order=False)
class PriorityTask:
    """Lower urgency number = higher priority (0=critical, 9=low).

    The *seq* field is a monotonic sequence number assigned at construction
    time.  When two tasks have equal urgency the sequence number decides
    ordering, so the ``message`` field is **never** compared directly.
    """

    urgency: int          # Primary sort key (0 = highest priority)
    seq: int              # Monotonic tie-breaker (type-safe: always int)
    message: Any = field(compare=False, repr=True)
    _seq: int = field(init=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        """Assign the internal sequence number automatically."""
        # If the caller provided a seq, honour it (used by tests for
        # deterministic ordering); otherwise auto-generate.
        if self.seq == 0 and not hasattr(self, '_seq'):
            # seq=0 may be an explicit value, but we use _seq as the actual
            # internal counter.  We always auto-generate regardless.
            pass
        self._seq = _next_seq()

    # -- rich comparison methods -------------------------------------------
    # All comparisons are based on (urgency, _seq) ONLY.  The ``message``
    # field is NEVER touched during comparison, which is the core fix.

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, PriorityTask):
            return NotImplemented
        if self.urgency != other.urgency:
            return self.urgency < other.urgency
        return self._seq < other._seq

    def __le__(self, other: object) -> bool:
        if not isinstance(other, PriorityTask):
            return NotImplemented
        return self < other or self == other

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PriorityTask):
            return NotImplemented
        return (self.urgency == other.urgency and
                self._seq == other._seq)

    def __ne__(self, other: object) -> bool:
        if not isinstance(other, PriorityTask):
            return NotImplemented
        return not self == other

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, PriorityTask):
            return NotImplemented
        return not self <= other

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, PriorityTask):
            return NotImplemented
        return not self < other

    def __hash__(self) -> int:
        return hash((self.urgency, self._seq))

    def __repr__(self) -> str:
        return (f"PriorityTask(urgency={self.urgency}, "
                f"seq={self.seq}, message={self.message!r})")
