# MULTI4: Monorepo Dependency Fix (Brief)

Fix 3 dependency issues in a 5-package Python monorepo: a circular import between
`models` and `api`, a stale version pin in `utils`, and a moved function reference
in `worker`. The Planner has mapped the full dependency graph and identified each fix.

Follow the Planner's guidance precisely. Run `pytest tests/` to verify all imports resolve and versions are consistent.
