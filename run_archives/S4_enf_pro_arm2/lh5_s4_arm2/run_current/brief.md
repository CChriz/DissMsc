# LH5: Data Migration (Brief)

Data needs to be migrated to the new format. Execute the migration.

- Source: `data/old_format/` (csv)
- Target: `data/new_format/` (jsonl)
- Domain: IoT sensor telemetry

Run: `python migrate.py`
Validate: `python validate.py`

The Planner has the full 6-step migration plan with validation checkpoints and rollback triggers.
