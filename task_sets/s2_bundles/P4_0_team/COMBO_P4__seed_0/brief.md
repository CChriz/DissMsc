# Combined task: P4

This workspace contains 2 INDEPENDENT subtasks. Complete ALL of them; each is graded separately. Files for different subtasks are co-located in one workspace — identify which files belong to which subtask.



====================================================================
## Subtask 1: spec6  (spec, HTNI)
====================================================================

# SPEC6: RFC-Style Protocol Implementation (Brief)

Implement the KVP (Key-Value Protocol) in `protocol.py`. The `KVStore` class must
handle text commands: SET, GET, DEL, KEYS, COUNT, EXISTS, FLUSH, plus optional
MSET, MGET, TTL, SETEX, APPEND, RENAME, TYPE, DUMP.

The protocol has 20 requirements (12 MUST, 5 SHOULD, 3 MAY). All 12 MUST and
at least 3 SHOULD are required to pass. See `protocol_spec.txt` in workspace
for the full RFC-style specification.

Run: `python -m pytest tests/test_protocol.py -v`



====================================================================
## Subtask 2: lh5  (lh, LB90)
====================================================================

# LH5: Data Migration (Brief)

Data needs to be migrated to the new format. Execute the migration.

- Source: `data/old_format/` (csv)
- Target: `data/new_format/` (jsonl)
- Domain: IoT sensor telemetry

Run: `python migrate.py`
Validate: `python validate.py`

The Planner has the full 6-step migration plan with validation checkpoints and rollback triggers.
