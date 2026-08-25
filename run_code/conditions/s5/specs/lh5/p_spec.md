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
- `checksums.json`: SHA-256 checksum manifest.
- `verification_report.json`: `{"source_count": 60, "dest_count": 60, "counts_match": true}`
- `data/backup/`: Copy of original source files.
- `data/new_format/sensor_readings.jsonl`: Migrated primary records.
- `data/new_format/devices.jsonl`: Migrated reference records.


## Deliverables
- Complete implementation of all TODO functions in `migrate.py`.
- Run `python migrate.py` to execute the migration.
- Run `python validate.py` — all checks must pass.
