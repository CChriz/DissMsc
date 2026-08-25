# PIPE3: Stream Processing Pipeline — Serialization Mismatch Fixes

## Goal
Fix 3 serialization mismatch bugs in a stream processing pipeline where a producer
generates events, a processor transforms them, and a sink writes the final output.
Each component makes different assumptions about data format, encoding, and structure.

## Requirements
1. **Datetime serialization**: The producer serializes datetime fields using `default=str` (which produces `"2023-11-14 22:13:20"` format). The processor expects ISO 8601 format (`"2023-11-14T22:13:20"`). Fix the producer to use `.isoformat()` for datetime fields.
2. **Envelope stripping**: The processor wraps its output in `{"data": <payload>}` envelopes. The sink expects bare payload objects (no wrapper). Fix the processor to emit bare objects, OR fix the sink to unwrap the envelope.
3. **Encoding consistency**: The processor writes output strings with latin-1 encoding for special characters (accented names, currency symbols). The sink reads with UTF-8 decoding, causing `UnicodeDecodeError` on non-ASCII content. Fix the processor to use UTF-8 encoding.
4. All tests in `tests/` must pass after fixes.

## Supporting Documents
- `producer.py` — Event producer (Bug 1: datetime serialization)
- `processor.py` — Event transformer (Bug 2: envelope wrapping; Bug 3: latin-1 encoding)
- `sink.py` — Output writer expecting bare UTF-8 JSON objects
- `models.py` — Shared event schema definitions
- `tests/test_pipeline.py` — End-to-end pipeline tests
- `tests/test_serialization.py` — Targeted serialization tests

## Background

### Stream Processing Serialization Contracts

In a producer-processor-sink pipeline, each component must agree on:
1. **Data format**: How types (datetime, decimal, bytes) are serialized to JSON
2. **Message structure**: Whether messages are bare objects or wrapped in envelopes
3. **Character encoding**: What encoding is used for string data

### The 3 Bugs

| Component | Bug | Symptom |
|-----------|-----|---------|
| Producer | `json.dumps(default=str)` for datetime | Processor's `datetime.fromisoformat()` fails on space-separated format |
| Processor | Wraps output in `{"data": ...}` | Sink tries to access fields directly on the envelope, gets KeyError |
| Processor | Writes with `encoding='latin-1'` | Sink's UTF-8 read raises UnicodeDecodeError on `"Müller"`, `"€"` |

### Real-World Context
These are the 3 most common integration bugs in stream processing pipelines:
- **datetime format mismatch**: Python's `str(datetime)` produces `"YYYY-MM-DD HH:MM:SS"`,
  not ISO 8601 `"YYYY-MM-DDTHH:MM:SS"`. This breaks `fromisoformat()` in Python < 3.11
  and every non-Python consumer.
- **envelope wrapping**: Some processors add metadata wrappers; downstream consumers
  must either expect the wrapper or the processor must be configured to emit bare objects.
- **encoding mismatch**: latin-1 encodes all byte values 0-255 but cannot represent
  characters outside that range, while UTF-8 is the universal standard.

## Hidden Complexity
- The datetime bug only manifests for datetime objects, not date-only or string timestamps.
- The envelope bug is masked when the sink reads test data that happens to have a `"data"` key.
- The encoding bug only triggers on non-ASCII characters; pure ASCII data passes fine.
