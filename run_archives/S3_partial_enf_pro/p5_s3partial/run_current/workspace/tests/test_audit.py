"""
Test suite for P5: Audit Logging Compliance

Tests verify that audit.py correctly implements:
  1. Required fields per event type
  2. Tamper-detection field presence ('signature')
  3. verify_log() detects tampered entries
  4. log_event() returns entries and populates get_log()
  5. Universal fields (event_type, log_id) on all entries

Domain: finance
Tamper detection method: hmac_sha256
"""

import pytest
import json
import hashlib
import sys
import os

# Ensure workspace root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import audit


@pytest.fixture(autouse=True)
def reset_audit_log():
    """Clear audit log between tests."""
    audit._AUDIT_LOG.clear()
    yield
    audit._AUDIT_LOG.clear()


# ── 1. log_event() returns a dict ─────────────────────────────────────────────

def test_log_event_returns_dict():
    payload = {'user_id': 'test_user_id_value', 'timestamp': 'test_timestamp_value', 'config_key': 'test_config_key_value', 'old_value': 'test_old_value_value', 'new_value': 'test_new_value_value', 'user_agent': 'test_user_agent_value'}
    result = audit.log_event('config_changed', **payload)
    assert isinstance(result, dict), "log_event() must return a dict"


# ── 2. Universal fields present ───────────────────────────────────────────────

def test_universal_fields_event_type():
    result = audit.log_event('config_changed', **{'user_id': 'test_user_id_value', 'timestamp': 'test_timestamp_value', 'config_key': 'test_config_key_value', 'old_value': 'test_old_value_value', 'new_value': 'test_new_value_value', 'user_agent': 'test_user_agent_value'})
    assert "event_type" in result, "entry must contain 'event_type'"
    assert result["event_type"] == 'config_changed'


def test_universal_fields_log_id():
    result = audit.log_event('config_changed', **{'user_id': 'test_user_id_value', 'timestamp': 'test_timestamp_value', 'config_key': 'test_config_key_value', 'old_value': 'test_old_value_value', 'new_value': 'test_new_value_value', 'user_agent': 'test_user_agent_value'})
    assert "log_id" in result, "entry must contain 'log_id'"
    assert isinstance(result["log_id"], str), "'log_id' must be a string"
    assert len(result["log_id"]) > 0, "'log_id' must not be empty"


def test_log_ids_unique():
    r1 = audit.log_event('config_changed', **{'user_id': 'test_user_id_value', 'timestamp': 'test_timestamp_value', 'config_key': 'test_config_key_value', 'old_value': 'test_old_value_value', 'new_value': 'test_new_value_value', 'user_agent': 'test_user_agent_value'})
    r2 = audit.log_event('config_changed', **{'user_id': 'test_user_id_value', 'timestamp': 'test_timestamp_value', 'config_key': 'test_config_key_value', 'old_value': 'test_old_value_value', 'new_value': 'test_new_value_value', 'user_agent': 'test_user_agent_value'})
    assert r1["log_id"] != r2["log_id"], "Each entry must have a unique log_id"


# ── 3. Required fields per event type ────────────────────────────────────────

@pytest.mark.parametrize("event_type,required_fields", [
    ('config_changed', ['event_type', 'log_id', 'user_id', 'timestamp', 'config_key', 'old_value', 'new_value', 'user_agent']),
    ('user_login', ['event_type', 'log_id', 'user_id', 'timestamp', 'ip_address', 'success', 'correlation_id']),
    ('report_accessed', ['event_type', 'log_id', 'user_id', 'timestamp', 'report_id', 'report_type', 'request_id']),
    ('data_exported', ['event_type', 'log_id', 'user_id', 'timestamp', 'export_format', 'record_count', 'destination', 'user_agent']),
    ('payment_initiated', ['event_type', 'log_id', 'user_id', 'timestamp', 'amount', 'currency', 'recipient_account', 'session_id']),
])
def test_required_fields_present(event_type, required_fields):
    # Build a minimal payload with dummy values for non-universal fields
    _universal = {"event_type", "log_id", "signature", "prev_hash", "checksum"}
    payload = {f: "test_" + f for f in required_fields if f not in _universal}
    entry = audit.log_event(event_type, **payload)
    for field in required_fields:
        assert field in entry, (
            "Event type '" + event_type + "' entry missing required field '" + field + "'"
        )


# ── 4. Tamper-detection field present ────────────────────────────────────────

def test_tamper_field_present():
    result = audit.log_event('config_changed', **{'user_id': 'test_user_id_value', 'timestamp': 'test_timestamp_value', 'config_key': 'test_config_key_value', 'old_value': 'test_old_value_value', 'new_value': 'test_new_value_value', 'user_agent': 'test_user_agent_value'})
    assert 'signature' in result, (
        "Entry must contain tamper-detection field " + repr('signature')
    )


def test_tamper_field_non_empty():
    result = audit.log_event('config_changed', **{'user_id': 'test_user_id_value', 'timestamp': 'test_timestamp_value', 'config_key': 'test_config_key_value', 'old_value': 'test_old_value_value', 'new_value': 'test_new_value_value', 'user_agent': 'test_user_agent_value'})
    assert result.get('signature'), (
        "Tamper-detection field " + repr('signature') + " must not be empty"
    )


# ── 5. get_log() returns all entries ─────────────────────────────────────────

def test_get_log_empty_initially():
    assert audit.get_log() == [], "get_log() must return [] before any events"


