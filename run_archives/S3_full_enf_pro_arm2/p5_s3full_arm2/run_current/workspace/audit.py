"""Audit logging module for FinanceApp — SOX / PCI-DSS compliant.

Provides tamper-evident audit logging with HMAC-SHA256 signatures over
canonical JSON representations of security-relevant events.

Public API:
    log_event(event_type, **fields) -> dict
    get_log() -> list[dict]
    verify_log(entries: list[dict]) -> list[int]
"""

import datetime
import hashlib
import hmac
import json
import os
import uuid

# ---------------------------------------------------------------------------
# Event-type schemas — required fields per event type
# ---------------------------------------------------------------------------

_REQUIRED_FIELDS: dict[str, set[str]] = {
    "config_changed": {
        "user_id", "config_key", "old_value", "new_value", "user_agent",
    },
    "user_login": {
        "user_id", "ip_address", "success", "correlation_id",
    },
    "report_accessed": {
        "user_id", "report_id", "report_type", "request_id",
    },
    "data_exported": {
        "user_id", "export_format", "record_count",
        "destination", "user_agent",
    },
    "payment_initiated": {
        "user_id", "amount", "currency",
        "recipient_account", "session_id",
    },
}

_VALID_EVENT_TYPES: set[str] = set(_REQUIRED_FIELDS.keys())

# ---------------------------------------------------------------------------
# In-memory log store (append-only, insertion order preserved)
# ---------------------------------------------------------------------------

_log_store: list[dict] = []


# ---------------------------------------------------------------------------
# Internal: HMAC-SHA256 over canonical JSON
# ---------------------------------------------------------------------------

def _compute_signature(entry: dict) -> str:
    """Return the HMAC-SHA256 hex digest for *entry*.

    The entry MUST NOT contain a ``signature`` key — callers are responsible
    for stripping it before invoking this helper.
    """
    canonical: str = json.dumps(
        entry,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    key_bytes: bytes = os.environ.get("AUDIT_HMAC_KEY", "default-key").encode(
        "utf-8"
    )
    return hmac.new(key_bytes, canonical.encode("utf-8"), hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def log_event(event_type: str, **fields) -> dict:
    """Create and store a signed audit-log entry."""
    if event_type not in _VALID_EVENT_TYPES:
        raise ValueError(f"Unknown event_type: {event_type!r}")

    required: set[str] = _REQUIRED_FIELDS[event_type]
    missing: set[str] = required - set(fields.keys())
    if missing:
        raise TypeError(
            f"Missing required fields for {event_type!r}: "
            f"{sorted(missing)}"
        )

    entry: dict = {
        "event_type": event_type,
        "log_id": str(uuid.uuid4()),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    entry.update(fields)

    entry["signature"] = _compute_signature(entry)

    _log_store.append(entry)
    return dict(entry)


def get_log() -> list[dict]:
    """Return a shallow copy of all stored audit entries."""
    return list(_log_store)


def verify_log(entries: list[dict]) -> list[int]:
    """Verify a list of audit entries for tampering.

    Returns zero-based indices of tampered entries.
    """
    tampered: list[int] = []

    for idx, entry in enumerate(entries):
        stored_sig: str | None = entry.get("signature")
        if stored_sig is None:
            tampered.append(idx)
            continue

        entry_no_sig: dict = {
            k: v for k, v in entry.items() if k != "signature"
        }
        recomputed: str = _compute_signature(entry_no_sig)

        if not hmac.compare_digest(recomputed, stored_sig):
            tampered.append(idx)

    return tampered
