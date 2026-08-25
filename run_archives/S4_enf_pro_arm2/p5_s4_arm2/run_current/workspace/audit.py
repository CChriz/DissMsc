"""
Audit logging module — implements compliant audit logging with HMAC-SHA256
tamper detection per planner1 (event taxonomy) and planner2 (security pipeline).

Required exports:
    log_event(event_type, **fields) -> dict
        Create, store, and return a compliant audit log entry.
        The entry includes ALL required fields for the event type,
        plus the tamper-detection field ('signature').

    get_log() -> list[dict]
        Return all stored audit log entries.

    verify_log(entries) -> list[int]
        Return indices of entries that fail tamper-detection verification.
        Return an empty list if all entries are valid.

Tamper detection method: HMAC-SHA256 Entry Signature
Required tamper-detection field: 'signature'
"""

import hashlib
import hmac
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Event schemas — planner1 field definitions
# ---------------------------------------------------------------------------
# Each event type maps to a dict of {field_name: python_type}.
# Fields listed here are callers' responsibility.
# System fields (event_type, log_id, timestamp, signature) are NOT in these
# schemas — they are generated inside log_event().

VALID_EVENT_TYPES = {
    "config_changed",
    "user_login",
    "report_accessed",
    "data_exported",
    "payment_initiated",
}

EVENT_SCHEMAS: dict[str, dict[str, type]] = {
    "config_changed": {
        "user_id": str,
        "config_key": str,
        "old_value": str,
        "new_value": str,
        "user_agent": str,
    },
    "user_login": {
        "user_id": str,
        "ip_address": str,
        "success": bool,
        "correlation_id": str,
    },
    "report_accessed": {
        "user_id": str,
        "report_id": str,
        "report_type": str,
        "request_id": str,
    },
    "data_exported": {
        "user_id": str,
        "export_format": str,
        "record_count": int,
        "destination": str,
        "user_agent": str,
    },
    "payment_initiated": {
        "user_id": str,
        "amount": float,
        "currency": str,
        "recipient_account": str,
        "session_id": str,
    },
}

# System-reserved fields — callers must NOT pass these.
SYSTEM_FIELDS = {"log_id", "timestamp", "signature"}

# ---------------------------------------------------------------------------
# In-memory audit log store
# ---------------------------------------------------------------------------
_AUDIT_LOG: list[dict] = []
_lock = threading.Lock()

# Rotation tracking
_current_date: Any = None  # datetime.date or None


# ---------------------------------------------------------------------------
# HMAC key management — planner2 §2
# ---------------------------------------------------------------------------

def _get_hmac_key() -> bytes:
    """Return the HMAC key: AUDIT_HMAC_KEY env var or 'default-key' fallback."""
    key = os.environ.get("AUDIT_HMAC_KEY", "default-key")
    return key.encode("utf-8")


# ---------------------------------------------------------------------------
# Canonical JSON — planner2 §1.1
# ---------------------------------------------------------------------------

