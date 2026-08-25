"""Raft cluster configuration."""

CLUSTER_SIZE = 5
ELECTION_TIMEOUT_MIN = 0.15   # seconds
ELECTION_TIMEOUT_MAX = 0.30   # seconds
HEARTBEAT_INTERVAL = 0.05     # seconds
RPC_TIMEOUT = 0.10            # seconds
QUORUM = 5 // 2 + 1
