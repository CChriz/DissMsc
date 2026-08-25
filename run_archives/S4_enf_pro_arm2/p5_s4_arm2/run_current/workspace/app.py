"""
FinanceApp — Flask application skeleton.

Audit logging has NOT been implemented yet.
Your task: integrate audit.log_event() into each endpoint so that every
relevant event produces a compliant audit log entry per corpus/audit_policy.txt.

Do NOT modify the route signatures or return structures.
"""

from flask import Flask, request, jsonify
import sys
import audit

app = Flask(__name__)


def _safe_audit_log(event_type, **fields):
    """Call audit.log_event() without blocking the endpoint response.

    Audit failures (missing fields, invalid types, I/O errors) are logged
    to stderr but never raised to the caller — the endpoint always returns
    its normal response.
    """
    try:
        return audit.log_event(event_type, **fields)
    except Exception:
        print(
            f"[audit] WARNING: Failed to log event '{event_type}'",
            file=sys.stderr,
        )
        return None


@app.route('/config-changed', methods=['POST'])
def config_changed():
    """Handle Config Changed: System configuration is modified"""
    data = request.get_json() or {}
    _safe_audit_log(
        'config_changed',
        user_id=data.get('user_id', ''),
        config_key=data.get('config_key', ''),
        old_value=data.get('old_value', ''),
        new_value=data.get('new_value', ''),
        user_agent=request.headers.get('User-Agent', ''),
    )
    return jsonify({'status': 'ok', 'event': 'config_changed'}), 200


@app.route('/user-login', methods=['POST'])
def user_login():
    """Handle User Login: A user authenticates into the system"""
    data = request.get_json() or {}
    _safe_audit_log(
        'user_login',
        user_id=data.get('user_id', ''),
        ip_address=request.remote_addr or '',
        success=data.get('success', False),
        correlation_id=data.get('correlation_id', ''),
    )
    return jsonify({'status': 'ok', 'event': 'user_login'}), 200


@app.route('/report-accessed', methods=['POST'])
def report_accessed():
    """Handle Report Accessed: A financial report is viewed or exported"""
    data = request.get_json() or {}
    _safe_audit_log(
        'report_accessed',
        user_id=data.get('user_id', ''),
        report_id=data.get('report_id', ''),
        report_type=data.get('report_type', ''),
        request_id=data.get('request_id', ''),
    )
    return jsonify({'status': 'ok', 'event': 'report_accessed'}), 200


@app.route('/data-exported', methods=['POST'])
def data_exported():
    """Handle Data Exported: Bulk data export is performed"""
    data = request.get_json() or {}
    _safe_audit_log(
        'data_exported',
        user_id=data.get('user_id', ''),
        export_format=data.get('export_format', ''),
        record_count=data.get('record_count', 0),
        destination=data.get('destination', ''),
        user_agent=request.headers.get('User-Agent', ''),
    )
    return jsonify({'status': 'ok', 'event': 'data_exported'}), 200


@app.route('/payment-initiated', methods=['POST'])
def payment_initiated():
    """Handle Payment Initiated: A payment transaction is started"""
    data = request.get_json() or {}
    _safe_audit_log(
        'payment_initiated',
        user_id=data.get('user_id', ''),
        amount=data.get('amount', 0.0),
        currency=data.get('currency', ''),
        recipient_account=data.get('recipient_account', ''),
        session_id=data.get('session_id', ''),
    )
    return jsonify({'status': 'ok', 'event': 'payment_initiated'}), 200


@app.route('/audit-log', methods=['GET'])
def get_audit_log():
    """Return all audit log entries."""
    return jsonify({'entries': audit.get_log()}), 200


@app.route('/verify-log', methods=['GET'])
def verify_audit_log():
    """Verify audit log integrity and return tampered entry indices."""
    entries = audit.get_log()
    tampered = audit.verify_log(entries)
    return jsonify({'tampered_indices': tampered}), 200


if __name__ == '__main__':
    app.run(debug=False)
