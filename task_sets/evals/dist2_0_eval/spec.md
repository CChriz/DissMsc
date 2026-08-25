# DIST2: Raft Consensus — Network Partition Safety

## Goal
Fix 3 bugs in the Raft consensus protocol implementation that cause safety violations
during network partitions.

## Requirements
Per the Raft paper (Ongaro & Ousterhout 2014):
1. RequestVote RPC must reject candidates whose log is less up-to-date than the voter's log
   (compare last log term first, then last log index)
2. AppendEntries RPC must check prevLogIndex and prevLogTerm before appending entries
   (reject if the follower's log doesn't match at that position)
3. Leaders must only commit log entries from their current term
   (never commit entries from previous terms by counting replicas alone)
4. All tests must pass: `pytest tests/`

## Supporting Documents
- `raft/node.py` — Main Raft node implementation (all 3 bugs here)
- `raft/messages.py` — RequestVote and AppendEntries RPC types
- `raft/log.py` — Replicated log operations
- `tests/scenarios/` — JSON scenarios for partition simulations

## Important
The implementation uses in-process simulation (no real network). Nodes communicate
via thread-safe queues. The `network.py` module supports simulated partitions.
Do not change the network simulation or message format — only fix the consensus logic
in `raft/node.py`.
