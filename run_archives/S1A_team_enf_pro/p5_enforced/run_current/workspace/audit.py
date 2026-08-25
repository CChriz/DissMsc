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
import glob as _glob
from datetime import datetime, timezone
from typing import Any

# Supported event types: "config_changed", "user_login", "report_accessed", "data_exported", "payment_initiated"
# See corpus/audit_policy.txt Section 1 for required fields per event type.

# In-memory audit log store (do not change this to a persistent store)
_AUDIT_LOG: list[dict] = []

# Event type → required fields (event-type-specific only; event_type, log_id, and signature
# are handled automatically)
EVENT_SCHEMA: dict[str, list[str]] = {
    "config_changed":   ["user_id", "timestamp", "config_key", "old_value", "new_value", "user_agent"],
    "user_login":       ["user_id", "timestamp", "ip_address", "success", "correlation_id"],
    "report_accessed":  ["user_id", "timestamp", "report_id", "report_type", "request_id"],
    "data_exported":    ["user_id", "timestamp", "export_format", "record_count", "destination", "user_agent"],
    "payment_initiated":["user_id", "timestamp", "amount", "currency", "recipient_account", "session_id"],
}

# Workspace path for log file I/O (rotation / retention)
_WORKSPACE = os.path.dirname(os.path.abspath(__file__))


def _compute_signature(entry: dict) -> str:
    """
    Compute HMAC-SHA256 signature for an audit log entry.

    The signature is computed over the canonical JSON of the entry
    (keys sorted alphabetically, no whitespace), excluding the
    'signature' field itself.

    HMAC key is read from AUDIT_HMAC_KEY env var; defaults to 'default-key'.
    """
    data = {k: v for k, v in entry.items() if k != "signature"}
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    key = os.environ.get("AUDIT_HMAC_KEY", "default-key")
    return hmac.new(key.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def _rotate_log() -> None:
    """
    Daily log rotation: if audit_today.jsonl contains entries from a previous
    day, rename it to audit_YYYY-MM-DD.jsonl and start a fresh file.
    """
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_path = os.path.join(_WORKSPACE, "audit_today.jsonl")

    if not os.path.isfile(today_path):
        return

    try:
        with open(today_path, "r") as fh:
            first_line = fh.readline().strip()
        if first_line:
            entry = json.loads(first_line)
            ts = entry.get("timestamp", "")
            entry_date = ts[:10] if ts else ""
        else:
            entry_date = ""
    except Exception:
        entry_date = ""

    if entry_date and entry_date != today_str:
        archive_path = os.path.join(_WORKSPACE, f"audit_{entry_date}.jsonl")
        try:
            os.rename(today_path, archive_path)
        except OSError:
            pass


def cleanup_old_logs(retention_days: int = 2555) -> None:
    """
    Remove audit log files older than retention_days (default 2555 ≈ 7 years).

    Scans workspace for audit_YYYY-MM-DD.jsonl files and deletes those
    whose date is before (today - retention_days).
    """
    import time as _time
    cutoff_ts = _time.time() - retention_days * 86400

    pattern = os.path.join(_WORKSPACE, "audit_????-??-??.jsonl")
    for filepath in _glob.glob(pattern):
        try:
            mtime = os.path.getmtime(filepath)
            if mtime < cutoff_ts:
                os.remove(filepath)
        except OSError:
            pass


def log_event(event_type: str, **fields: Any) -> dict:
    """
    Create a compliant audit log entry for the given event_type.

    - Adds universal fields: event_type, log_id
    - Adds all caller-supplied fields
    - Computes and attaches the tamper-detection field ('signature')
    - Appends the entry to _AUDIT_LOG
    - Returns the completed entry

    Raises ValueError if event_type is not a recognized event type,
    or if required fields are missing.
    """
    # 1. Validate event_type
    if event_type not in EVENT_SCHEMA:
        raise ValueError(f"Unknown event_type: {event_type}")

    # 2. Validate required fields
    required = EVENT_SCHEMA[event_type]
    missing = [f for f in required if f not in fields]
    if missing:
        raise ValueError(
            f"Missing required fields for event_type '{event_type}': {', '.join(missing)}"
        )

    # 3. Build the entry
    # Use caller-supplied log_id if provided, else generate UUID4
    log_id = fields.pop("log_id", None)
    if log_id is None:
        log_id = str(uuid.uuid4())

    # Auto-generate timestamp if not provided by caller
    timestamp = fields.get("timestamp")
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()

    entry: dict = {
        "event_type": event_type,
        "log_id": log_id,
    }
    # Merge all caller-supplied fields (ensure timestamp is the resolved one)
    entry.update(fields)
    entry["timestamp"] = timestamp

    # 4. Compute and attach signature
    signature = _compute_signature(entry)
    entry["signature"] = signature

    # 5. Persist: in-memory store
    _AUDIT_LOG.append(entry)

    # 6. Persist: JSONL file (best-effort; do not crash on I/O errors)
    try:
        _rotate_log()
        today_path = os.path.join(_WORKSPACE, "audit_today.jsonl")
        with open(today_path, "a") as fh:
            fh.write(json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n")
    except Exception:
        pass

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
        if stored_sig is None:
            # Missing signature → tampered
            tampered.append(idx)
            continue
        expected_sig = _compute_signature(entry)
        if not hmac.compare_digest(stored_sig, expected_sig):
            tampered.append(idx)
    return tampered
