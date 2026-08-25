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

# ── Constants ─────────────────────────────────────────────────────────────────

# Supported event types
_SUPPORTED_EVENT_TYPES: set[str] = {
    "config_changed",
    "user_login",
    "report_accessed",
    "data_exported",
    "payment_initiated",
}

# Required fields per event type (excluding autogen: event_type, log_id)
_REQUIRED_FIELDS: dict[str, set[str]] = {
    "config_changed":   {"user_id", "timestamp", "config_key", "old_value", "new_value", "user_agent"},
    "user_login":       {"user_id", "timestamp", "ip_address", "success", "correlation_id"},
    "report_accessed":  {"user_id", "timestamp", "report_id", "report_type", "request_id"},
    "data_exported":    {"user_id", "timestamp", "export_format", "record_count", "destination", "user_agent"},
    "payment_initiated":{"user_id", "timestamp", "amount", "currency", "recipient_account", "session_id"},
}

# HMAC key — sourced from environment variable, default 'default-key'
_AUDIT_HMAC_KEY: str = os.environ.get("AUDIT_HMAC_KEY", "default-key")

# In-memory audit log store (do not change this to a persistent store)
_AUDIT_LOG: list[dict] = []


# ── Helper: canonical JSON serialisation ──────────────────────────────────────

def _canonical_json(data: dict) -> str:
    """Return a deterministic JSON string: keys sorted, compact format."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


# ── Helper: compute HMAC-SHA256 signature ─────────────────────────────────────

def _compute_signature(entry: dict) -> str:
    """Compute HMAC-SHA256 signature over all fields except 'signature'."""
    # Build a dict excluding the 'signature' field
    data = {k: v for k, v in entry.items() if k != "signature"}
    canonical = _canonical_json(data)
    digest = hmac.new(
        _AUDIT_HMAC_KEY.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest


# ── Helper: compute SHA-256 checksum ──────────────────────────────────────────

def _compute_checksum(entry: dict) -> str:
    """Compute SHA-256 hex digest over the entry (excluding 'signature' and 'checksum')."""
    data = {k: v for k, v in entry.items() if k not in ("signature", "checksum")}
    canonical = _canonical_json(data)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ── Helper: compute prev_hash ─────────────────────────────────────────────────

def _compute_prev_hash() -> str:
    """Return SHA-256 hex digest of the previous log entry, or '' if first."""
    if not _AUDIT_LOG:
        return ""
    prev_entry = _AUDIT_LOG[-1]
    data = {k: v for k, v in prev_entry.items() if k not in ("signature", "prev_hash")}
    canonical = _canonical_json(data)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ── Public API ────────────────────────────────────────────────────────────────

def log_event(event_type: str, **fields: Any) -> dict:
    """
    Create a compliant audit log entry for the given event_type.

    - Validates event_type against supported types
    - Validates all required fields are present
    - Auto-fills timestamp if missing
    - Generates log_id (UUID4), prev_hash, checksum, and HMAC-SHA256 signature
    - Appends the entry to _AUDIT_LOG
    - Returns the completed entry

    Raises ValueError if event_type is not a recognized event type,
    or if required fields are missing.
    """
    # 1. Validate event_type
    if event_type not in _SUPPORTED_EVENT_TYPES:
        raise ValueError(
            f"Unknown event type: '{event_type}'. "
            f"Supported types: {sorted(_SUPPORTED_EVENT_TYPES)}"
        )

    # 2. Validate required fields
    required = _REQUIRED_FIELDS[event_type]
    provided = set(fields.keys())
    missing = required - provided
    if missing:
        raise ValueError(
            f"Missing required fields for '{event_type}': {sorted(missing)}"
        )

    # 3. Auto-fill timestamp if not provided
    if "timestamp" not in fields or fields["timestamp"] is None:
        fields["timestamp"] = datetime.now(timezone.utc).isoformat()

    # 4. Build base entry: universal fields + caller-supplied fields
    entry: dict[str, Any] = {
        "event_type": event_type,
        "log_id": str(uuid.uuid4()),
    }
    entry.update(fields)

    # 5. Compute prev_hash (chain of custody)
    entry["prev_hash"] = _compute_prev_hash()

    # 6. Compute checksum
    entry["checksum"] = _compute_checksum(entry)

    # 7. Compute signature (excludes 'signature', includes prev_hash + checksum)
    entry["signature"] = _compute_signature(entry)

    # 8. Store in memory
    _AUDIT_LOG.append(entry)

    # 9. Return the completed entry
    return entry


def get_log() -> list[dict]:
    """Return all audit log entries."""
    return list(_AUDIT_LOG)


def verify_log(entries: list[dict]) -> list[int]:
    """
    Verify tamper-detection field ('signature') on every entry.

    Returns a list of 0-based indices of entries that fail verification.
    An entry is considered invalid if:
      - 'signature' field is missing
      - 'signature' value does not match the recomputed HMAC-SHA256

    Uses hmac.compare_digest() for constant-time comparison.
    Returns an empty list if all entries are valid.
    """
    tampered_indices: list[int] = []

    for i, entry in enumerate(entries):
        # Missing signature → tampered
        if "signature" not in entry:
            tampered_indices.append(i)
            continue

        current_sig = entry.get("signature")

        # Recompute expected signature
        expected_sig = _compute_signature(entry)

        # Constant-time comparison (safe against timing attacks)
        if not hmac.compare_digest(expected_sig, current_sig or ""):
            tampered_indices.append(i)

    return tampered_indices
