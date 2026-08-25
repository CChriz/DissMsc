"""
FinanceApp — Flask application skeleton.

Audit logging has been integrated for all security-relevant endpoints.
Every endpoint that triggers a loggable event produces a compliant audit
log entry per corpus/audit_policy.txt.

Do NOT modify the route signatures or return structures.
"""

import uuid
from flask import Flask, request, jsonify
import audit

app = Flask(__name__)


@app.route('/config-changed', methods=['POST'])
def config_changed():
    """Handle Config Changed: System configuration is modified"""
    data = request.get_json() or {}
    try:
        audit.log_event('config_changed',
            user_id=data.get('user_id', ''),
            timestamp=data.get('timestamp', ''),
            config_key=data.get('config_key', ''),
            old_value=data.get('old_value', ''),
            new_value=data.get('new_value', ''),
            user_agent=data.get('user_agent', request.headers.get('User-Agent', '')))
    except Exception as e:
        print(f"[AUDIT] Failed to log config_changed: {e}", flush=True)
    return jsonify({'status': 'ok', 'event': 'config_changed'}), 200


@app.route('/user-login', methods=['POST'])
def user_login():
    """Handle User Login: A user authenticates into the system"""
    data = request.get_json() or {}
    try:
        # Ensure success is boolean
        success_raw = data.get('success', False)
        if isinstance(success_raw, str):
            success = success_raw.lower() in ('true', '1', 'yes')
        else:
            success = bool(success_raw)
        audit.log_event('user_login',
            user_id=data.get('user_id', ''),
            timestamp=data.get('timestamp', ''),
            ip_address=data.get('ip_address', request.remote_addr or ''),
            success=success,
            correlation_id=data.get('correlation_id')
                         or request.headers.get('X-Correlation-ID')
                         or str(uuid.uuid4())))
    except Exception as e:
        print(f"[AUDIT] Failed to log user_login: {e}", flush=True)
    return jsonify({'status': 'ok', 'event': 'user_login'}), 200


@app.route('/report-accessed', methods=['POST'])
def report_accessed():
    """Handle Report Accessed: A financial report is viewed or exported"""
    data = request.get_json() or {}
    try:
        audit.log_event('report_accessed',
            user_id=data.get('user_id', ''),
            timestamp=data.get('timestamp', ''),
            report_id=data.get('report_id', ''),
            report_type=data.get('report_type', ''),
            request_id=data.get('request_id')
                      or request.headers.get('X-Request-ID')
                      or str(uuid.uuid4())))
    except Exception as e:
        print(f"[AUDIT] Failed to log report_accessed: {e}", flush=True)
    return jsonify({'status': 'ok', 'event': 'report_accessed'}), 200


@app.route('/data-exported', methods=['POST'])
def data_exported():
    """Handle Data Exported: Bulk data export is performed"""
    data = request.get_json() or {}
    try:
        audit.log_event('data_exported',
            user_id=data.get('user_id', ''),
            timestamp=data.get('timestamp', ''),
            export_format=data.get('export_format', ''),
            record_count=data.get('record_count', 0),
            destination=data.get('destination', ''),
            user_agent=data.get('user_agent', request.headers.get('User-Agent', '')))
    except Exception as e:
        print(f"[AUDIT] Failed to log data_exported: {e}", flush=True)
    return jsonify({'status': 'ok', 'event': 'data_exported'}), 200


@app.route('/payment-initiated', methods=['POST'])
def payment_initiated():
    """Handle Payment Initiated: A payment transaction is started"""
    data = request.get_json() or {}
    try:
        audit.log_event('payment_initiated',
            user_id=data.get('user_id', ''),
            timestamp=data.get('timestamp', ''),
            amount=data.get('amount', ''),
            currency=data.get('currency', ''),
            recipient_account=data.get('recipient_account', ''),
            session_id=data.get('session_id') or str(uuid.uuid4())))
    except Exception as e:
        print(f"[AUDIT] Failed to log payment_initiated: {e}", flush=True)
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
