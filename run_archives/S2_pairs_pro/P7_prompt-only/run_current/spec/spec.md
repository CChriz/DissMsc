# Combined task: P7

This workspace contains 2 INDEPENDENT subtasks. Complete ALL of them; each is graded separately. Files for different subtasks are co-located in one workspace — identify which files belong to which subtask.



====================================================================
## Subtask 1: pipe3_stream_processing  (pipe, LB90)
====================================================================

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



====================================================================
## Subtask 2: lh5  (lh, LB90)
====================================================================

# LH5: Data Migration

## Goal
Execute a complete 6-step data migration for a IoT sensor telemetry system.
Source data is in `data/old_format/` (csv format).
Target is `data/new_format/` (JSONL format).

## Source Data
- `data/old_format/sensor_readings.csv`: **60 records** (primary table)
- `data/old_format/devices.csv`: **26 records** (reference table)

## Migration Steps (execute in strict order)

   1. **backup**: Create a backup of all source data before any changes
   2. **transform_format**: Convert records from old format to new target format
   3. **validate_checksums**: Verify data integrity via SHA-256 checksums of every record
   4. **load_new_store**: Load transformed records into the new data store
   5. **verify_counts**: Confirm row counts match between source and destination
   6. **update_references**: Rewrite foreign-key references to use new primary keys

## Validation Checkpoints

After **transform_format**:
- `data/transformed/` must contain JSONL files for both tables.
- Row count in `data/transformed/sensor_readings.jsonl` must equal `60`.

After **validate_checksums**:
- `checksums.json` must exist with keys `"source"` and `"transformed"`.
- Each entry must be a valid 64-character hex SHA-256 string.

After **load_new_store**:
- `data/new_format/sensor_readings.jsonl` must exist.
- Row count must equal `60`.
- `data/new_format/devices.jsonl` must exist.

After **verify_counts**:
- `verification_report.json` must exist.
- `counts_match` must be `true`.
- `source_count` must equal `dest_count` must equal `60`.

After **update_references**:
- Every `device_id` in `data/new_format/sensor_readings.jsonl` must exist in `data/new_format/devices.jsonl`.
- No orphaned `device_id` values are permitted.

## Rollback Triggers

If any step fails (returns False or raises an exception), the migration must:
1. Immediately stop execution of further steps.
2. Execute rollback for all successfully completed steps **in reverse order**.

Rollback actions per step:
   - Rollback of `backup`: Remove incomplete backup directory
   - Rollback of `transform_format`: Delete all files in data/transformed/
   - Rollback of `validate_checksums`: Clear checksum manifest (checksums.json)
   - Rollback of `load_new_store`: Truncate data/new_format/ directory
   - Rollback of `verify_counts`: Remove verification report
   - Rollback of `update_references`: Restore original reference mapping from backup

## Required Output Files

- `migration_log.jsonl`: Every step start/complete/fail/rollback event.
- `migration_report.json`: `{"status": "success", "steps_completed": [...], "total_steps": 6, "ts": "<iso>"}`
- `checksums.json`: SHA-256 checksums of source and transformed files.
- `verification_report.json`: `{"source_count": 60, "dest_count": 60, "counts_match": true}`
- `data/backup/`: Copy of original source files.
- `data/new_format/sensor_readings.jsonl`: Migrated primary records.
- `data/new_format/devices.jsonl`: Migrated reference records.


## Deliverables
- Complete implementation of all TODO functions in `migrate.py`.
- Run `python migrate.py` to execute the migration.
- Run `python validate.py` — all checks must pass.
