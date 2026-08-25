"""
FinanceApp — Flask application skeleton with integrated audit logging.

Audit logging has been implemented: every security-relevant endpoint produces
a compliant audit log entry via audit.log_event(). Logging failures are
non-blocking (try/except + stderr fallback).

Route signatures and return structures are preserved as required.
"""

import sys
import uuid

from flask import Flask, request, jsonify
import audit

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Request context extraction helpers
# ---------------------------------------------------------------------------

def _extract_user_id() -> str:
    """Extract user_id from request context using priority chain.

    Priority: X-User-ID header → request.current_user → remote_addr → 'anonymous'
    """
    header_user = request.headers.get('X-User-ID', '').strip()
    if header_user:
        return header_user

    current_user = getattr(request, 'current_user', None)
    if current_user:
        return str(current_user)

    return request.remote_addr or 'anonymous'


def _extract_ip_address() -> str:
    """Extract client IP address."""
    forwarded = request.headers.get('X-Forwarded-For', '').strip()
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or '0.0.0.0'


def _extract_user_agent() -> str:
    """Extract User-Agent header value."""
    return request.headers.get('User-Agent', 'unknown')


def _extract_correlation_id() -> str:
    """Extract or generate correlation_id for request tracing."""
    corr_id = request.headers.get('X-Correlation-ID', '').strip()
    return corr_id if corr_id else str(uuid.uuid4())


def _extract_request_id() -> str:
    """Extract or generate request_id for request tracing."""
    req_id = request.headers.get('X-Request-ID', '').strip()
    return req_id if req_id else str(uuid.uuid4())


def _extract_session_id() -> str:
    """Extract session_id from request header."""
    sess_id = request.headers.get('X-Session-ID', '').strip()
    return sess_id if sess_id else str(uuid.uuid4())


def _safe_audit(event_type: str, **fields) -> None:
    """Call audit.log_event() in a non-blocking manner.

    If logging fails, the error is written to stderr and the exception is
    silently swallowed so that the business response is not affected.
    """
    try:
        audit.log_event(event_type, **fields)
    except Exception as exc:
        print(
            f'AUDIT_FAILED: event_type={event_type} user_id={fields.get("user_id", "?")} '
            f'error={exc}',
            file=sys.stderr,
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.route('/config-changed', methods=['POST'])
def config_changed():
    """Handle Config Changed: System configuration is modified"""
    data = request.get_json() or {}

    _safe_audit(
        'config_changed',
        user_id=_extract_user_id(),
        config_key=data.get('config_key', ''),
        old_value=data.get('old_value', ''),
        new_value=data.get('new_value', ''),
        user_agent=_extract_user_agent(),
    )

    return jsonify({'status': 'ok', 'event': 'config_changed'}), 200


@app.route('/user-login', methods=['POST'])
def user_login():
    """Handle User Login: A user authenticates into the system"""
    data = request.get_json() or {}

    _safe_audit(
        'user_login',
        user_id=_extract_user_id(),
        ip_address=_extract_ip_address(),
        success=data.get('success', False),
        correlation_id=_extract_correlation_id(),
    )

    return jsonify({'status': 'ok', 'event': 'user_login'}), 200


@app.route('/report-accessed', methods=['POST'])
def report_accessed():
    """Handle Report Accessed: A financial report is viewed or exported"""
    data = request.get_json() or {}

    _safe_audit(
        'report_accessed',
        user_id=_extract_user_id(),
        report_id=data.get('report_id', ''),
        report_type=data.get('report_type', ''),
        request_id=_extract_request_id(),
    )

    return jsonify({'status': 'ok', 'event': 'report_accessed'}), 200


@app.route('/data-exported', methods=['POST'])
def data_exported():
    """Handle Data Exported: Bulk data export is performed"""
    data = request.get_json() or {}

    _safe_audit(
        'data_exported',
        user_id=_extract_user_id(),
        export_format=data.get('export_format', ''),
        record_count=data.get('record_count', 0),
        destination=data.get('destination', ''),
        user_agent=_extract_user_agent(),
    )

    return jsonify({'status': 'ok', 'event': 'data_exported'}), 200


@app.route('/payment-initiated', methods=['POST'])
def payment_initiated():
    """Handle Payment Initiated: A payment transaction is started"""
    data = request.get_json() or {}

    _safe_audit(
        'payment_initiated',
        user_id=_extract_user_id(),
        amount=data.get('amount', 0),
        currency=data.get('currency', ''),
        recipient_account=data.get('recipient_account', ''),
        session_id=_extract_session_id(),
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
