"""
Priority-ordered task message wrapper.

``PriorityTask`` is the heap item used by ``TaskQueue``.  It orders by
``urgency`` (ascending: lower urgency = higher priority, 0=critical), breaking
ties deterministically by ``seq`` (FIFO).  The payload ``message`` is excluded
from all comparisons so non-comparable payloads (dict, list, ...) are safe.
"""
from dataclasses import dataclass, field
from typing import Any


@dataclass(order=True)
class PriorityTask:
    """Lower urgency number = higher priority (0=critical, 9=low).

    ``seq`` is a monotonically increasing insertion sequence number used as a
    deterministic FIFO tie-breaker when two tasks share the same urgency.

    BUG 3 fix: ``message`` is marked ``compare=False``, so it never takes part
    in ordering.  Equal-urgency tasks therefore fall through to ``seq`` instead
    of comparing payloads, which previously raised ``TypeError`` for
    non-comparable payloads such as ``dict`` or ``list``.
    """
    urgency: int
    seq: int
    message: Any = field(compare=False)
