"""
Raft RPC message types.

These are pure data containers — no logic here.
Do not modify this file.
"""
from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class LogEntry:
    """A single entry in the replicated log."""
    term: int
    index: int
    command: Any


@dataclass
class RequestVoteRequest:
    """Sent by a candidate to gather votes."""
    term: int
    candidate_id: int
    last_log_index: int
    last_log_term: int


@dataclass
class RequestVoteResponse:
    """Response to a RequestVote RPC."""
    term: int
    vote_granted: bool


@dataclass
class AppendEntriesRequest:
    """Sent by leader to replicate log entries (also serves as heartbeat)."""
    term: int
    leader_id: int
    prev_log_index: int
    prev_log_term: int
    entries: List[LogEntry] = field(default_factory=list)
    leader_commit: int = 0


@dataclass
class AppendEntriesResponse:
    """Response to an AppendEntries RPC."""
    term: int
    success: bool
    match_index: int = 0  # Highest log index known to be replicated on this follower
