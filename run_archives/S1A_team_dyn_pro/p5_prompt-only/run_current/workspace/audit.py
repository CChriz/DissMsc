"""
Audit logging module — compliant with corpus/audit_policy.txt.

Implements HMAC-SHA256 entry-level tamper detection for 5 event types:
    config_changed, user_login, report_accessed, data_exported, payment_initiated

Exports:
    log_event(event_type, **fields) -> dict
        Create, store, and return a compliant audit log entry.
    get_log() -> list[dict]
        Return all stored audit log entries.
    verify_log(entries) -> list[int]
        Return indices of entries that fail tamper-detection verification.
"""

import uuid
import hashlib
import hmac
import json
import os
from typing import Any

# ── Supported event types ──────────────────────────────────────────────────────

VALID_EVENT_TYPES = {
    "config_changed",
    "user_login",
    "report_accessed",
    "data_exported",
    "payment_initiated",
}

# ── Required fields per event type (universal + event-specific) ─────────────────

REQUIRED_FIELDS: dict[str, list[str]] = {
    "config_changed": [
        "event_type", "log_id", "user_id", "timestamp",
        "config_key", "old_value", "new_value", "user_agent",
    ],
    "user_login": [
        "event_type", "log_id", "user_id", "timestamp",
        "ip_address", "success", "correlation_id",
    ],
    "report_accessed": [
        "event_type", "log_id", "user_id", "timestamp",
        "report_id", "report_type", "request_id",
    ],
    "data_exported": [
        "event_type", "log_id", "user_id", "timestamp",
        "export_format", "record_count", "destination", "user_agent",
    ],
    "payment_initiated": [
        "event_type", "log_id", "user_id", "timestamp",
        "amount", "currency", "recipient_account", "session_id",
    ],
}

# ── In-memory audit log store ──────────────────────────────────────────────────

_AUDIT_LOG: list[dict] = []

# ── Internal helper ────────────────────────────────────────────────────────────


def _compute_signature(entry: dict) -> str:
    """
    Compute HMAC-SHA256 signature over the canonical JSON of *entry*.

    Canonical JSON rules:
      - Exclude the 'signature' field itself.
      - Sort keys alphabetically (sort_keys=True).
      - Compact output: no whitespace (separators=(",", ":")).
      - HMAC key from env AUDIT_HMAC_KEY, default 'default-key'.
    """
    payload = {k: v for k, v in entry.items() if k != "signature"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    key = os.environ.get("AUDIT_HMAC_KEY", "default-key").encode("utf-8")
    return hmac.new(key, canonical.encode("utf-8"), hashlib.sha256).hexdigest()


# ── Public API ─────────────────────────────────────────────────────────────────


def log_event(event_type: str, **fields: Any) -> dict:
    """
    Create a compliant audit log entry for *event_type*.

    1. Validate *event_type* is recognised.
    2. Build entry with universal fields (event_type, log_id) + caller fields.
    3. Validate all required fields are present.
    4. Compute and attach HMAC-SHA256 'signature'.
    5. Append to _AUDIT_LOG and return the entry.

    Raises ValueError if event_type is unknown or a required field is missing.
    """
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(f"Unknown event_type: {event_type!r}")

    entry: dict[str, Any] = {
        "event_type": event_type,
        "log_id": str(uuid.uuid4()),
    }
    entry.update(fields)

    # Check all required fields are present
    for field in REQUIRED_FIELDS[event_type]:
        if field not in entry:
            raise ValueError(
                f"Missing required field {field!r} for event_type {event_type!r}"
            )

    # Compute signature *after* the entry is fully built
    entry["signature"] = _compute_signature(entry)

    _AUDIT_LOG.append(entry)
    return entry


def get_log() -> list[dict]:
    """Return a copy of all stored audit log entries."""
    return list(_AUDIT_LOG)


def verify_log(entries: list[dict]) -> list[int]:
    """
    Verify the 'signature' tamper-detection field on every entry.

    Returns a list of 0-based indices of entries that fail verification
    (missing signature or mismatched signature).  Returns an empty list if
    all entries are valid.
    """
    tampered: list[int] = []
    for i, entry in enumerate(entries):
        if "signature" not in entry:
            tampered.append(i)
            continue
        original = entry["signature"]
        expected = _compute_signature(entry)
        if not hmac.compare_digest(expected, original):
            tampered.append(i)
    return tampered
