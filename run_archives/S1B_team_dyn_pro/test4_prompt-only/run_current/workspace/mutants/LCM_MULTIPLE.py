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
    # MUTANT: returns a+b — not necessarily a multiple of either
    return abs(a + b)

def clamp(value: float, lo: float, hi: float) -> float:
    """Clamp value to [lo, hi] inclusive."""
    if lo > hi:
        raise ValueError('lo must be <= hi')
    return max(lo, min(hi, value))

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
