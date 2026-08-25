# PIPE3: Stream Processing Pipeline (Brief)

Fix 3 serialization mismatch bugs across a producer-processor-sink pipeline.
Each component makes different assumptions about datetime format, message structure,
and character encoding. The Planner has traced the data flow to identify each mismatch.

Follow the Planner's guidance precisely. Run `pytest tests/` to verify the full pipeline works.
