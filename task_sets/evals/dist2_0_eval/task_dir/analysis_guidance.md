# Analysis Guidance — DIST2_consensus_partition

## Tools to run
- `cat raft/node.py` — find all 3 bug locations
- `cat raft/messages.py` — understand RPC message types
- `cat raft/log.py` — understand log operations
- `python -m pytest tests/test_election.py tests/test_safety.py -v`

## Bug 1: RequestVote — No Log Up-to-Date Check (raft/node.py)

In `handle_request_vote()`:
```python
# BUGGY: grants vote regardless of candidate log freshness
def handle_request_vote(self, msg):
    if msg.term >= self.current_term and self.voted_for in (None, msg.candidate_id):
        self.voted_for = msg.candidate_id
        return RequestVoteResponse(term=self.current_term, vote_granted=True)
    return RequestVoteResponse(term=self.current_term, vote_granted=False)
```

Fix: Add log up-to-date check BEFORE granting vote:
```python
def _log_is_up_to_date(self, last_log_term, last_log_index):
    my_last_term = self.log.last_term()
    my_last_index = self.log.last_index()
    if last_log_term != my_last_term:
        return last_log_term > my_last_term
    return last_log_index >= my_last_index
```

## Bug 2: AppendEntries — No prevLogIndex/prevLogTerm Check (raft/node.py)

In `handle_append_entries()`:
```python
# BUGGY: blindly appends without checking log consistency
def handle_append_entries(self, msg):
    if msg.term >= self.current_term:
        for entry in msg.entries:
            self.log.append(entry)  # BUG: no consistency check
        return AppendEntriesResponse(term=self.current_term, success=True)
    return AppendEntriesResponse(term=self.current_term, success=False)
```

Fix: Check prevLogIndex and prevLogTerm before appending:
```python
# Reject if log doesn't contain matching entry at prevLogIndex
if msg.prev_log_index > 0:
    if self.log.last_index() < msg.prev_log_index:
        return AppendEntriesResponse(success=False)
    if self.log.term_at(msg.prev_log_index) != msg.prev_log_term:
        self.log.truncate_from(msg.prev_log_index)
        return AppendEntriesResponse(success=False)
```

## Bug 3: Commit — Commits Entries from Previous Terms (raft/node.py)

In `try_commit()` or `update_commit_index()`:
```python
# BUGGY: commits any entry that has majority replication
def try_commit(self):
    for n in range(self.commit_index + 1, self.log.last_index() + 1):
        count = sum(1 for m in self.match_index.values() if m >= n)
        if count >= self.quorum_size:
            self.commit_index = n  # BUG: may commit old-term entries
```

Fix: Only commit entries from the current term:
```python
def try_commit(self):
    for n in range(self.commit_index + 1, self.log.last_index() + 1):
        if self.log.term_at(n) != self.current_term:  # Must be current term
            continue
        count = sum(1 for m in self.match_index.values() if m >= n)
        if count >= self.quorum_size:
            self.commit_index = n
```

## Tell Executor
All 3 bugs are in `raft/node.py`. Do not change `raft/network.py`, `raft/messages.py`,
or the test scenarios in `tests/scenarios/`.
