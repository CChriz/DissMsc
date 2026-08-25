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

# Valid event types recognised by this system
_VALID_EVENT_TYPES: set[str] = {
    "config_changed",
    "user_login",
    "report_accessed",
    "data_exported",
    "payment_initiated",
}


def _get_hmac_key() -> str:
    """Return the HMAC key from environment or the default."""
    return os.environ.get("AUDIT_HMAC_KEY", "default-key")


def _compute_signature(entry_without_sig: dict) -> str:
    """Compute HMAC-SHA256 signature for an entry dict.

    The canonical JSON is obtained by sorting keys alphabetically.
    The 'signature' field must NOT be present in the dict passed here.
    """
    canonical = json.dumps(entry_without_sig, sort_keys=True, separators=(",", ":"))
    key = _get_hmac_key().encode("utf-8")
    return hmac.new(key, canonical.encode("utf-8"), hashlib.sha256).hexdigest()


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
    if event_type not in _VALID_EVENT_TYPES:
        raise ValueError(
            f"Unrecognized event_type '{event_type}'. "
            f"Valid types: {sorted(_VALID_EVENT_TYPES)}"
        )

    # 1. Build the base entry with event_type + log_id (uuid4) + all **fields
    entry = {
        "event_type": event_type,
        "log_id": str(uuid.uuid4()),
    }
    entry.update(fields)

    # 2. Compute 'signature' using HMAC-SHA256 (exclude signature itself)
    signature = _compute_signature(entry)

    # 3. Attach 'signature' to the entry
    entry["signature"] = signature

    # 4. Append to _AUDIT_LOG
    _AUDIT_LOG.append(entry)

    # 5. Return the entry
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
        # 1. Check signature field is present
        stored_signature = entry.get("signature")
        if stored_signature is None:
            tampered.append(idx)
            continue

        # 2. Recompute expected signature (exclude signature field)
        entry_without_sig = {k: v for k, v in entry.items() if k != "signature"}
        expected_signature = _compute_signature(entry_without_sig)

        # 3. Compare
        if not hmac.compare_digest(stored_signature, expected_signature):
            tampered.append(idx)

    return tampered
