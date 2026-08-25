# SPEC6: RFC-Style Protocol Implementation (Brief)

Implement the KVP (Key-Value Protocol) in `protocol.py`. The `KVStore` class must
handle text commands: SET, GET, DEL, KEYS, COUNT, EXISTS, FLUSH, plus optional
MSET, MGET, TTL, SETEX, APPEND, RENAME, TYPE, DUMP.

The protocol has 20 requirements (12 MUST, 5 SHOULD, 3 MAY). All 12 MUST and
at least 3 SHOULD are required to pass. See `protocol_spec.txt` in workspace
for the full RFC-style specification.

Run: `python -m pytest tests/test_protocol.py -v`
