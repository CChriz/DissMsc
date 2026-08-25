"""
Simulated in-process network for Raft testing.

DO NOT MODIFY — the grader verifies this file is unchanged.

Nodes communicate via thread-safe queues. The network supports:
- Point-to-point message delivery
- Simulated partitions (bidirectional or one-way)
- Message loss simulation (for future use)
"""
import threading
import queue
from typing import Dict, FrozenSet, Set, Tuple, Any


class SimulatedNetwork:
    """
    In-process network simulation for a 5-node Raft cluster.

    Messages are delivered synchronously via put() on the recipient's inbox queue.
    Partitioned links silently drop messages in both directions.
    """

    def __init__(self):
        self._lock = threading.Lock()
        # Set of (from_id, to_id) pairs that are currently partitioned
        self._partitioned_links: Set[Tuple[int, int]] = set()
        # Per-node message queues
        self._queues: Dict[int, queue.Queue] = {}

    def register(self, node_id: int) -> queue.Queue:
        """Register a node and return its inbox queue."""
        with self._lock:
            q = queue.Queue()
            self._queues[node_id] = q
            return q

    def send(self, from_id: int, to_id: int, message: Any) -> bool:
        """
        Send a message from one node to another.

        Returns True if delivered, False if the link is partitioned.
        """
        with self._lock:
            if (from_id, to_id) in self._partitioned_links:
                return False
            if to_id not in self._queues:
                return False
            self._queues[to_id].put((from_id, message))
            return True

    def partition(self, node_a: int, node_b: int) -> None:
        """Create a bidirectional partition between two nodes."""
        with self._lock:
            self._partitioned_links.add((node_a, node_b))
            self._partitioned_links.add((node_b, node_a))

    def heal(self, node_a: int, node_b: int) -> None:
        """Heal a partition between two nodes."""
        with self._lock:
            self._partitioned_links.discard((node_a, node_b))
            self._partitioned_links.discard((node_b, node_a))

    def heal_all(self) -> None:
        """Remove all partitions."""
        with self._lock:
            self._partitioned_links.clear()

    def is_partitioned(self, from_id: int, to_id: int) -> bool:
        """Check if a link is currently partitioned."""
        with self._lock:
            return (from_id, to_id) in self._partitioned_links

    def isolate(self, node_id: int, all_node_ids: list) -> None:
        """Isolate a node from all other nodes (partition all links to/from it)."""
        for other_id in all_node_ids:
            if other_id != node_id:
                self.partition(node_id, other_id)

    def unisolate(self, node_id: int, all_node_ids: list) -> None:
        """Remove all partitions involving a node."""
        for other_id in all_node_ids:
            if other_id != node_id:
                self.heal(node_id, other_id)