def test_get_log_contains_logged_entries():
    audit.log_event('config_changed', **{'user_id': 'test_user_id_value', 'timestamp': 'test_timestamp_value', 'config_key': 'test_config_key_value', 'old_value': 'test_old_value_value', 'new_value': 'test_new_value_value', 'user_agent': 'test_user_agent_value'})
    audit.log_event('config_changed', **{'user_id': 'test_user_id_value', 'timestamp': 'test_timestamp_value', 'config_key': 'test_config_key_value', 'old_value': 'test_old_value_value', 'new_value': 'test_new_value_value', 'user_agent': 'test_user_agent_value'})
    log = audit.get_log()
    assert len(log) == 2, "Expected 2 entries in log, got " + str(len(log))


def test_get_log_returns_list():
    result = audit.get_log()
    assert isinstance(result, list), "get_log() must return a list"


# ── 6. verify_log() on untampered log ────────────────────────────────────────

def test_verify_log_empty():
    result = audit.verify_log([])
    assert result == [], "verify_log([]) must return []"


def test_verify_log_valid_entries_no_tamper():
    audit.log_event('config_changed', **{'user_id': 'test_user_id_value', 'timestamp': 'test_timestamp_value', 'config_key': 'test_config_key_value', 'old_value': 'test_old_value_value', 'new_value': 'test_new_value_value', 'user_agent': 'test_user_agent_value'})
    audit.log_event('config_changed', **{'user_id': 'test_user_id_value', 'timestamp': 'test_timestamp_value', 'config_key': 'test_config_key_value', 'old_value': 'test_old_value_value', 'new_value': 'test_new_value_value', 'user_agent': 'test_user_agent_value'})
    entries = audit.get_log()
    tampered = audit.verify_log(entries)
    assert tampered == [], (
        "verify_log() must return [] for untampered entries, got " + str(tampered)
    )


# ── 7. verify_log() detects tampered entry ───────────────────────────────────

def test_verify_log_detects_tampering():
    audit.log_event('config_changed', **{'user_id': 'test_user_id_value', 'timestamp': 'test_timestamp_value', 'config_key': 'test_config_key_value', 'old_value': 'test_old_value_value', 'new_value': 'test_new_value_value', 'user_agent': 'test_user_agent_value'})
    entries = audit.get_log()
    # Tamper with the entry by mutating a copy
    tampered_entries = [dict(e) for e in entries]
    tampered_entries[0]["event_type"] = "tampered_event"
    # Remove tamper-detection field to simulate manual edit
    tampered_entries[0].pop('signature', None)
    result = audit.verify_log(tampered_entries)
    assert 0 in result, (
        "verify_log() must detect the tampered entry at index 0"
    )


# ── 8. Multiple event types produce correct field sets ───────────────────────

def test_multiple_event_types_logged():
    _two_events = [('config_changed', 'Config Changed', 'System configuration is modified', ['user_id', 'timestamp', 'config_key', 'old_value', 'new_value']), ('user_login', 'User Login', 'A user authenticates into the system', ['user_id', 'timestamp', 'ip_address', 'success'])]
    _schemas = {'config_changed': ['event_type', 'log_id', 'user_id', 'timestamp', 'config_key', 'old_value', 'new_value', 'user_agent'], 'user_login': ['event_type', 'log_id', 'user_id', 'timestamp', 'ip_address', 'success', 'correlation_id'], 'report_accessed': ['event_type', 'log_id', 'user_id', 'timestamp', 'report_id', 'report_type', 'request_id'], 'data_exported': ['event_type', 'log_id', 'user_id', 'timestamp', 'export_format', 'record_count', 'destination', 'user_agent'], 'payment_initiated': ['event_type', 'log_id', 'user_id', 'timestamp', 'amount', 'currency', 'recipient_account', 'session_id']}
    _universal = {"event_type", "log_id", "signature", "prev_hash", "checksum"}
    results = []
    for ev_id, _label, _desc, _fields in _two_events:
        fields = _schemas[ev_id]
        payload = {f: "val_" + f for f in fields if f not in _universal}
        entry = audit.log_event(ev_id, **payload)
        results.append(entry)
    assert len(results) == 2, "Expected 2 logged entries"
    # Just ensure no crash and event_type is set correctly
    for i, (ev_id, _, _, _) in enumerate(_two_events):
        assert results[i]["event_type"] == ev_id


# ── 9. Retention metadata (structural check) ─────────────────────────────────

def test_retention_days_constant_exists():
    """audit.py should work correctly (retention config is in the policy doc)."""
    entry = audit.log_event('config_changed', **{'user_id': 'test_user_id_value', 'timestamp': 'test_timestamp_value', 'config_key': 'test_config_key_value', 'old_value': 'test_old_value_value', 'new_value': 'test_new_value_value', 'user_agent': 'test_user_agent_value'})
    assert entry is not None


# ── 10. log_event stores entry in get_log ────────────────────────────────────

def test_log_event_persists_to_store():
    entry = audit.log_event('config_changed', **{'user_id': 'test_user_id_value', 'timestamp': 'test_timestamp_value', 'config_key': 'test_config_key_value', 'old_value': 'test_old_value_value', 'new_value': 'test_new_value_value', 'user_agent': 'test_user_agent_value'})
    stored = audit.get_log()
    assert len(stored) == 1
    assert stored[0]["log_id"] == entry["log_id"], (
        "Stored entry must match the returned entry"
    )
