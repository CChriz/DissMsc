"""
Audit logging module — compliant audit log entry creation, tamper detection,
and file rotation for FinanceApp under SOX / PCI-DSS requirements.

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

import glob
import hashlib
import hmac
import json
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

HMAC_KEY: str = os.environ.get("AUDIT_HMAC_KEY", "default-key")
LOG_DIR: str = os.path.dirname(os.path.abspath(__file__))
TODAY_FILE: str = os.path.join(LOG_DIR, "audit_today.jsonl")
RETENTION_DAYS: int = 2555  # 7 years

# ---------------------------------------------------------------------------
# Event type → required caller-supplied fields
# (event_type, log_id, timestamp, signature are auto-generated)
# ---------------------------------------------------------------------------

REQUIRED_FIELDS: dict[str, list[str]] = {
    "config_changed":    ["user_id", "config_key", "old_value", "new_value", "user_agent"],
    "user_login":        ["user_id", "ip_address", "success", "correlation_id"],
    "report_accessed":   ["user_id", "report_id", "report_type", "request_id"],
    "data_exported":     ["user_id", "export_format", "record_count", "destination", "user_agent"],
    "payment_initiated": ["user_id", "amount", "currency", "recipient_account", "session_id"],
}

# ---------------------------------------------------------------------------
# In-memory audit log store and thread-safety
# ---------------------------------------------------------------------------

_AUDIT_LOG: list[dict] = []
_log_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Canonical JSON + HMAC-SHA256 signature
# ---------------------------------------------------------------------------

def _compute_signature(entry: dict) -> str:
    """
    Compute HMAC-SHA256 signature over the canonical JSON of *entry*.

    Canonicalisation rules (order matters):
      1. Exclude the ``signature`` field itself.
      2. ``json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False)``
         → fields sorted alphabetically, no extra whitespace, Unicode preserved.

    Returns the hex digest.
    """
    data = {k: v for k, v in entry.items() if k != "signature"}
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    sig = hmac.new(
        HMAC_KEY.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return sig


# ---------------------------------------------------------------------------
# File persistence helpers
# ---------------------------------------------------------------------------

def _append_to_file(entry: dict) -> None:
    """
    Append a single audit entry as a JSON line to the current day's active
    log file (audit_today.jsonl).  Calls ``os.fsync()`` to force the write
    to disk so that an OS crash does not lose the last entry.
    """
    line = json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    try:
        with open(TODAY_FILE, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
    except OSError:
        # Never let a disk error crash the application — the entry is still
        # held in-memory and returned to the caller.
        pass


def _rotate_if_needed() -> None:
    """
    Detect a date change and rotate ``audit_today.jsonl`` →
    ``audit_YYYY-MM-DD.jsonl`` when required.
    """
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dated_file = os.path.join(LOG_DIR, f"audit_{today_str}.jsonl")

    if not os.path.exists(TODAY_FILE):
        return  # nothing to rotate

    try:
        mtime = datetime.fromtimestamp(os.path.getmtime(TODAY_FILE), tz=timezone.utc)
        if mtime.strftime("%Y-%m-%d") != today_str:
            os.rename(TODAY_FILE, dated_file)
    except OSError:
        pass  # best-effort rotation


def _cleanup_expired() -> None:
    """
    Remove audit log files older than RETENTION_DAYS (2555 days ≈ 7 years).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    pattern = os.path.join(LOG_DIR, "audit_20*.jsonl")
    for filepath in glob.glob(pattern):
        try:
            basename = os.path.basename(filepath)
            # Expected: audit_YYYY-MM-DD.jsonl
            date_str = basename.replace("audit_", "").replace(".jsonl", "")
            file_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if file_date < cutoff:
                os.remove(filepath)
        except (ValueError, OSError):
            pass  # skip malformed filenames or permission errors


def _init_rotation() -> None:
    """Run rotation + cleanup once at import time."""
    _rotate_if_needed()
    _cleanup_expired()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def log_event(event_type: str, **fields: Any) -> dict:
    """
    Create a compliant audit log entry.

    1. Validate *event_type* is recognised.
    2. Validate all required caller-supplied fields are present.
    3. Build the entry with auto-generated ``event_type``, ``log_id`` (UUID4),
       ``timestamp`` (ISO 8601 UTC), and all caller fields.
    4. Compute the HMAC-SHA256 ``signature`` over the canonical JSON.
    5. Append to the in-memory store (thread-safe) and disk (best-effort).
    6. Return the completed entry dict.

    Raises ``ValueError`` for unknown event types or missing required fields.
    """
    # --- validation ---
    if event_type not in REQUIRED_FIELDS:
        raise ValueError(f"Unknown event_type: {event_type}")

    required = REQUIRED_FIELDS[event_type]
    missing = [f for f in required if f not in fields]
    if missing:
        raise ValueError(
            f"Missing required fields for {event_type}: {missing}"
        )

    # --- build entry (without signature first) ---
    entry: dict[str, Any] = {
        "event_type": event_type,
        "log_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    entry.update(fields)

    # NOTE: For config_changed, old_value / new_value may contain sensitive
    # data (e.g. keys).  V1 does NOT redact — the signature covers all fields
    # and any future redaction would break existing signatures.

    # --- sign ---
    entry["signature"] = _compute_signature(entry)

    # --- store ---
    with _log_lock:
        _AUDIT_LOG.append(entry)
        _append_to_file(entry)

    return entry


def get_log() -> list[dict]:
    """Return a shallow copy of all in-memory audit log entries."""
    return list(_AUDIT_LOG)


def verify_log(entries: list[dict]) -> list[int]:
    """
    Verify the ``signature`` field on every entry.

    Returns a list of 0-based indices whose signature is missing *or* does
    not match the recomputed HMAC-SHA256 value.

    Uses ``hmac.compare_digest`` to avoid timing side-channel leaks.
    """
    tampered: list[int] = []
    for i, entry in enumerate(entries):
        stored_sig = entry.get("signature")
        if stored_sig is None:
            tampered.append(i)
            continue
        expected = _compute_signature(entry)
        if not hmac.compare_digest(expected, stored_sig):
            tampered.append(i)
    return tampered


# ---------------------------------------------------------------------------
# Module-level initialisation
# ---------------------------------------------------------------------------

_init_rotation()
