"""
Priority-ordered task message wrapper.

Uses a dataclass with ordering so that tasks can be placed in a heap.
"""
from dataclasses import dataclass, field
from typing import Any


@dataclass(order=True)
class PriorityTask:
    """Lower urgency number = higher priority (0=critical, 9=low)

    Comparison order:
     1. urgency (primary sort key — lower = higher priority)
     2. seq     (tie-breaker — insertion order, deterministic & type-safe)
     3. message is excluded from comparison entirely (compare=False)
    """
    urgency: int                    # Primary sort key
    seq: int                        # Tie-breaker: insertion sequence number
    message: Any = field(compare=False)   # Payload — never compared
