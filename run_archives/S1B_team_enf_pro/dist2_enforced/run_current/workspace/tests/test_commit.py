"""
Commit safety tests — verifies Bug 3 fix: leaders must not commit
entries from previous terms by counting replicas alone.

From the Raft paper (Section 5.4.2):
"Raft never commits log entries from previous terms by counting replicas."
"""
import time
import pytest

from raft.network import SimulatedNetwork
from raft.node import RaftNode, NodeState
from raft.messages import LogEntry


CLUSTER_SIZE = 5
ALL_IDS = list(range(CLUSTER_SIZE))


def test_leader_does_not_commit_old_term_entry_directly():
    """
    A leader must not advance commit_index to an old-term entry
    even if a majority of match_index values cover it.

    Per Raft Section 5.4.2: only current-term entries can be directly committed.
    Old entries are committed indirectly via log matching.
    """
    net = SimulatedNetwork()
    # Build a standalone leader node (no running peers — we control state directly)
    node = RaftNode(0, list(range(1, CLUSTER_SIZE)), net)

    # Simulate the node as a leader in term 3
    node.current_term = 3
    node.state = NodeState.LEADER

    # Add a log entry from term 1 (old term) at index 1
    node.log.append(LogEntry(term=1, index=1, command={"op": "old_entry"}))

    # Simulate majority replication of this old-term entry
    for peer in node.peers:
        node.match_index[peer] = 1
    node.match_index[node.node_id] = 1

    # With Bug 3, this would commit index 1 (old-term entry)
    node._try_commit()

    # The fixed implementation must NOT commit an old-term entry directly
    assert node.commit_index == 0, (
        f"Bug 3 present: committed old-term entry directly. "
        f"commit_index={node.commit_index}, entry term=1, current_term=3"
    )


def test_current_term_entry_can_be_committed():
    """
    A leader can commit an entry from its current term once majority replicated.
    """
    net = SimulatedNetwork()
    node = RaftNode(0, list(range(1, CLUSTER_SIZE)), net)

    node.current_term = 3
    node.state = NodeState.LEADER

    # Add a current-term entry
    node.log.append(LogEntry(term=3, index=1, command={"op": "current_entry"}))

    # Simulate majority replication
    for peer in node.peers:
        node.match_index[peer] = 1
    node.match_index[node.node_id] = 1

    node._try_commit()

    assert node.commit_index == 1, (
        f"Current-term entry must be committable. commit_index={node.commit_index}"
    )


def test_old_term_entry_committed_indirectly():
    """
    An old-term entry is committed indirectly when a current-term entry
    at a higher index is committed (log matching property).
    """
    net = SimulatedNetwork()
    node = RaftNode(0, list(range(1, CLUSTER_SIZE)), net)

    node.current_term = 3
    node.state = NodeState.LEADER

    # Index 1: old-term entry
    node.log.append(LogEntry(term=1, index=1, command={"op": "old_entry"}))
    # Index 2: current-term entry
    node.log.append(LogEntry(term=3, index=2, command={"op": "new_entry"}))

    # Simulate majority replication of both entries
    for peer in node.peers:
        node.match_index[peer] = 2
    node.match_index[node.node_id] = 2

    node._try_commit()

    # Both should be committed now (index 2 is current-term, commits index 1 too)
    assert node.commit_index == 2, (
        f"Old-term entry should be committed indirectly via current-term entry. "
        f"commit_index={node.commit_index}"
    )
    # Both entries should be applied
    assert node.last_applied == 2
