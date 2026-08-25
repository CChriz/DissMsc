"""Property-based tests for Math Utilities.

Use hypothesis to write property tests for each invariant listed below.
Each @given test must:
  1. Pass on the correct module.py.
  2. FAIL when the corresponding mutant is substituted.
"""
from hypothesis import given, assume, strategies as st

from module import gcd, lcm, clamp, running_average


# Invariant 1 (GCD_DIVIDES_BOTH): gcd(a,b) 整除 a 且整除 b
@given(
    st.integers(min_value=1, max_value=10**6),
    st.integers(min_value=1, max_value=10**6),
)
def test_gcd_divides_both(a, b):
    g = gcd(a, b)
    assert a % g == 0
    assert b % g == 0


# Invariant 2 (LCM_MULTIPLE): lcm(a,b) 是 a 和 b 的公倍数
@given(
    st.integers(min_value=1, max_value=1000),
    st.integers(min_value=1, max_value=1000),
)
def test_lcm_is_multiple_of_both(a, b):
    m = lcm(a, b)
    assert m % a == 0
    assert m % b == 0


# Invariant 3 (CLAMP_IN_RANGE): lo <= clamp(v,lo,hi) <= hi（前置 lo<=hi）
# 额外断言精确语义：result 必须等于 max(lo, min(hi, v))。
# 用于捕获 CLAMP_IN_RANGE mutant（min(hi-1, value) 的 off-by-one，
# 其输出虽仍在 [lo,hi] 内，但当 v>=hi 时返回 hi-1 而非 hi）。
@given(
    st.floats(allow_nan=False, allow_infinity=False),
    st.floats(allow_nan=False, allow_infinity=False),
    st.floats(allow_nan=False, allow_infinity=False),
)
def test_clamp_in_range(v, lo, hi):
    assume(lo <= hi)
    result = clamp(v, lo, hi)
    assert lo <= result <= hi
    assert result == max(lo, min(hi, v))


# Invariant 4 (LCM_GCD_IDENTITY): gcd(a,b) * lcm(a,b) == a * b
@given(
    st.integers(min_value=1, max_value=1000),
    st.integers(min_value=1, max_value=1000),
)
def test_gcd_lcm_identity(a, b):
    assert gcd(a, b) * lcm(a, b) == a * b


# Invariant 5 (GCD_COMMUTATIVE): gcd(a,b) == gcd(b,a)（含 0）
# 额外断言整除性：用于捕获"对称但错误"的 GCD_COMMUTATIVE mutant
# （abs(a-b) 本身满足交换律，但通常不整除 a、b）。
@given(
    st.integers(min_value=0, max_value=10**6),
    st.integers(min_value=0, max_value=10**6),
)
def test_gcd_commutative(a, b):
    assert gcd(a, b) == gcd(b, a)          # 交换律（spec 明示的不变量）
    assume(a != 0 or b != 0)               # 排除 g == 0，避免下方取模除零
    g = gcd(a, b)
    assert a % g == 0 and b % g == 0       # 整除性：捕获"对称但错误"的突变


# Invariant 6 (CLAMP_IDEMPOTENT): clamp(clamp(v,lo,hi),lo,hi) == clamp(v,lo,hi)
# 注意：hint 已用 lo∈[-1e6,0]、hi∈[0,1e6] 保证 lo<=hi
@given(
    st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6),
    st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=0),
    st.floats(allow_nan=False, allow_infinity=False, min_value=0, max_value=1e6),
)
def test_clamp_idempotent(v, lo, hi):
    assert clamp(clamp(v, lo, hi), lo, hi) == clamp(v, lo, hi)


# Invariant 7 (RUNNING_AVG_LENGTH): len(running_average(xs)) == len(xs)
@given(
    st.lists(st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6))
)
def test_running_average_length(xs):
    assert len(running_average(xs)) == len(xs)
