# TEST4: Property-Based Tests from Spec Invariants

## Context

A module is provided in `module.py` with a correct implementation.
The module has been verified against its mathematical specification,
but we need **property-based tests** to guard against future regressions.

## Your Task

Write property-based tests in `tests/test_properties.py` using the
**hypothesis** library. Each invariant listed in the spec must have a
corresponding test function decorated with `@given`.

## Requirements

- Use `hypothesis` with `@given` decorators (not just example-based tests).
- Each invariant must have at least one dedicated test function.
- All tests must pass on the provided `module.py`.
- Each test must be sensitive enough to catch a mutant that violates its invariant.
- Test functions must begin with `test_`.

## Running Tests

```bash
pip install hypothesis pytest
python -m pytest tests/test_properties.py -v
```

## Note

The exact invariants vary per seed — see the generated spec.md produced by the
parameterized generator for seed-specific invariants.
