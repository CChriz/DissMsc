"""
Audit logging module — implement this file to satisfy the compliance requirements
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

# Supported event types: "config_changed", "user_login", "report_accessed", "data_exported", "payment_initiated"
# See corpus/audit_policy.txt Section 1 for required fields per event type.

# In-memory audit log store (do not change this to a persistent store)
_AUDIT_LOG: list[dict] = []

# HMAC key from environment; falls back to 'default-key' for dev/test
_AUDIT_HMAC_KEY = os.environ.get("AUDIT_HMAC_KEY", "default-key")

# Required caller-supplied fields per event type.
# event_type and log_id are auto-generated; signature is auto-computed.
_EVENT_REQUIRED_FIELDS: dict[str, list[str]] = {
    "config_changed": [
        "user_id", "timestamp", "config_key", "old_value", "new_value", "user_agent",
    ],
    "user_login": [
        "user_id", "timestamp", "ip_address", "success", "correlation_id",
    ],
    "report_accessed": [
        "user_id", "timestamp", "report_id", "report_type", "request_id",
    ],
    "data_exported": [
        "user_id", "timestamp", "export_format", "record_count", "destination", "user_agent",
    ],
    "payment_initiated": [
        "user_id", "timestamp", "amount", "currency", "recipient_account", "session_id",
    ],
}


def _compute_signature(entry: dict) -> str:
    """
    Compute an HMAC-SHA256 signature over the canonical JSON of *entry*.

    The canonical form sorts keys alphabetically, uses compact separators
    (no spaces), and omits the ``signature`` field itself so that the
    signature can be recomputed and verified independently.
    """
    # Build a cleaned dict that excludes the signature field
    cleaned = {k: v for k, v in entry.items() if k != "signature"}

    # Canonical JSON: sorted keys, compact separators, preserve Unicode
    canonical = json.dumps(
        cleaned,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    key_bytes = _AUDIT_HMAC_KEY.encode("utf-8")
    msg_bytes = canonical.encode("utf-8")
    return hmac.new(key_bytes, msg_bytes, hashlib.sha256).hexdigest()


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
    if event_type not in _EVENT_REQUIRED_FIELDS:
        raise ValueError(f"Unknown event_type: {event_type!r}")

    # Build the base entry with universal auto-generated fields
    entry: dict = {
        "event_type": event_type,
        "log_id": str(uuid.uuid4()),
    }

    # Merge caller-supplied fields (may override universal fields except
    # event_type and log_id which are deliberately set after merging).
    entry.update(fields)

    # Validate that every required field for this event type is present
    for field in _EVENT_REQUIRED_FIELDS[event_type]:
        if field not in entry:
            raise ValueError(
                f"Missing required field {field!r} for event_type {event_type!r}"
            )

    # Compute and attach the tamper-detection signature
    entry["signature"] = _compute_signature(entry)

    # Persist to the in-memory log
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
    tampered: list[int] = []
    for idx, entry in enumerate(entries):
        stored_sig = entry.get("signature")
        computed_sig = _compute_signature(entry)
        if stored_sig != computed_sig:
            tampered.append(idx)
    return tampered
