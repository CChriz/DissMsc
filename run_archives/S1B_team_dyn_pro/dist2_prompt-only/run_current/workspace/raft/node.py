"""
Raft node implementation.

WARNING: This file contains 3 known bugs for testing purposes.

Bug 1 (handle_request_vote): Does not check log up-to-date-ness before granting vote.
Bug 2 (handle_append_entries): Does not check prevLogIndex/prevLogTerm before appending.
Bug 3 (_try_commit): Commits entries from any term, not just the current term.

All 3 bugs must be fixed. Only modify this file.
"""
import threading
import queue
import time
import random
from typing import Dict, List, Optional, Set

from raft.messages import (
    LogEntry,
    RequestVoteRequest,
    RequestVoteResponse,
    AppendEntriesRequest,
    AppendEntriesResponse,
)
from raft.log import ReplicatedLog
from raft.config import ELECTION_TIMEOUT_MIN, ELECTION_TIMEOUT_MAX, HEARTBEAT_INTERVAL


class NodeState:
    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    LEADER = "leader"


class RaftNode:
    """
    Raft consensus node.

    Implements leader election, log replication, and commit logic per the Raft paper.
    Uses in-process thread + queue communication (no real networking).
    """

    def __init__(self, node_id: int, peers: List[int], network):
        self.node_id = node_id
        self.peers = peers
        self.network = network
        self._quorum = 3

        # Persistent state (would be written to stable storage in real Raft)
        self.current_term = 0
        self.voted_for: Optional[int] = None
        self.log = ReplicatedLog()

        # Volatile state
        self.state = NodeState.FOLLOWER
        self.leader_id: Optional[int] = None
        self.commit_index = 0
        self.last_applied = 0

        # Leader-only state (initialized on election)
        self.next_index: Dict[int, int] = {}
        self.match_index: Dict[int, int] = {}

        self._lock = threading.RLock()
        self._inbox = network.register(node_id)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_heartbeat = time.monotonic()
        self._election_timeout = self._random_election_timeout()
        self._votes_received: Set[int] = set()

        # Applied commands (for test verification)
        self.applied: List[LogEntry] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the node's background thread."""
        self._running = True
        self._thread = threading.Thread(
            target=self._run, name=f"raft-node-{self.node_id}", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the node's background thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def submit(self, command) -> Optional[int]:
        """
        Submit a command to the cluster (leader only).

        Returns the log index if accepted, or None if this node is not the leader.
        """
        with self._lock:
            if self.state != NodeState.LEADER:
                return None
            index = self.log.last_index() + 1
            entry = LogEntry(term=self.current_term, index=index, command=command)
            self.log.append(entry)
            self.match_index[self.node_id] = index
            self._broadcast_append_entries()
            return index

    def is_leader(self) -> bool:
        with self._lock:
            return self.state == NodeState.LEADER

    # ------------------------------------------------------------------
    # RPC Handlers — called by the message loop
    # ------------------------------------------------------------------

    def handle_request_vote(self, msg: RequestVoteRequest) -> RequestVoteResponse:
        with self._lock:
            # Update term if needed
            if msg.term > self.current_term:
                self._become_follower(msg.term)

            if msg.term < self.current_term:
                return RequestVoteResponse(self.current_term, False)

            # Check log up-to-date-ness per Raft §5.4.1
            last_log_term = self.log.last_term()
            last_log_index = self.log.last_index()
            log_ok = (
                msg.last_log_term > last_log_term
                or (msg.last_log_term == last_log_term and msg.last_log_index >= last_log_index)
            )
            can_vote = (
                (self.voted_for is None or self.voted_for == msg.candidate_id)
                and log_ok
            )
            if can_vote:
                self.voted_for = msg.candidate_id
                self._reset_election_timeout()
                return RequestVoteResponse(self.current_term, True)
            return RequestVoteResponse(self.current_term, False)

    def handle_append_entries(self, msg: AppendEntriesRequest) -> AppendEntriesResponse:
        with self._lock:
            # Update term if needed
            if msg.term > self.current_term:
                self._become_follower(msg.term)

            if msg.term < self.current_term:
                return AppendEntriesResponse(self.current_term, False)

            # Valid leader contact — reset election timeout
            self._reset_election_timeout()
            self.leader_id = msg.leader_id
            if self.state != NodeState.FOLLOWER:
                self._become_follower(msg.term)

            # Consistency check: verify follower's log matches at prevLogIndex/prevLogTerm
            if msg.prev_log_index > 0:
                if self.log.last_index() < msg.prev_log_index:
                    return AppendEntriesResponse(self.current_term, False, self.log.last_index())
                if self.log.term_at(msg.prev_log_index) != msg.prev_log_term:
                    # Conflict: truncate the log from prev_log_index to remove conflicting entries
                    self.log.truncate_from(msg.prev_log_index)
                    return AppendEntriesResponse(self.current_term, False, self.log.last_index())

            for entry in msg.entries:
                # Overwrite conflicting entries and append new ones
                if entry.index <= self.log.last_index():
                    if self.log.term_at(entry.index) != entry.term:
                        self.log.truncate_from(entry.index)
                        self.log.append(entry)
                else:
                    self.log.append(entry)

            # Update commit index
            if msg.leader_commit > self.commit_index:
                self.commit_index = min(msg.leader_commit, self.log.last_index())
                self._apply_committed()

            return AppendEntriesResponse(self.current_term, True, self.log.last_index())

    def handle_request_vote_response(self, sender: int, msg: RequestVoteResponse) -> None:
        with self._lock:
            if msg.term > self.current_term:
                self._become_follower(msg.term)
                return

            if self.state != NodeState.CANDIDATE:
                return
            if msg.term != self.current_term:
                return

            if msg.vote_granted:
                self._votes_received.add(sender)
                if len(self._votes_received) >= self._quorum:
                    self._become_leader()

    def handle_append_entries_response(
        self, sender: int, msg: AppendEntriesResponse
    ) -> None:
        with self._lock:
            if msg.term > self.current_term:
                self._become_follower(msg.term)
                return

            if self.state != NodeState.LEADER:
                return

            if msg.success:
                self.match_index[sender] = msg.match_index
                self.next_index[sender] = msg.match_index + 1
                self._try_commit()
            else:
                # Decrement next_index and retry
                self.next_index[sender] = max(1, self.next_index.get(sender, 1) - 1)

    # ------------------------------------------------------------------
    # Leader commit logic
    # ------------------------------------------------------------------

    def _try_commit(self) -> None:
        """
        Advance commit_index if a majority of nodes have replicated the entry.

        BUG 3: Commits entries from any term, not just the current term.
        The Raft paper (Section 5.4.2) states: "a leader can only commit log
        entries from its current term by counting replicas."
        Entries from previous terms are committed indirectly when a current-term
        entry is committed (log matching property).
        Missing: check self.log.term_at(n) == self.current_term before committing.
        """
        for n in range(self.commit_index + 1, self.log.last_index() + 1):
            # Only commit entries from the current term directly (Raft §5.4.2)
            if self.log.term_at(n) != self.current_term:
                continue
            # Count replicas (leader counts itself)
            count = 1 + sum(1 for m in self.match_index.values() if m >= n)
            if count >= self._quorum:
                self.commit_index = n
        self._apply_committed()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _become_follower(self, term: int) -> None:
        self.state = NodeState.FOLLOWER
        self.current_term = term
        self.voted_for = None
        self.leader_id = None
        self._reset_election_timeout()

    def _become_candidate(self) -> None:
        self.state = NodeState.CANDIDATE
        self.current_term += 1
        self.voted_for = self.node_id
        self._votes_received = {self.node_id}
        self._reset_election_timeout()

        # Send RequestVote to all peers
        msg = RequestVoteRequest(
            term=self.current_term,
            candidate_id=self.node_id,
            last_log_index=self.log.last_index(),
            last_log_term=self.log.last_term(),
        )
        for peer in self.peers:
            self.network.send(self.node_id, peer, ("request_vote", msg))

    def _become_leader(self) -> None:
        self.state = NodeState.LEADER
        self.leader_id = self.node_id
        # Initialize next_index and match_index
        last_idx = self.log.last_index()
        for peer in self.peers:
            self.next_index[peer] = last_idx + 1
            self.match_index[peer] = 0
        self.match_index[self.node_id] = last_idx
        self._broadcast_append_entries()

    def _broadcast_append_entries(self) -> None:
        """Send AppendEntries to all peers (heartbeat or with entries)."""
        for peer in self.peers:
            ni = self.next_index.get(peer, self.log.last_index() + 1)
            prev_idx = ni - 1
            prev_term = self.log.term_at(prev_idx)
            entries = self.log.entries_from(ni)
            msg = AppendEntriesRequest(
                term=self.current_term,
                leader_id=self.node_id,
                prev_log_index=prev_idx,
                prev_log_term=prev_term,
                entries=entries,
                leader_commit=self.commit_index,
            )
            self.network.send(self.node_id, peer, ("append_entries", msg))

    def _apply_committed(self) -> None:
        """Apply all committed but not-yet-applied log entries."""
        while self.last_applied < self.commit_index:
            self.last_applied += 1
            entry = self.log.entry_at(self.last_applied)
            if entry is not None:
                self.applied.append(entry)

    def _reset_election_timeout(self) -> None:
        self._last_heartbeat = time.monotonic()
        self._election_timeout = self._random_election_timeout()

    def _random_election_timeout(self) -> float:
        return random.uniform(ELECTION_TIMEOUT_MIN, ELECTION_TIMEOUT_MAX)

    def _election_timed_out(self) -> bool:
        return (time.monotonic() - self._last_heartbeat) > self._election_timeout

    # ------------------------------------------------------------------
    # Main event loop
    # ------------------------------------------------------------------

    def _run(self) -> None:
        """Background thread: process messages and trigger elections/heartbeats."""
        while self._running:
            # Process all pending messages (non-blocking)
            try:
                while True:
                    sender, message = self._inbox.get_nowait()
                    self._dispatch(sender, message)
            except queue.Empty:
                pass

            with self._lock:
                if self.state == NodeState.LEADER:
                    # Send heartbeats
                    now = time.monotonic()
                    if now - self._last_heartbeat >= HEARTBEAT_INTERVAL:
                        self._broadcast_append_entries()
                        self._last_heartbeat = now
                elif self._election_timed_out():
                    self._become_candidate()

            time.sleep(0.005)  # 5ms poll interval

    def _dispatch(self, sender: int, message) -> None:
        """Route an incoming message to the appropriate handler."""
        msg_type, msg = message
        if msg_type == "request_vote":
            resp = self.handle_request_vote(msg)
            self.network.send(self.node_id, sender, ("request_vote_response", resp))
        elif msg_type == "append_entries":
            resp = self.handle_append_entries(msg)
            self.network.send(self.node_id, sender, ("append_entries_response", resp))
        elif msg_type == "request_vote_response":
            self.handle_request_vote_response(sender, msg)
        elif msg_type == "append_entries_response":
            self.handle_append_entries_response(sender, msg)
