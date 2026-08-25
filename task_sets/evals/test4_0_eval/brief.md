# TEST4: Property-Based Tests (Brief)

The module needs property-based tests to verify its correctness guarantees.

Write `@given` hypothesis tests in `tests/test_properties.py` covering each
invariant listed in the spec. The Planner has the full invariant list.

- File to write: `tests/test_properties.py`
- Run with: `python -m pytest tests/test_properties.py`
- Use `hypothesis` library with `@given` decorators.
- Each invariant must have at least one dedicated test function.
- All tests must pass on the provided `module.py`.
