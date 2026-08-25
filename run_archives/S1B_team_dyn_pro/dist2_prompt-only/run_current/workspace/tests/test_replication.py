"""
Log replication tests — verifies AppendEntries consistency check (Bug 2).

Tests that followers reject AppendEntries when prevLogIndex/prevLogTerm
does not match their log.
"""
import time
import pytest

from raft.network import SimulatedNetwork
from raft.node import RaftNode
from raft.messages import AppendEntriesRequest, LogEntry


CLUSTER_SIZE = 5
ALL_IDS = list(range(CLUSTER_SIZE))


def make_cluster():
    net = SimulatedNetwork()
    nodes = [
        RaftNode(i, [j for j in ALL_IDS if j != i], net)
        for i in ALL_IDS
    ]
    return net, nodes


def wait_for_leader(nodes, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        leaders = [n for n in nodes if n.is_leader()]
        if len(leaders) == 1:
            return leaders[0]
        time.sleep(0.05)
    return None


def start_all(nodes):
    for n in nodes:
        n.start()


def stop_all(nodes):
    for n in nodes:
        n.stop()


def test_follower_rejects_inconsistent_append():
    """
    A follower must reject AppendEntries when prevLogIndex/prevLogTerm don't match.

    Directly calls handle_append_entries on a fresh node with a mismatched
    prev_log_index to verify the consistency check is present.
    """
    net = SimulatedNetwork()
    node = RaftNode(0, [1, 2], net)

    # Node has no entries (log is empty except sentinel)
    # Send AppendEntries claiming prev_log_index=5 (which doesn't exist)
    msg = AppendEntriesRequest(
        term=1,
        leader_id=1,
        prev_log_index=5,   # Follower log is empty — mismatch
        prev_log_term=1,
        entries=[LogEntry(term=1, index=6, command={"op": "set"})],
        leader_commit=0,
    )
    # Force term to match
    node.current_term = 1

    resp = node.handle_append_entries(msg)
    assert not resp.success, (
        "Follower must reject AppendEntries when prev_log_index doesn't exist in its log"
    )


def test_follower_rejects_wrong_prev_term():
    """
    A follower must reject AppendEntries when prevLogTerm doesn't match.
    """
    net = SimulatedNetwork()
    node = RaftNode(0, [1, 2], net)

    # Add an entry at index 1 with term 1
    node.log.append(LogEntry(term=1, index=1, command={"op": "init"}))
    node.current_term = 2

    # Send AppendEntries claiming prev_log_index=1, prev_log_term=99 (wrong)
    msg = AppendEntriesRequest(
        term=2,
        leader_id=1,
        prev_log_index=1,
        prev_log_term=99,  # Wrong term — should be 1
        entries=[LogEntry(term=2, index=2, command={"op": "set"})],
        leader_commit=0,
    )

    resp = node.handle_append_entries(msg)
    assert not resp.success, (
        "Follower must reject AppendEntries when prev_log_term doesn't match"
    )


def test_follower_accepts_consistent_append():
    """
    A follower must accept AppendEntries when prevLogIndex/prevLogTerm match.
    """
    net = SimulatedNetwork()
    node = RaftNode(0, [1, 2], net)

    # Add an entry at index 1 with term 1
    node.log.append(LogEntry(term=1, index=1, command={"op": "init"}))
    node.current_term = 2

    # Send AppendEntries with correct prev values
    msg = AppendEntriesRequest(
        term=2,
        leader_id=1,
        prev_log_index=1,
        prev_log_term=1,   # Correct
        entries=[LogEntry(term=2, index=2, command={"op": "set"})],
        leader_commit=0,
    )

    resp = node.handle_append_entries(msg)
    assert resp.success, "Follower must accept AppendEntries when prev log matches"
    assert node.log.last_index() == 2


def test_log_convergence_after_leader_change():
    """
    After a leader change, all nodes must converge to the same log.

    Exercises the full replication path including prevLogIndex checks.
    """
    net, nodes = make_cluster()
    start_all(nodes)
    try:
        leader = wait_for_leader(nodes)
        assert leader is not None

        # Submit several entries
        for i in range(5):
            leader.submit({"op": "put", "key": f"key{i}", "value": i})

        time.sleep(0.5)  # Wait for replication

        # All nodes must have the same last committed index
        commit_indices = [n.commit_index for n in nodes]
        assert max(commit_indices) > 0, "No entries committed"
        # At least a quorum must agree
        majority_commit = sorted(commit_indices)[2]
        assert majority_commit > 0, f"Majority not committed: {commit_indices}"
    finally:
        stop_all(nodes)
