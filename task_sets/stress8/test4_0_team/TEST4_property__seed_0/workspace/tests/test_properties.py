"""Property-based tests for Math Utilities.

Use hypothesis to write property tests for each invariant listed below.
Each @given test must:
  1. Pass on the correct module.py.
  2. FAIL when the corresponding mutant is substituted.
"""
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from module import gcd, lcm, clamp, running_average


# TODO: Write property-based tests below.
# Each invariant in the spec must have a corresponding test function.
# Use @given decorators with hypothesis strategies.

# Invariant GCD_DIVIDES_BOTH: gcd(a,b) divides both a and b
# Formal: a % gcd(a,b) == 0 and b % gcd(a,b) == 0 for all non-negative a, b (not both zero)
# Hint: @given(st.integers(min_value=1, max_value=10**6), st.integers(min_value=1, max_value=10**6))
# def test_gcd_divides_both(...):
#     ...

# Invariant LCM_MULTIPLE: lcm(a,b) is divisible by both a and b
# Formal: lcm(a,b) % a == 0 and lcm(a,b) % b == 0 for positive a, b
# Hint: @given(st.integers(min_value=1, max_value=1000), st.integers(min_value=1, max_value=1000))
# def test_lcm_multiple(...):
#     ...

# Invariant CLAMP_IN_RANGE: clamp output is always within [lo, hi]
# Formal: lo <= clamp(v, lo, hi) <= hi for all v, lo <= hi
# Hint: @given(st.floats(allow_nan=False, allow_infinity=False), st.floats(allow_nan=False, allow_infinity=False), st.floats(allow_nan=False, allow_infinity=False))
# def test_clamp_in_range(...):
#     ...

# Invariant LCM_GCD_IDENTITY: gcd(a,b) * lcm(a,b) == a * b
# Formal: gcd(a, b) * lcm(a, b) == abs(a * b) for positive a, b
# Hint: @given(st.integers(min_value=1, max_value=1000), st.integers(min_value=1, max_value=1000))
# def test_lcm_gcd_identity(...):
#     ...

# Invariant GCD_COMMUTATIVE: gcd is commutative: gcd(a,b) == gcd(b,a)
# Formal: gcd(a, b) == gcd(b, a) for all non-negative a, b
# Hint: @given(st.integers(min_value=0, max_value=10**6), st.integers(min_value=0, max_value=10**6))
# def test_gcd_commutative(...):
#     ...

# Invariant CLAMP_IDEMPOTENT: clamp is idempotent: clamp(clamp(v,lo,hi),lo,hi) == clamp(v,lo,hi)
# Formal: clamp(clamp(v, lo, hi), lo, hi) == clamp(v, lo, hi) for all v, lo <= hi
# Hint: @given(st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6), st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=0), st.floats(allow_nan=False, allow_infinity=False, min_value=0, max_value=1e6))
# def test_clamp_idempotent(...):
#     ...

# Invariant RUNNING_AVG_LENGTH: running_average output has same length as input
# Formal: len(running_average(xs)) == len(xs) for all lists xs
# Hint: @given(st.lists(st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6)))
# def test_running_avg_length(...):
#     ...

