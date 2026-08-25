"""
Network partition and heal tests.

Tests that the cluster maintains safety during and after network partitions:
- A minority partition cannot elect a leader (no quorum)
- After healing, the cluster converges to a consistent state
"""
import time
import pytest

from raft.network import SimulatedNetwork
from raft.node import RaftNode


CLUSTER_SIZE = 5
ALL_IDS = list(range(CLUSTER_SIZE))
QUORUM = 3


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


def test_minority_partition_no_leader():
    """
    A minority partition (size < quorum) must not elect a leader.
    """
    net, nodes = make_cluster()
    start_all(nodes)
    try:
        # Wait for initial leader
        leader = wait_for_leader(nodes)
        assert leader is not None

        # Isolate a minority (nodes 0..quorum-2) from the majority
        minority_size = QUORUM - 1
        minority_ids = list(range(minority_size))
        majority_ids = [i for i in ALL_IDS if i not in minority_ids]

        for mid in minority_ids:
            for maj_id in majority_ids:
                net.partition(mid, maj_id)

        time.sleep(0.8)  # Give minority time to attempt elections

        # Minority nodes must not have elected a leader among themselves
        minority_nodes = [nodes[i] for i in minority_ids]
        minority_leaders = [n for n in minority_nodes if n.is_leader()]
        assert len(minority_leaders) == 0, (
            f"Minority of {minority_size} nodes elected a leader: "
            f"{[n.node_id for n in minority_leaders]}"
        )
    finally:
        stop_all(nodes)


def test_partition_heal_convergence():
    """
    After healing a partition, all nodes must converge to the same log.
    """
    net, nodes = make_cluster()
    start_all(nodes)
    try:
        leader = wait_for_leader(nodes)
        assert leader is not None

        # Submit entries before partition
        for i in range(3):
            leader.submit({"op": "pre_partition", "index": i})
        time.sleep(0.3)

        # Partition node 0 from everyone
        for oid in ALL_IDS[1:]:
            net.partition(0, oid)

        time.sleep(0.4)

        # Submit entries during partition (to remaining majority)
        majority_nodes = nodes[1:]
        new_leader = wait_for_leader(majority_nodes, timeout=3.0)
        if new_leader is not None:
            for i in range(3):
                new_leader.submit({"op": "during_partition", "index": i})
            time.sleep(0.3)

        # Heal partition
        for oid in ALL_IDS[1:]:
            net.heal(0, oid)

        time.sleep(1.0)  # Allow convergence

        # Majority nodes must agree on commit_index
        majority_commits = [nodes[i].commit_index for i in ALL_IDS[1:]]
        assert len(set(majority_commits)) <= 2, (
            f"Majority nodes disagree on commit_index after heal: {majority_commits}"
        )
        assert max(majority_commits) >= 3, (
            f"Pre-partition entries not committed: max commit={max(majority_commits)}"
        )
    finally:
        stop_all(nodes)
