"""
FinanceApp — Flask application with audit logging integration.

Audit logging via audit.log_event() is integrated into every security-relevant
endpoint.  Logging failures are non-blocking — they are logged to stderr but
never cause a 500 response for the business request.

Read corpus/audit_policy.txt for compliance requirements.
"""

import sys
import traceback
from flask import Flask, request, jsonify
import audit

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Non-blocking audit wrapper — logging failures MUST NOT break the application
# ---------------------------------------------------------------------------

def safe_audit(event_type: str, **fields):
    """
    Wrap audit.log_event() so that any exception (e.g. missing fields,
    disk error) is caught and reported to stderr without crashing the
    calling endpoint.
    """
    try:
        return audit.log_event(event_type, **fields)
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# POST endpoints — security-relevant events
# ---------------------------------------------------------------------------

@app.route("/config-changed", methods=["POST"])
def config_changed():
    """Handle Config Changed: System configuration is modified."""
    data = request.get_json() or {}
    entry = safe_audit(
        "config_changed",
        user_id=data.get("user_id", ""),
        config_key=data.get("config_key", ""),
        old_value=data.get("old_value", ""),
        new_value=data.get("new_value", ""),
        user_agent=request.headers.get("User-Agent", ""),
    )
    return jsonify(entry), 201


@app.route("/user-login", methods=["POST"])
def user_login():
    """Handle User Login: A user authenticates into the system."""
    data = request.get_json() or {}
    entry = safe_audit(
        "user_login",
        user_id=data.get("user_id", ""),
        ip_address=request.remote_addr or "127.0.0.1",
        success=data.get("success", False),
        correlation_id=data.get("correlation_id", ""),
    )
    return jsonify(entry), 201


@app.route("/report-accessed", methods=["POST"])
def report_accessed():
    """Handle Report Accessed: A financial report is viewed or exported."""
    data = request.get_json() or {}
    entry = safe_audit(
        "report_accessed",
        user_id=data.get("user_id", ""),
        report_id=data.get("report_id", ""),
        report_type=data.get("report_type", ""),
        request_id=data.get("request_id", ""),
    )
    return jsonify(entry), 201


@app.route("/data-exported", methods=["POST"])
def data_exported():
    """Handle Data Exported: Bulk data export is performed."""
    data = request.get_json() or {}
    entry = safe_audit(
        "data_exported",
        user_id=data.get("user_id", ""),
        export_format=data.get("export_format", ""),
        record_count=data.get("record_count", 0),
        destination=data.get("destination", ""),
        user_agent=request.headers.get("User-Agent", ""),
    )
    return jsonify(entry), 201


@app.route("/payment-initiated", methods=["POST"])
def payment_initiated():
    """Handle Payment Initiated: A payment transaction is started."""
    data = request.get_json() or {}
    entry = safe_audit(
        "payment_initiated",
        user_id=data.get("user_id", ""),
        amount=data.get("amount", 0),
        currency=data.get("currency", ""),
        recipient_account=data.get("recipient_account", ""),
        session_id=data.get("session_id", ""),
    )
    return jsonify(entry), 201


# ---------------------------------------------------------------------------
# GET endpoints — audit log retrieval and verification
# ---------------------------------------------------------------------------

@app.route("/audit-log", methods=["GET"])
def get_audit_log():
    """Return all audit log entries."""
    entries = audit.get_log()
    return jsonify(entries), 200


@app.route("/verify-log", methods=["GET"])
def verify_audit_log():
    """Verify audit log integrity and return tampered entry indices."""
    entries = audit.get_log()
    tampered = audit.verify_log(entries)
    return jsonify({"tampered_indices": tampered, "total_entries": len(entries)}), 200


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=False)
