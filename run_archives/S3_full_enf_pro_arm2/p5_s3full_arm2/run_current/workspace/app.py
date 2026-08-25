"""
FinanceApp - Flask Application with Integrated Audit Logging
============================================================
All 5 endpoints log security-relevant events via audit.log_event().
Logging failures are non-blocking: they are caught, logged as warnings,
and never propagate to the caller.
"""

import logging
from flask import Flask, request, jsonify

import audit

logger = logging.getLogger(__name__)

app = Flask(__name__)


# ---------------------------------------------------------------------------
# POST /config-changed  →  audit event: config_changed
# ---------------------------------------------------------------------------
@app.route("/config-changed", methods=["POST"])
def config_changed():
    data = request.get_json()

    # --- business logic here (unchanged) ---
    # (placeholder for actual config-change processing)

    # --- audit logging (non-blocking) ---
    try:
        audit.log_event(
            "config_changed",
            user_id=data["user_id"],
            config_key=data["config_key"],
            old_value=data["old_value"],
            new_value=data["new_value"],
            user_agent=data["user_agent"],
        )
    except Exception as exc:
        logger.warning("Audit log failed for config_changed: %s", exc)

    return jsonify({"status": "success", "message": "Config changed"})


# ---------------------------------------------------------------------------
# POST /user-login  →  audit event: user_login
# ---------------------------------------------------------------------------
@app.route("/user-login", methods=["POST"])
def user_login():
    data = request.get_json()

    # --- business logic here (unchanged) ---

    # --- audit logging (non-blocking) ---
    try:
        audit.log_event(
            "user_login",
            user_id=data["user_id"],
            ip_address=data["ip_address"],
            success=data["success"],
            correlation_id=data["correlation_id"],
        )
    except Exception as exc:
        logger.warning("Audit log failed for user_login: %s", exc)

    return jsonify({"status": "success", "message": "User login recorded"})


# ---------------------------------------------------------------------------
# POST /report-accessed  →  audit event: report_accessed
# ---------------------------------------------------------------------------
@app.route("/report-accessed", methods=["POST"])
def report_accessed():
    data = request.get_json()

    # --- business logic here (unchanged) ---

    # --- audit logging (non-blocking) ---
    try:
        audit.log_event(
            "report_accessed",
            user_id=data["user_id"],
            report_id=data["report_id"],
            report_type=data["report_type"],
            request_id=data["request_id"],
        )
    except Exception as exc:
        logger.warning("Audit log failed for report_accessed: %s", exc)

    return jsonify({"status": "success", "message": "Report accessed"})


# ---------------------------------------------------------------------------
# POST /data-exported  →  audit event: data_exported
# ---------------------------------------------------------------------------
@app.route("/data-exported", methods=["POST"])
def data_exported():
    data = request.get_json()

    # --- business logic here (unchanged) ---

    # --- audit logging (non-blocking) ---
    try:
        audit.log_event(
            "data_exported",
            user_id=data["user_id"],
            export_format=data["export_format"],
            record_count=data["record_count"],
            destination=data["destination"],
            user_agent=data["user_agent"],
        )
    except Exception as exc:
        logger.warning("Audit log failed for data_exported: %s", exc)

    return jsonify({"status": "success", "message": "Data exported"})


# ---------------------------------------------------------------------------
# POST /payment-initiated  →  audit event: payment_initiated
# ---------------------------------------------------------------------------
@app.route("/payment-initiated", methods=["POST"])
def payment_initiated():
    data = request.get_json()

    # --- business logic here (unchanged) ---

    # --- audit logging (non-blocking) ---
    try:
        audit.log_event(
            "payment_initiated",
            user_id=data["user_id"],
            amount=data["amount"],
            currency=data["currency"],
            recipient_account=data["recipient_account"],
            session_id=data["session_id"],
        )
    except Exception as exc:
        logger.warning("Audit log failed for payment_initiated: %s", exc)

    return jsonify({"status": "success", "message": "Payment initiated"})


# ---------------------------------------------------------------------------
# Auxiliary routes for audit log inspection / verification
# ---------------------------------------------------------------------------
@app.route("/audit-log", methods=["GET"])
def audit_log():
    """Return all in-memory audit log entries (debug / verification)."""
    try:
        return jsonify(audit.get_log())
    except Exception as exc:
        logger.warning("Audit log retrieval failed: %s", exc)
        return jsonify({"error": "Failed to retrieve audit log"}), 500


@app.route("/verify-log", methods=["GET"])
def verify_log():
    """Verify integrity of all in-memory audit log entries."""
    try:
        return jsonify(audit.verify_log())
    except Exception as exc:
        logger.warning("Audit log verification failed: %s", exc)
        return jsonify({"error": "Failed to verify audit log"}), 500


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
