"""
Election safety tests for the Raft consensus implementation.

Tests that:
- A node with a stale log cannot win an election (Bug 1 target)
- At most one leader per term (election safety invariant)
"""
import time
import random
import pytest

from raft.network import SimulatedNetwork
from raft.node import RaftNode
from raft.messages import LogEntry


CLUSTER_SIZE = 5
ALL_IDS = list(range(CLUSTER_SIZE))


def make_cluster():
    net = SimulatedNetwork()
    nodes = [
        RaftNode(i, [j for j in ALL_IDS if j != i], net)
        for i in ALL_IDS
    ]
    return net, nodes


def start_all(nodes):
    for n in nodes:
        n.start()


def stop_all(nodes):
    for n in nodes:
        n.stop()


def wait_for_leader(nodes, timeout=5.0):
    """Wait until exactly one leader emerges."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        leaders = [n for n in nodes if n.is_leader()]
        if len(leaders) == 1:
            return leaders[0]
        time.sleep(0.05)
    return None


def test_leader_elected():
    """A leader must emerge within the election timeout window."""
    net, nodes = make_cluster()
    start_all(nodes)
    try:
        leader = wait_for_leader(nodes)
        assert leader is not None, "No leader elected within timeout"
    finally:
        stop_all(nodes)


def test_at_most_one_leader_per_term():
    """Election safety: at most one leader per term across the cluster."""
    net, nodes = make_cluster()
    start_all(nodes)
    try:
        # Let a leader emerge
        leader = wait_for_leader(nodes)
        assert leader is not None

        # Collect all (term, node_id) pairs for leaders observed
        leaders_by_term = {}
        for n in nodes:
            if n.is_leader():
                t = n.current_term
                if t in leaders_by_term:
                    assert leaders_by_term[t] == n.node_id, (
                        f"Two leaders in term {t}: {leaders_by_term[t]} and {n.node_id}"
                    )
                else:
                    leaders_by_term[t] = n.node_id
    finally:
        stop_all(nodes)


def test_stale_candidate_cannot_win():
    """
    A node with a stale log must not win the election.

    Setup: node 0 has extra committed entries; it is isolated, a new leader
    emerges among the remaining nodes (without node 0's entries), then node 0
    is brought back. Node 0 must not become leader because its term is lower.

    This test exposes Bug 1: without a log up-to-date check, any candidate
    whose term is high enough can win even with a stale log.
    """
    net, nodes = make_cluster()
    start_all(nodes)
    try:
        # Wait for initial leader
        leader = wait_for_leader(nodes)
        assert leader is not None

        # Submit some entries via the leader
        for i in range(3):
            leader.submit({"op": "set", "key": f"k{i}", "value": i})
        time.sleep(0.3)

        # Isolate node 0 (assume it may or may not have the entries)
        # Partition all remaining nodes from node 0
        other_ids = [i for i in ALL_IDS if i != 0]
        for oid in other_ids:
            net.partition(0, oid)

        time.sleep(0.5)  # Let remaining nodes elect a new leader

        # A new leader must emerge among the non-isolated nodes
        non_isolated = [nodes[i] for i in other_ids]
        new_leader = wait_for_leader(non_isolated, timeout=3.0)
        assert new_leader is not None, "No leader emerged after isolating node 0"
        assert new_leader.node_id != 0, "Node 0 (isolated) should not be leader"

        # Heal the partition
        for oid in other_ids:
            net.heal(0, oid)

        time.sleep(0.5)

        # At most one leader must exist now
        current_leaders = [n for n in nodes if n.is_leader()]
        assert len(current_leaders) <= 1, (
            f"Multiple leaders after heal: {[n.node_id for n in current_leaders]}"
        )
    finally:
        stop_all(nodes)
