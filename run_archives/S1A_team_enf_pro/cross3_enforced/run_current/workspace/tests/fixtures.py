"""
Test fixtures: sample JSON inputs and expected translated messages.
"""
import base64

# A large int64 value that would be corrupted by a 32-bit mask
LARGE_RECORD_ID = 9007199254740993

# Raw binary payload and its base64 encoding (as Service A would send it)
RAW_PAYLOAD = b"binary data here"
B64_PAYLOAD = base64.b64encode(RAW_PAYLOAD).decode()  # "YmluYXJ5IGRhdGEgaGVyZQ=="

# Minimal valid JSON dict from Service A (text_content oneof variant)
SAMPLE_JSON_TEXT = {
    "event_id": LARGE_RECORD_ID,
    "event_type": "user.login",
    "payload": B64_PAYLOAD,
    "status": "STATUS_ACTIVE",
    "occurred_at": 1700000000,
    "text_content": "User logged in from 192.168.1.1",
    # binary_content intentionally absent -> only content_text set
}

# JSON dict using binary content oneof variant
SAMPLE_JSON_BINARY = {
    "event_id": LARGE_RECORD_ID,
    "event_type": "user.login",
    "payload": B64_PAYLOAD,
    "status": "STATUS_INACTIVE",
    "occurred_at": 1700000001,
    # text_content intentionally absent -> only content_binary set
    "binary_content": B64_PAYLOAD,
}
