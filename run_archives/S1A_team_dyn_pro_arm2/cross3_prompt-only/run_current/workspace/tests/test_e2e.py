"""
End-to-end pipeline test: verifies that the full bridge pipeline
(translate + publish + consume) works correctly after all bugs are fixed.
"""
import pytest
import base64
from bridge.publisher import BridgePublisher
from service_b.consumer import MessageConsumer
from service_b.schema import ErrorCode


def make_consumer_and_publisher():
    consumer = MessageConsumer()
    publisher = BridgePublisher(consumer)
    return consumer, publisher


def test_e2e_translate_and_consume():
    """Full pipeline: JSON -> translate -> consume without errors."""
    consumer, publisher = make_consumer_and_publisher()

    raw = b"end to end binary"
    b64 = base64.b64encode(raw).decode()
    json_data = {
        "event_id": 9007199254740993,
        "event_type": "user.login",
        "payload": b64,
        "status": "STATUS_ACTIVE",
        "occurred_at": 1700000000,
        "text_content": "User logged in from 192.168.1.1",
    }

    # Should not raise (consumer validates types and oneof)
    publisher.publish_record(json_data)

    assert len(consumer.received) == 1
    msg = consumer.received[0]
    assert msg.event_id == 9007199254740993
    assert msg.payload == raw
    assert isinstance(msg.status, int)


def test_e2e_error_routing():
    """Error path: HTTP 404 and 429 must reach consumer with correct codes."""
    consumer, publisher = make_consumer_and_publisher()

    publisher.publish_error(404, "not found")
    publisher.publish_error(429, "rate limited")

    assert len(consumer.errors) == 2
    codes = [e.code for e in consumer.errors]
    assert ErrorCode.NOT_FOUND in codes, f"NOT_FOUND missing from errors: {codes}"
    assert ErrorCode.RESOURCE_EXHAUSTED in codes, (
        f"RESOURCE_EXHAUSTED missing from errors: {codes}"
    )
