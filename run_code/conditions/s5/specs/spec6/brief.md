# SPEC6: RFC-Style Protocol Implementation (Brief)

Implement the KVP (Key-Value Protocol) in `protocol.py`. The `KVStore` class must
handle text commands: SET, GET, DEL, KEYS, COUNT, FLUSH, plus optional
MSET, MGET, TTL, RENAME, TYPE, DUMP.

The protocol has 13 requirements (7 MUST, 3 SHOULD, 3 MAY). All 7 MUST and
at least 2 SHOULD are required to pass. See `protocol_spec.txt` in workspace
for the full RFC-style specification.

Run: `python -m pytest tests/test_protocol.py -v`
