# DIST2: Raft Consensus Bugs (Brief)

Fix 3 Raft consensus bugs per the Planner's analysis. The bugs are in `raft/node.py`
in the RequestVote handler, AppendEntries handler, and commit logic.

Run `pytest tests/` to verify safety invariants hold under partitions.
