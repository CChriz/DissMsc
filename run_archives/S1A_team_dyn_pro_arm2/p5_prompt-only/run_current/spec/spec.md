# P5: Audit Logging for Compliance

## Goal

Implement compliant audit logging in `audit.py` and integrate it into `app.py` so that
every security-relevant event produces a tamper-evident audit log entry meeting
SOX / PCI-DSS requirements.

## Application Domain

**Financial Services** — FinanceApp
Regulatory framework: **SOX / PCI-DSS**

## Required Event Types and Fields

The following events must be logged. Each entry must contain ALL listed fields.

- **config_changed** (Config Changed): System configuration is modified
  Required fields: `event_type`, `log_id`, `user_id`, `timestamp`, `config_key`, `old_value`, `new_value`, `user_agent`
- **user_login** (User Login): A user authenticates into the system
  Required fields: `event_type`, `log_id`, `user_id`, `timestamp`, `ip_address`, `success`, `correlation_id`
- **report_accessed** (Report Accessed): A financial report is viewed or exported
  Required fields: `event_type`, `log_id`, `user_id`, `timestamp`, `report_id`, `report_type`, `request_id`
- **data_exported** (Data Exported): Bulk data export is performed
  Required fields: `event_type`, `log_id`, `user_id`, `timestamp`, `export_format`, `record_count`, `destination`, `user_agent`
- **payment_initiated** (Payment Initiated): A payment transaction is started
  Required fields: `event_type`, `log_id`, `user_id`, `timestamp`, `amount`, `currency`, `recipient_account`, `session_id`

**Universal fields** (required on every entry regardless of event type):
- `event_type` (string): the event type identifier
- `log_id` (string): a unique UUID4 string for this entry

## Tamper Detection

**Method:** HMAC-SHA256 Entry Signature

Each audit log entry must include a `signature` field containing an HMAC-SHA256 digest of the canonical JSON of the entry (fields sorted alphabetically, excluding the `signature` field itself). The HMAC key is the value of the environment variable AUDIT_HMAC_KEY (default: 'default-key' if unset). This allows any entry to be independently verified for tampering.

Required tamper-detection field: `signature`

## Retention Policy

Minimum retention period: **7 years** (2555 days)

Audit logs must be retained for at least this period and must not be modified or
deleted before expiry.

## Log Rotation

Strategy: **daily**

Audit log files must be rotated daily. Each file is named audit_YYYY-MM-DD.jsonl. The current day's entries are written to audit_today.jsonl and renamed at midnight.

## Hard Requirements

1. Implement `log_event(event_type, **fields) -> dict` in `audit.py`.
   - Must include all required fields for the event type (see above).
   - Must compute and attach the `signature` tamper-detection field.
   - Must append the entry to an in-memory log and return it.

2. Implement `get_log() -> list[dict]` returning all stored entries.

3. Implement `verify_log(entries) -> list[int]` returning indices of tampered entries.

4. Integrate `audit.log_event()` into every relevant endpoint in `app.py`.

5. All entries must have unique `log_id` values (UUID4).

6. `verify_log()` must correctly detect entries whose `signature` field
   has been corrupted or is missing.

## Files

- `corpus/audit_policy.txt` — authoritative compliance policy (read this first)
- `audit.py` — implement all audit functions here
- `app.py` — integrate audit logging into each endpoint
- `tests/test_audit.py` — test suite that must pass

## Deliverables

- `audit.py` fully implemented
- `app.py` with `audit.log_event()` called at each event endpoint
- All tests in `tests/test_audit.py` passing
- Verifier produces `output/attestation.json` with verdict
