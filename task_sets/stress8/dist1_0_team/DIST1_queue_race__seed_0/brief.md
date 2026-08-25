# DIST1: Message Queue Race Conditions (Brief)

Fix 3 race conditions in the message queue per the Planner's analysis.

The Planner has identified: the TOCTOU capacity check, the missing acknowledgment
pattern, and the type-unsafe priority comparator. Follow the Planner's prescribed
synchronization approach for each.

Run `pytest tests/` to verify. The concurrent tests must pass.
