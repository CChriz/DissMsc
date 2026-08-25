# Combined task: P7

This workspace contains 2 INDEPENDENT subtasks. Complete ALL of them; each is graded separately. Files for different subtasks are co-located in one workspace — identify which files belong to which subtask.



====================================================================
## Subtask 1: pipe3_stream_processing  (pipe, LB90)
====================================================================

# PIPE3: Stream Processing Pipeline (Brief)

Fix 3 serialization mismatch bugs across a producer-processor-sink pipeline.
Each component makes different assumptions about datetime format, message structure,
and character encoding. The Planner has traced the data flow to identify each mismatch.

Follow the Planner's guidance precisely. Run `pytest tests/` to verify the full pipeline works.



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