def _canonical_json(entry: dict) -> str:
    """
    Produce a deterministic JSON string for HMAC signing.

    Rules:
      1. Exclude 'signature' from the payload
      2. Sort keys alphabetically
      3. Compact separators — no whitespace: (',', ':')
      4. ensure_ascii=False so Unicode is preserved; UTF-8 encoding is
         applied in _compute_signature
    """
    payload = {k: v for k, v in entry.items() if k != "signature"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


# ---------------------------------------------------------------------------
# HMAC-SHA256 signing — planner2 §1.2
# ---------------------------------------------------------------------------

def _compute_signature(entry: dict, key: bytes) -> str:
    """Compute HMAC-SHA256 hex digest for *entry*."""
    canonical = _canonical_json(entry)
    digest = hmac.new(key, canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest


# ---------------------------------------------------------------------------
# Log rotation helpers — planner2 §4
# ---------------------------------------------------------------------------

def _rotate_if_needed() -> None:
    """Check whether the UTC date has changed; if so, rotate the log file."""
    global _current_date
    today = datetime.now(timezone.utc).date()
    if _current_date is None:
        _current_date = today
        return
    if today != _current_date:
        _do_rotate(_current_date)
        _current_date = today


def _do_rotate(old_date: Any) -> None:
    """Atomically rename audit_today.jsonl → audit_YYYY-MM-DD.jsonl."""
    old_name = "audit_today.jsonl"
    new_name = f"audit_{old_date.isoformat()}.jsonl"
    if os.path.exists(old_name):
        os.rename(old_name, new_name)  # atomic on the same filesystem


# ---------------------------------------------------------------------------
# Field validation helpers — planner1 §4
# ---------------------------------------------------------------------------

def _validate_field_type(
    field_name: str, value: Any, expected_type: type, event_type: str
) -> None:
    """Raise TypeError if *value* does not match *expected_type*."""
    # bool is a subclass of int — must check explicitly
    if expected_type is bool:
        if not isinstance(value, bool):
            raise TypeError(
                f"Event '{event_type}': field '{field_name}' "
                f"must be bool, got {type(value).__name__}"
            )
        return

    if expected_type is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(
                f"Event '{event_type}': field '{field_name}' "
                f"must be int, got {type(value).__name__}"
            )
        return

    if expected_type is float:
        # Allow int for float fields (e.g. amount=100 is acceptable)
        if isinstance(value, bool) or not isinstance(value, (float, int)):
            raise TypeError(
                f"Event '{event_type}': field '{field_name}' "
                f"must be float, got {type(value).__name__}"
            )
        return

    if not isinstance(value, expected_type):
        raise TypeError(
            f"Event '{event_type}': field '{field_name}' "
            f"must be {expected_type.__name__}, got {type(value).__name__}"
        )


def _validate_value_range(
    field_name: str, value: Any, event_type: str
) -> None:
    """Raise ValueError if *value* violates domain constraints."""
    if field_name == "amount" and float(value) <= 0.0:
        raise ValueError(
            f"Event '{event_type}': field 'amount' must be > 0.0, got {value}"
        )
    if field_name == "record_count" and int(value) < 0:
        raise ValueError(
            f"Event '{event_type}': field 'record_count' must be >= 0, got {value}"
        )
    if field_name == "currency":
        s = str(value)
        if len(s) != 3 or s != s.upper():
            raise ValueError(
                f"Event '{event_type}': field 'currency' must be 3-char uppercase "
                f"ISO 4217 code, got '{value}'"
            )


def _validate_non_empty(
    field_name: str, value: str, event_type: str
) -> None:
    """Raise ValueError if *value* is an empty string."""
    if isinstance(value, str) and len(value) == 0:
        raise ValueError(
            f"Event '{event_type}': field '{field_name}' must not be empty"
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def log_event(event_type: str, **fields: Any) -> dict:
    """
    Create a compliant audit log entry for the given event_type.

    1. Validate *event_type* against VALID_EVENT_TYPES
    2. Reject system-reserved fields passed by caller (log_id, timestamp, signature)
    3. Validate all required fields are present and of correct type
    4. Generate system fields: log_id (uuid4), timestamp (ISO 8601 UTC)
    5. Compute and attach HMAC-SHA256 signature
    6. Append entry to in-memory log and persist to audit_today.jsonl
    7. Return the completed entry

    Raises ValueError if event_type invalid, required field missing,
        or caller passes a system-reserved field.
    Raises TypeError if a field has the wrong Python type.
    """
    # ---- 1. Validate event_type ----
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(
            f"Invalid event_type: '{event_type}'. "
            f"Must be one of: {', '.join(sorted(VALID_EVENT_TYPES))}"
        )

    # ---- 2. Reject system-reserved fields ----
    for sys_field in SYSTEM_FIELDS:
        if sys_field in fields:
            raise ValueError(
                f"Field '{sys_field}' is system-generated and must not be provided"
            )

    # Allow caller to pass event_type (consistency check only)
    if "event_type" in fields and fields["event_type"] != event_type:
        raise ValueError(
            f"event_type mismatch: call argument is '{event_type}' "
            f"but fields contains '{fields['event_type']}'"
        )

    # ---- 3. Validate required fields ----
    schema = EVENT_SCHEMAS[event_type]
    for field_name, expected_type in schema.items():
        if field_name not in fields:
            raise ValueError(
                f"Event '{event_type}': missing required field '{field_name}'"
            )

        value = fields[field_name]

        # Type check
        _validate_field_type(field_name, value, expected_type, event_type)

        # Value-range constraints
        if field_name in ("amount", "record_count", "currency"):
            _validate_value_range(field_name, value, event_type)

        # Non-empty check for string fields (except old_value which may be empty)
        if expected_type is str and field_name != "old_value":
            _validate_non_empty(field_name, value, event_type)

    # ---- 4. Build the entry ----
    entry: dict[str, Any] = {"event_type": event_type}
    entry["log_id"] = str(uuid.uuid4())
    entry["timestamp"] = datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    # Merge caller fields
    entry.update(fields)

    # ---- 5. Compute signature ----
    key = _get_hmac_key()
    entry["signature"] = _compute_signature(entry, key)

    # ---- 6. Persist (thread-safe, with rotation) ----
    with _lock:
        _rotate_if_needed()
        _AUDIT_LOG.append(entry)
        _write_to_file(entry)

    return entry


def _write_to_file(entry: dict) -> None:
    """Write a single entry as JSONL to audit_today.jsonl with fsync."""
    try:
        with open("audit_today.jsonl", "a", encoding="utf-8") as f:
            line = json.dumps(entry, sort_keys=True, ensure_ascii=False)
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())
    except OSError:
        # Logging failure must not crash the application — planner2 §5.4
        import sys
        print(
            f"[audit] ERROR: failed to write audit entry {entry.get('log_id', '?')}",
            file=sys.stderr,
        )


def get_log() -> list[dict]:
    """Return all stored audit log entries (shallow copy)."""
    with _lock:
        return list(_AUDIT_LOG)


def verify_log(entries: list[dict]) -> list[int]:
    """
    Verify tamper-detection on every entry.

    For each entry:
    - If 'signature' is missing → mark as tampered
    - Recompute expected signature via _compute_signature
    - Compare with hmac.compare_digest (timing-safe)

    Returns a list of 0-based indices of entries that fail verification.
    Returns an empty list if all entries are valid.
    """
    key = _get_hmac_key()
    tampered: list[int] = []

    for i, entry in enumerate(entries):
        if "signature" not in entry:
            tampered.append(i)
            continue

        stored_sig = entry["signature"]

        # SEC-001: signature must be str — non-string types (None, int, dict, etc.)
        # would cause hmac.compare_digest to throw TypeError.  Mark as tampered.
        if not isinstance(stored_sig, str):
            tampered.append(i)
            continue

        expected_sig = _compute_signature(entry, key)

        if not hmac.compare_digest(expected_sig, stored_sig):
            tampered.append(i)

    return tampered
