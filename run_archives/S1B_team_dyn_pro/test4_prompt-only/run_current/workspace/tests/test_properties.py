"""Property-based tests for Math Utilities.

Use hypothesis to write property tests for each invariant listed below.
Each @given test must:
  1. Pass on the correct module.py.
  2. FAIL when the corresponding mutant is substituted.
"""
import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from module import gcd, lcm, clamp, running_average


# ---------------------------------------------------------------------------
# Invariant GCD_DIVIDES_BOTH:
#   gcd(a,b) divides both a and b
#   Formal: a % gcd(a,b) == 0 and b % gcd(a,b) == 0
#            for all non-negative a, b (not both zero)
# ---------------------------------------------------------------------------
@given(
    st.integers(min_value=1, max_value=10**6),
    st.integers(min_value=1, max_value=10**6),
)
@settings(max_examples=200)
def test_gcd_divides_both(a: int, b: int):
    """gcd(a, b) must evenly divide both a and b."""
    g = gcd(a, b)
    assert a % g == 0, f"gcd({a},{b})={g} does not divide {a}"
    assert b % g == 0, f"gcd({a},{b})={g} does not divide {b}"


# ---------------------------------------------------------------------------
# Invariant LCM_MULTIPLE:
#   lcm(a,b) is divisible by both a and b
#   Formal: lcm(a,b) % a == 0 and lcm(a,b) % b == 0
#            for positive a, b
# ---------------------------------------------------------------------------
@given(
    st.integers(min_value=1, max_value=1000),
    st.integers(min_value=1, max_value=1000),
)
@settings(max_examples=200)
def test_lcm_multiple(a: int, b: int):
    """lcm(a, b) must be a multiple of both a and b."""
    l = lcm(a, b)
    assert l % a == 0, f"lcm({a},{b})={l} is not divisible by {a}"
    assert l % b == 0, f"lcm({a},{b})={l} is not divisible by {b}"


# ---------------------------------------------------------------------------
# Invariant CLAMP_IN_RANGE:
#   clamp output is always within [lo, hi]
#   Formal: lo <= clamp(v, lo, hi) <= hi for all v, lo <= hi
# ---------------------------------------------------------------------------
@given(
    st.floats(allow_nan=False, allow_infinity=False),
    st.floats(allow_nan=False, allow_infinity=False),
    st.floats(allow_nan=False, allow_infinity=False),
)
@settings(max_examples=500)
def test_clamp_in_range(v: float, lo: float, hi: float):
    """clamp(v, lo, hi) must always lie within [lo, hi]."""
    assume(lo <= hi)
    result = clamp(v, lo, hi)
    assert lo <= result <= hi, (
        f"clamp({v}, {lo}, {hi})={result} is outside [{lo}, {hi}]"
    )


# ---------------------------------------------------------------------------
# Invariant LCM_GCD_IDENTITY:
#   gcd(a,b) * lcm(a,b) == a * b
#   Formal: gcd(a, b) * lcm(a, b) == abs(a * b) for positive a, b
# ---------------------------------------------------------------------------
@given(
    st.integers(min_value=1, max_value=1000),
    st.integers(min_value=1, max_value=1000),
)
@settings(max_examples=200)
def test_lcm_gcd_identity(a: int, b: int):
    """gcd(a, b) * lcm(a, b) must equal a * b (absolute)."""
    g = gcd(a, b)
    l = lcm(a, b)
    assert g * l == a * b, (
        f"gcd({a},{b})={g} * lcm({a},{b})={l} != {a} * {b} = {a * b}"
    )


# ---------------------------------------------------------------------------
# Invariant GCD_COMMUTATIVE:
#   gcd is commutative: gcd(a,b) == gcd(b,a)
#   Formal: gcd(a, b) == gcd(b, a) for all non-negative a, b
# ---------------------------------------------------------------------------
@given(
    st.integers(min_value=0, max_value=10**6),
    st.integers(min_value=0, max_value=10**6),
)
@settings(max_examples=200)
def test_gcd_commutative(a: int, b: int):
    """gcd(a, b) must equal gcd(b, a)."""
    assert gcd(a, b) == gcd(b, a), (
        f"gcd({a},{b})={gcd(a,b)} != gcd({b},{a})={gcd(b,a)}"
    )


# ---------------------------------------------------------------------------
# Invariant CLAMP_IDEMPOTENT:
#   clamp is idempotent: clamp(clamp(v,lo,hi),lo,hi) == clamp(v,lo,hi)
#   Formal: clamp(clamp(v, lo, hi), lo, hi) == clamp(v, lo, hi)
#            for all v, lo <= hi
# ---------------------------------------------------------------------------
@given(
    st.floats(allow_nan=False, allow_infinity=False,
              min_value=-1e6, max_value=1e6),
    st.floats(allow_nan=False, allow_infinity=False,
              min_value=-1e6, max_value=0),
    st.floats(allow_nan=False, allow_infinity=False,
              min_value=0, max_value=1e6),
)
@settings(max_examples=500)
def test_clamp_idempotent(v: float, lo: float, hi: float):
    """Applying clamp twice must give the same result as applying once."""
    assume(lo <= hi)
    once = clamp(v, lo, hi)
    twice = clamp(once, lo, hi)
    assert once == twice, (
        f"clamp(clamp({v},{lo},{hi})={once},{lo},{hi})={twice} != {once}"
    )


# ---------------------------------------------------------------------------
# Invariant RUNNING_AVG_LENGTH:
#   running_average output has same length as input
#   Formal: len(running_average(xs)) == len(xs) for all lists xs
# ---------------------------------------------------------------------------
@given(
    st.lists(st.floats(allow_nan=False, allow_infinity=False,
                       min_value=-1e6, max_value=1e6))
)
@settings(max_examples=200)
def test_running_avg_length(xs: list):
    """running_average(xs) must have the same number of elements as xs."""
    result = running_average(xs)
    assert len(result) == len(xs), (
        f"len(running_average({xs}))={len(result)} != len({xs})={len(xs)}"
    )
