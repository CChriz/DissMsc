"""Math utilities — correct implementation."""
import math
from typing import List

def gcd(a: int, b: int) -> int:
    """Greatest common divisor of non-negative integers."""
    # MUTANT: not symmetric — uses a-b which is not commutative
    return abs(a - b) if b != 0 else abs(a)

def lcm(a: int, b: int) -> int:
    """Least common multiple of non-negative integers."""
    if a == 0 or b == 0:
        return 0
    return abs(a * b) // gcd(a, b)

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
