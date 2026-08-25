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


# Recognized event types from audit_policy.txt Section 1
_SUPPORTED_EVENT_TYPES = {
    "config_changed",
    "user_login",
    "report_accessed",
    "data_exported",
    "payment_initiated",
}


def _compute_signature(entry: dict) -> str:
    """Compute HMAC-SHA256 signature for an audit entry.

    The canonical JSON is built from all fields EXCEPT 'signature',
    sorted alphabetically, with compact separators (no spaces).
    """
    key = os.environ.get("AUDIT_HMAC_KEY", "default-key")
    fields = {k: v for k, v in entry.items() if k != "signature"}
    canonical = json.dumps(fields, sort_keys=True, separators=(",", ":"))
    return hmac.new(key.encode(), canonical.encode(), hashlib.sha256).hexdigest()


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
    if event_type not in _SUPPORTED_EVENT_TYPES:
        raise ValueError(
            f"Unsupported event type: {event_type!r}. "
            f"Must be one of: {sorted(_SUPPORTED_EVENT_TYPES)}"
        )

    # Build the base entry with event_type + log_id + all **fields
    entry: dict[str, Any] = {"event_type": event_type, "log_id": str(uuid.uuid4())}
    entry.update(fields)

    # Compute and attach the tamper-detection field
    entry["signature"] = _compute_signature(entry)

    # Append to in-memory store
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
    for i, entry in enumerate(entries):
        if "signature" not in entry:
            tampered.append(i)
            continue
        stored_sig = entry["signature"]
        expected_sig = _compute_signature(entry)
        if not hmac.compare_digest(stored_sig, expected_sig):
            tampered.append(i)
    return tampered
