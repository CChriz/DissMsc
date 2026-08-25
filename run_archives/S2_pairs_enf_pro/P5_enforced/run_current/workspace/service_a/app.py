"""
Event Streaming API — Flask REST API.

This is the source-of-truth REST service. The bridge polls these endpoints
and translates responses into Service B messages.
"""
from flask import Flask, jsonify, abort
from service_a.models import EventRecord
import base64

app = Flask(__name__)

# Sample data store
_STORE = {
    1: EventRecord(
        event_id=9007199254740993,
        event_type="user.login",
        payload=base64.b64encode(b"sample binary data").decode(),
        status="STATUS_ACTIVE",
        occurred_at=1700000000,
        text_content="User logged in from 192.168.1.1",
        binary_content="",
    ),
}


@app.route("/events/<int:record_id>", methods=["GET"])
def get_record(record_id: int):
    """Return a single record as JSON."""
    record = _STORE.get(record_id)
    if record is None:
        abort(404)
    return jsonify(record.to_dict())


@app.route("/events", methods=["GET"])
def list_records():
    """Return all records as JSON."""
    return jsonify([r.to_dict() for r in _STORE.values()])


if __name__ == "__main__":
    app.run(port=5000)
