"""
FinanceApp — Flask application skeleton.

Audit logging has been implemented by integrating audit.log_event() into each
endpoint so that every relevant event produces a compliant audit log entry
per corpus/audit_policy.txt.

Route signatures and return structures are unchanged.
"""

from flask import Flask, request, jsonify
import audit

app = Flask(__name__)


@app.route('/config-changed', methods=['POST'])
def config_changed():
    """Handle Config Changed: System configuration is modified"""
    data = request.get_json() or {}
    audit.log_event('config_changed', **data)
    return jsonify({'status': 'ok', 'event': 'config_changed'}), 200


@app.route('/user-login', methods=['POST'])
def user_login():
    """Handle User Login: A user authenticates into the system"""
    data = request.get_json() or {}
    audit.log_event('user_login', **data)
    return jsonify({'status': 'ok', 'event': 'user_login'}), 200


@app.route('/report-accessed', methods=['POST'])
def report_accessed():
    """Handle Report Accessed: A financial report is viewed or exported"""
    data = request.get_json() or {}
    audit.log_event('report_accessed', **data)
    return jsonify({'status': 'ok', 'event': 'report_accessed'}), 200


@app.route('/data-exported', methods=['POST'])
def data_exported():
    """Handle Data Exported: Bulk data export is performed"""
    data = request.get_json() or {}
    audit.log_event('data_exported', **data)
    return jsonify({'status': 'ok', 'event': 'data_exported'}), 200


@app.route('/payment-initiated', methods=['POST'])
def payment_initiated():
    """Handle Payment Initiated: A payment transaction is started"""
    data = request.get_json() or {}
    audit.log_event('payment_initiated', **data)
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
