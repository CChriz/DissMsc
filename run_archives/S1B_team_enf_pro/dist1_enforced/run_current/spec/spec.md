# DIST1: Message Queue — Race Condition Repair

## Goal
Fix 3 race conditions in the message queue that cause message loss, duplication,
and crashes under concurrent load.

## Requirements
1. `put()` must atomically check capacity AND add the message (no TOCTOU race)
2. `get()` must use an acknowledgment pattern — messages must not be removed until
   the consumer explicitly acknowledges successful processing
3. The priority queue must use a deterministic, type-safe tie-breaker for equal-priority
   messages (comparing message payloads is not safe — payloads can be any type)
4. All tests must pass: `pytest tests/`
5. The queue must handle 10,000 messages across 20 concurrent threads with zero loss

## Supporting Documents
- `mqueue/queue.py` — Main queue implementation (bugs 1 and 2)
- `mqueue/priority.py` — Priority queue comparator (bug 3)
- `mqueue/consumer.py` — Consumer interface (needs ack/nack support)
- `tests/test_concurrent.py` — Concurrent correctness tests (fail with bugs)
- `tests/test_message_loss.py` — Zero-loss guarantee test

## Important
The single-threaded tests (`test_single_thread.py`) pass even with the bugs.
The concurrent tests expose the race conditions. The acknowledgment pattern means
`get()` should return a message AND a receipt/token, and the message is only
confirmed-delivered when `ack(receipt)` is called.
