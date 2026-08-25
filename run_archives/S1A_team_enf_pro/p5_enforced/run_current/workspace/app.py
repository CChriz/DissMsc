"""
FinanceApp — Flask application skeleton.

Audit logging has NOT been implemented yet.
Your task: integrate audit.log_event() into each endpoint so that every
relevant event produces a compliant audit log entry per corpus/audit_policy.txt.

Do NOT modify the route signatures or return structures.
"""

from flask import Flask, request, jsonify
import audit

app = Flask(__name__)


@app.route('/config-changed', methods=['POST'])
def config_changed():
    """Handle Config Changed: System configuration is modified"""
    data = request.get_json() or {}
    entry = audit.log_event('config_changed', **data)
    return jsonify({'status': 'ok', 'event': 'config_changed', 'log_entry': entry}), 200


@app.route('/user-login', methods=['POST'])
def user_login():
    """Handle User Login: A user authenticates into the system"""
    data = request.get_json() or {}
    entry = audit.log_event('user_login', **data)
    return jsonify({'status': 'ok', 'event': 'user_login', 'log_entry': entry}), 200


@app.route('/report-accessed', methods=['POST'])
def report_accessed():
    """Handle Report Accessed: A financial report is viewed or exported"""
    data = request.get_json() or {}
    entry = audit.log_event('report_accessed', **data)
    return jsonify({'status': 'ok', 'event': 'report_accessed', 'log_entry': entry}), 200


@app.route('/data-exported', methods=['POST'])
def data_exported():
    """Handle Data Exported: Bulk data export is performed"""
    data = request.get_json() or {}
    entry = audit.log_event('data_exported', **data)
    return jsonify({'status': 'ok', 'event': 'data_exported', 'log_entry': entry}), 200


@app.route('/payment-initiated', methods=['POST'])
def payment_initiated():
    """Handle Payment Initiated: A payment transaction is started"""
    data = request.get_json() or {}
    entry = audit.log_event('payment_initiated', **data)
    return jsonify({'status': 'ok', 'event': 'payment_initiated', 'log_entry': entry}), 200


@app.route('/audit-log', methods=['GET'])
def get_audit_log():
    """Return all audit log entries."""
    entries = audit.get_log()
    return jsonify({'entries': entries, 'count': len(entries)}), 200


@app.route('/verify-log', methods=['GET', 'POST'])
def verify_audit_log():
    """Verify audit log integrity and return tampered entry indices."""
    if request.method == 'POST':
        body = request.get_json() or {}
        entries = body.get('entries', audit.get_log())
    else:
        entries = audit.get_log()
    tampered = audit.verify_log(entries)
    status = "clean" if len(tampered) == 0 else "tampered"
    return jsonify({'tampered_indices': tampered, 'status': status}), 200


if __name__ == '__main__':
    app.run(debug=False)
