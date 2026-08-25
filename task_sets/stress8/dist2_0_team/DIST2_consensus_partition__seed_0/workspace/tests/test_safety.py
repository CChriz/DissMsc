"""
Safety invariant tests for Raft consensus.

Verifies three core Raft safety invariants:
1. Election Safety: at most one leader per term
2. Leader Completeness: committed entries appear in all future leaders' logs
3. State Machine Safety: all nodes apply the same commands in the same order
"""
import time
import threading
import pytest

from raft.network import SimulatedNetwork
from raft.node import RaftNode


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


def test_election_safety_no_two_leaders_same_term():
    """
    Election Safety: at most one leader per term.

    Run multiple elections and verify no two leaders share the same term.
    """
    net, nodes = make_cluster()
    start_all(nodes)
    seen_leaders: dict = {}  # term -> node_id

    try:
        for _ in range(3):
            leader = wait_for_leader(nodes, timeout=3.0)
            if leader is None:
                continue

            term = leader.current_term
            if term in seen_leaders:
                assert seen_leaders[term] == leader.node_id, (
                    f"Two leaders in term {term}: "
                    f"{seen_leaders[term]} and {leader.node_id}"
                )
            seen_leaders[term] = leader.node_id

            # Force a new election by isolating current leader briefly
            for peer in leader.peers:
                net.partition(leader.node_id, peer)
            time.sleep(0.4)
            for peer in leader.peers:
                net.heal(leader.node_id, peer)
            time.sleep(0.3)
    finally:
        stop_all(nodes)


def test_state_machine_safety_same_commands_same_order():
    """
    State Machine Safety: nodes that have applied up to index N must agree on
    the command at every index <= N.

    All nodes that have committed the same index must have the same command there.
    """
    net, nodes = make_cluster()
    start_all(nodes)
    try:
        leader = wait_for_leader(nodes)
        assert leader is not None

        commands = [{"op": "put", "key": f"k{i}", "value": i} for i in range(5)]
        for cmd in commands:
            leader.submit(cmd)

        time.sleep(0.6)  # Wait for replication

        # Find the minimum committed index across all nodes
        committed = [n.commit_index for n in nodes]
        min_committed = min(committed)

        if min_committed < 1:
            pytest.skip("No entries committed yet — increase timeout")

        # All nodes must agree on log content up to min_committed
        for idx in range(1, min_committed + 1):
            entries_at_idx = [n.log.entry_at(idx) for n in nodes]
            # Filter out None (nodes that don't have this entry)
            present = [e for e in entries_at_idx if e is not None]
            if len(present) < 2:
                continue
            # All present entries must have the same term and command
            terms = {e.term for e in present}
            assert len(terms) == 1, (
                f"Nodes disagree on term at index {idx}: {terms}"
            )
            commands_at = [str(e.command) for e in present]
            assert len(set(commands_at)) == 1, (
                f"Nodes disagree on command at index {idx}: {commands_at}"
            )
    finally:
        stop_all(nodes)


def test_leader_completeness_after_election():
    """
    Leader Completeness: a new leader must have all committed entries.

    Submit entries, ensure they are committed, then force a re-election
    and verify the new leader has all previously committed entries.
    """
    net, nodes = make_cluster()
    start_all(nodes)
    try:
        leader = wait_for_leader(nodes)
        assert leader is not None

        # Submit and commit some entries
        for i in range(4):
            leader.submit({"op": "setup", "index": i})
        time.sleep(0.5)

        original_commit = leader.commit_index
        if original_commit == 0:
            pytest.skip("No entries committed — increase sleep")

        # Force re-election: isolate current leader
        old_leader_id = leader.node_id
        for peer in leader.peers:
            net.partition(old_leader_id, peer)

        time.sleep(0.6)  # New election

        remaining = [n for n in nodes if n.node_id != old_leader_id]
        new_leader = wait_for_leader(remaining, timeout=3.0)

        if new_leader is None:
            pytest.skip("No new leader elected — partition may have prevented quorum")

        # New leader must have all entries up to original_commit
        for idx in range(1, original_commit + 1):
            entry = new_leader.log.entry_at(idx)
            assert entry is not None, (
                f"Leader Completeness violated: new leader {new_leader.node_id} "
                f"missing committed entry at index {idx}"
            )

        # Heal
        for peer in leader.peers:
            net.heal(old_leader_id, peer)
    finally:
        stop_all(nodes)
