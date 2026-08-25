            # TEST4: Property-Based Tests from Spec Invariants

            ## Context

            The `math_utils` module provides mathematical functions with algebraic properties.
            It exposes the following functions: `gcd`, `lcm`, `clamp`, `running_average`.

            A correct implementation is provided in `module.py`.
            The module has been verified against its mathematical specification,
            but we need **property-based tests** to guard against future regressions.

            ## Your Task

            Write property-based tests in `tests/test_properties.py` using the
            **hypothesis** library. Each invariant below must have a corresponding
            test function decorated with `@given`.

            ## Invariants to Test (Seed 0)

            ### Invariant 1: gcd(a,b) divides both a and b (`GCD_DIVIDES_BOTH`)

**Formal property**: a % gcd(a,b) == 0 and b % gcd(a,b) == 0 for all non-negative a, b (not both zero)

**Hypothesis strategy hint**: `@given(st.integers(min_value=1, max_value=10**6), st.integers(min_value=1, max_value=10**6))`

**What to check**: gcd(a,b) divides both a and b

### Invariant 2: lcm(a,b) is divisible by both a and b (`LCM_MULTIPLE`)

**Formal property**: lcm(a,b) % a == 0 and lcm(a,b) % b == 0 for positive a, b

**Hypothesis strategy hint**: `@given(st.integers(min_value=1, max_value=1000), st.integers(min_value=1, max_value=1000))`

**What to check**: lcm(a,b) % a == 0 and lcm(a,b) % b == 0

### Invariant 3: clamp output is always within [lo, hi] (`CLAMP_IN_RANGE`)

**Formal property**: lo <= clamp(v, lo, hi) <= hi for all v, lo <= hi

**Hypothesis strategy hint**: `@given(st.floats(allow_nan=False, allow_infinity=False), st.floats(allow_nan=False, allow_infinity=False), st.floats(allow_nan=False, allow_infinity=False))`

**What to check**: lo <= clamp(v, lo, hi) <= hi

### Invariant 4: gcd(a,b) * lcm(a,b) == a * b (`LCM_GCD_IDENTITY`)

**Formal property**: gcd(a, b) * lcm(a, b) == abs(a * b) for positive a, b

**Hypothesis strategy hint**: `@given(st.integers(min_value=1, max_value=1000), st.integers(min_value=1, max_value=1000))`

**What to check**: gcd(a,b) * lcm(a,b) == a*b

### Invariant 5: gcd is commutative: gcd(a,b) == gcd(b,a) (`GCD_COMMUTATIVE`)

**Formal property**: gcd(a, b) == gcd(b, a) for all non-negative a, b

**Hypothesis strategy hint**: `@given(st.integers(min_value=0, max_value=10**6), st.integers(min_value=0, max_value=10**6))`

**What to check**: gcd(a,b) == gcd(b,a)

### Invariant 6: clamp is idempotent: clamp(clamp(v,lo,hi),lo,hi) == clamp(v,lo,hi) (`CLAMP_IDEMPOTENT`)

**Formal property**: clamp(clamp(v, lo, hi), lo, hi) == clamp(v, lo, hi) for all v, lo <= hi

**Hypothesis strategy hint**: `@given(st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6), st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=0), st.floats(allow_nan=False, allow_infinity=False, min_value=0, max_value=1e6))`

**What to check**: clamp(clamp(v,lo,hi),lo,hi) == clamp(v,lo,hi)

### Invariant 7: running_average output has same length as input (`RUNNING_AVG_LENGTH`)

**Formal property**: len(running_average(xs)) == len(xs) for all lists xs

**Hypothesis strategy hint**: `@given(st.lists(st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6)))`

**What to check**: len(running_average(xs)) == len(xs)


            ## Requirements

            - Use `hypothesis` with `@given` decorators (not just example-based tests).
            - Each of the 7 invariants must have at least one dedicated test function.
            - All tests must pass on the provided `module.py`.
            - Each test must be sensitive enough to catch the corresponding mutant.
            - Test functions must begin with `test_`.

            ## Running Tests

            ```bash
            pip install hypothesis pytest
            python -m pytest tests/test_properties.py -v
            ```

            ## Deliverables

            - `tests/test_properties.py` with at least 7 `@given` test functions.
            - Tests must run cleanly: `python -m pytest tests/test_properties.py`.

            ## Grading

            - **Check 1**: `tests/test_properties.py` exists.
            - **Check 2**: File imports from `hypothesis` (property-based approach used).
            - **Checks 3-9**: Each invariant has a corresponding test that catches its mutant.
            - **Check 10**: All tests pass on correct `module.py`.
            - **Check 11**: Test function count >= 7.
            - **Check 12**: At least 6 mutants are caught overall.
