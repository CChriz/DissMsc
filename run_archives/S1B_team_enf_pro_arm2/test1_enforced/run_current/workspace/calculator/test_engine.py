"""Comprehensive pytest tests for the calculator engine.

Covers every documented behavior:
- basic arithmetic, error handling, chaining, memory, precision,
- percent, expression parsing, history, undo, batch, reset,
- type coercion, and thread safety.

The assertions are intentionally exact (no pytest.approx) and assert on
``CalculatorError.code`` so that mutant engines which subtly change behavior
are caught.
"""
from concurrent.futures import ThreadPoolExecutor

import pytest

from calculator.engine import Calculator, CalculatorError


# ---------------------------------------------------------------------------
# A. Basic arithmetic
# ---------------------------------------------------------------------------
def test_add_basic(calc):
    assert calc.add(100, 200) == 300.0


def test_subtract_basic(calc):
    assert calc.subtract(99, 44) == 55.0


def test_multiply_basic(calc):
    assert calc.multiply(12, 12) == 144.0


def test_multiply_zero(calc):
    assert calc.multiply(0, 100) == 0.0


def test_divide_basic(calc):
    assert calc.divide(81, 9) == 9.0


# ---------------------------------------------------------------------------
# B. Error handling
# ---------------------------------------------------------------------------
def test_divide_by_zero(calc):
    with pytest.raises(CalculatorError) as exc:
        calc.divide(10, 0)
    assert exc.value.code == "division_by_zero"


def test_add_overflow_input(calc):
    # 9007199254741991 is itself greater than 2**53, hitting the input check.
    with pytest.raises(CalculatorError) as exc:
        calc.add(9007199254741991, 1)
    assert exc.value.code == "overflow"


def test_add_result_overflow(calc):
    # Both inputs are below the limit, but their sum exceeds 2**53,
    # exercising the *result* overflow check.
    with pytest.raises(CalculatorError) as exc:
        calc.add(2 ** 52 + 1, 2 ** 52 + 1)
    assert exc.value.code == "overflow"


def test_overflow_limit_boundary(calc):
    # Just above 2**52: must NOT raise on the correct engine (limit is 2**53).
    assert calc.add(2 ** 52 + 1, 0) == 4503599627370497.0


def test_sqrt_domain_error(calc):
    with pytest.raises(CalculatorError) as exc:
        calc.sqrt(-4)
    assert exc.value.code == "domain_error"


def test_sqrt_positive(calc):
    assert calc.sqrt(9) == 3.0


def test_invalid_input(calc):
    with pytest.raises(CalculatorError) as exc:
        calc.add("abc", 1)
    assert exc.value.code == "invalid_input"


def test_divide_invalid_input(calc):
    with pytest.raises(CalculatorError) as exc:
        calc.divide("x", "y")
    assert exc.value.code == "invalid_input"


def test_evaluate_invalid_syntax(calc):
    with pytest.raises(CalculatorError) as exc:
        calc.evaluate("2 +")
    assert exc.value.code == "invalid_input"


def test_evaluate_division_by_zero(calc):
    with pytest.raises(CalculatorError) as exc:
        calc.evaluate("1/0")
    assert exc.value.code == "division_by_zero"


# ---------------------------------------------------------------------------
# C. Chaining
# ---------------------------------------------------------------------------
def test_chain_operations(calc):
    assert calc.chain(8).add(2).multiply(3).subtract(6).result() == 24.0


def test_chain_multiply(calc):
    assert calc.chain(5).multiply(4).result() == 20.0


# ---------------------------------------------------------------------------
# D. Memory
# ---------------------------------------------------------------------------
def test_memory_store_recall(calc):
    calc.memory_store(99)
    assert calc.memory_recall() == 99.0


def test_memory_clear(calc):
    calc.memory_store(42)
    calc.memory_clear()
    assert calc.memory_recall() == 0.0


# ---------------------------------------------------------------------------
# E. Precision (exact 6-decimal rounding)
# ---------------------------------------------------------------------------
def test_precision_divide(calc):
    assert calc.divide(1, 9) == 0.111111


def test_precision_rounding(calc):
    assert calc.divide(2, 3) == 0.666667


# ---------------------------------------------------------------------------
# F. Percent
# ---------------------------------------------------------------------------
def test_percent(calc):
    assert calc.percent(80, 25) == 20.0


# ---------------------------------------------------------------------------
# G. Expression parsing
# ---------------------------------------------------------------------------
def test_evaluate_precedence(calc):
    assert calc.evaluate("2 + 3 * 4") == 14.0


def test_evaluate_parentheses(calc):
    assert calc.evaluate("(2 + 3) * 4") == 20.0


# ---------------------------------------------------------------------------
# H. History
# ---------------------------------------------------------------------------
def test_history_format(calc):
    calc.add(1, 2)
    assert calc.history() == ["add(1.0, 2.0) = 3.0"]


def test_history_cap(calc):
    for i in range(11):
        calc.add(i, i)
    hist = calc.history()
    assert len(hist) == 10
    # Oldest entry is dropped; first remaining is the 2nd operation.
    assert hist[0] == "add(1.0, 1.0) = 2.0"
    assert hist[-1] == "add(10.0, 10.0) = 20.0"


# ---------------------------------------------------------------------------
# I. Undo
# ---------------------------------------------------------------------------
def test_undo(calc):
    calc.add(1, 2)
    calc.undo()
    assert calc.history() == []


def test_undo_empty_ok(calc):
    # Undo on empty history must not raise.
    calc.undo()
    assert calc.history() == []


# ---------------------------------------------------------------------------
# J. Batch
# ---------------------------------------------------------------------------
def test_batch(calc):
    assert calc.batch([("add", 1, 2), ("multiply", 3, 4)]) == [3.0, 12.0]


# ---------------------------------------------------------------------------
# K. Reset
# ---------------------------------------------------------------------------
def test_reset(calc):
    calc.memory_store(5)
    calc.add(1, 1)
    calc.reset()
    assert calc.memory_recall() == 0.0
    assert calc.history() == []


# ---------------------------------------------------------------------------
# L. Type coercion
# ---------------------------------------------------------------------------
def test_coercion(calc):
    assert calc.add("5", "3") == 8.0


# ---------------------------------------------------------------------------
# M. Thread safety
# ---------------------------------------------------------------------------
def test_thread_safety(calc):
    def worker():
        calc.add(1, 1)
        return True

    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = [ex.submit(worker) for _ in range(10)]
        for future in futures:
            future.result()  # propagates any exception raised in a thread

    # State remains usable after concurrent access.
    assert calc.add(2, 3) == 5.0
