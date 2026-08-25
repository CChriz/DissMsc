"""Property-based tests for Math Utilities.

Use hypothesis to write property tests for each invariant listed below.
Each @given test must:
  1. Pass on the correct module.py.
  2. FAIL when the corresponding mutant is substituted.
"""
from hypothesis import given, assume, strategies as st
from module import gcd, lcm, clamp, running_average


# ============================================================
# Invariant GCD_DIVIDES_BOTH: gcd(a,b) divides both a and b
# ============================================================
@given(st.integers(min_value=1, max_value=10**6), st.integers(min_value=1, max_value=10**6))
def test_gcd_divides_both(a, b):
    g = gcd(a, b)
    assert a % g == 0 and b % g == 0


# ============================================================
# Invariant LCM_MULTIPLE: lcm(a,b) is divisible by both a and b
# ============================================================
@given(st.integers(min_value=1, max_value=1000), st.integers(min_value=1, max_value=1000))
def test_lcm_multiple(a, b):
    L = lcm(a, b)
    assert L % a == 0 and L % b == 0


# ============================================================
# Invariant CLAMP_IN_RANGE: clamp output is always within [lo, hi]
# ============================================================
@given(
    st.floats(allow_nan=False, allow_infinity=False),
    st.floats(allow_nan=False, allow_infinity=False),
    st.floats(allow_nan=False, allow_infinity=False),
)
def test_clamp_in_range(v, lo, hi):
    assume(lo <= hi)
    result = clamp(v, lo, hi)
    assert lo <= result <= hi


# ============================================================
# Invariant LCM_GCD_IDENTITY: gcd(a,b) * lcm(a,b) == a * b
# ============================================================
@given(st.integers(min_value=1, max_value=1000), st.integers(min_value=1, max_value=1000))
def test_lcm_gcd_identity(a, b):
    assert gcd(a, b) * lcm(a, b) == a * b


# ============================================================
# Invariant GCD_COMMUTATIVE: gcd is commutative
# ============================================================
@given(st.integers(min_value=0, max_value=10**6), st.integers(min_value=0, max_value=10**6))
def test_gcd_commutative(a, b):
    assume(a != 0 or b != 0)
    assert gcd(a, b) == gcd(b, a)


# ============================================================
# Invariant CLAMP_IDEMPOTENT: clamp is idempotent
# ============================================================
@given(
    st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6),
    st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=0),
    st.floats(allow_nan=False, allow_infinity=False, min_value=0, max_value=1e6),
)
def test_clamp_idempotent(v, lo, hi):
    assert clamp(clamp(v, lo, hi), lo, hi) == clamp(v, lo, hi)


# ============================================================
# Invariant RUNNING_AVG_LENGTH: running_average output has same length as input
# ============================================================
@given(st.lists(st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6)))
def test_running_avg_length(xs):
    assert len(running_average(xs)) == len(xs)
