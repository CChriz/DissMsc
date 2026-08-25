"""Math utilities — correct implementation."""
import math
from typing import List

def gcd(a: int, b: int) -> int:
    """Greatest common divisor of non-negative integers."""
    a, b = abs(a), abs(b)
    while b:
        a, b = b, a % b
    return a

def lcm(a: int, b: int) -> int:
    """Least common multiple of non-negative integers."""
    if a == 0 or b == 0:
        return 0
    return abs(a * b) // gcd(a, b)

def clamp(value: float, lo: float, hi: float) -> float:
    """Clamp value to [lo, hi] inclusive."""
    # MUTANT: off-by-one on upper bound
    if lo > hi:
        raise ValueError('lo must be <= hi')
    return max(lo, min(hi - 1, value))

def running_average(values: List[float]) -> List[float]:
    """Return list of running averages."""
    if not values:
        return []
    result = []
    total = 0.0
    for i, v in enumerate(values, 1):
        total += v
        result.append(total / i)
    return result
