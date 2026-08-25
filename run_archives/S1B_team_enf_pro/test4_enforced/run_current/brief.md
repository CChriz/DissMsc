          # TEST4: Property-Based Tests (Brief)

          The `math_utils` module needs property-based tests to verify its correctness guarantees.

          Write `@given` hypothesis tests in `tests/test_properties.py` covering these invariants:
            - gcd(a,b) divides both a and b
- lcm(a,b) is divisible by both a and b
- clamp output is always within [lo, hi]
- gcd(a,b) * lcm(a,b) == a * b
- gcd is commutative: gcd(a,b) == gcd(b,a)
- clamp is idempotent: clamp(clamp(v,lo,hi),lo,hi) == clamp(v,lo,hi)
- running_average output has same length as input

          - Run with: `python -m pytest tests/test_properties.py`
          - Use `hypothesis` library with `@given` decorators.
          - Each invariant must have at least one test function.
          - All tests must pass on the provided `module.py`.
