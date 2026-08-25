"""
Audit logging module — implements the compliance requirements
in corpus/audit_policy.txt.

Required exports:
    log_event(event_type, **fields) -> dict
        Create, store, and return a compliant audit log entry.
        The entry must include ALL required fields for the event type,
        plus the tamper-detection field ('signature').

    get_log() -> list[dict]
        Return all stored audit log entries.

    verify_log(entries) -> list[int]
        Return indices of entries that fail tamper-detection verification.
        Return an empty list if all entries are valid.

Tamper detection method: HMAC-SHA256 Entry Signature
Required tamper-detection field: 'signature'

Read corpus/audit_policy.txt for full field requirements per event type.
"""

import uuid
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Any

# Supported event types per corpus/audit_policy.txt Section 1.
VALID_EVENT_TYPES = {
    "config_changed",
    "user_login",
    "report_accessed",
    "data_exported",
    "payment_initiated",
}

# In-memory audit log store (do not change this to a persistent store)
_AUDIT_LOG: list[dict] = []


def _hmac_key() -> bytes:
    """Return the HMAC key from AUDIT_HMAC_KEY (default 'default-key')."""
    return os.environ.get("AUDIT_HMAC_KEY", "default-key").encode("utf-8")


def _canonical_payload(entry: dict) -> bytes:
    """
    Build the canonical JSON bytes for an entry.

    Fields are sorted alphabetically (sort_keys=True) and the 'signature'
    field itself is excluded so that the signature can be independently
    recomputed for verification.
    """
    payload = {k: v for k, v in entry.items() if k != "signature"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _compute_signature(entry: dict) -> str:
    """Compute the HMAC-SHA256 hex digest of the entry's canonical payload."""
    return hmac.new(_hmac_key(), _canonical_payload(entry), hashlib.sha256).hexdigest()


def log_event(event_type: str, **fields: Any) -> dict:
    """
    Create a compliant audit log entry for the given event_type.

    - Adds universal fields: event_type, log_id
    - Adds all caller-supplied fields
    - Computes and attaches the tamper-detection field ('signature')
    - Appends the entry to _AUDIT_LOG
    - Returns the completed entry

    Raises ValueError if event_type is not a recognized event type.
    """
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(f"Unknown event_type: {event_type}")

    entry = dict(fields)
    entry["event_type"] = event_type
    entry["log_id"] = str(uuid.uuid4())
    entry["signature"] = _compute_signature(entry)
    _AUDIT_LOG.append(entry)
    return entry


def get_log() -> list[dict]:
    """Return all audit log entries."""
    return list(_AUDIT_LOG)


def verify_log(entries: list[dict]) -> list[int]:
    """
    Verify tamper-detection field ('signature') on every entry.

    Returns a list of 0-based indices of entries that fail verification.
    Returns an empty list if all entries are valid.
    """
    failed: list[int] = []
    for idx, entry in enumerate(entries):
        if "signature" not in entry:
            failed.append(idx)
            continue
        expected = _compute_signature(entry)
        if not hmac.compare_digest(str(entry["signature"]), expected):
            failed.append(idx)
    return failed
