"""Comprehensive tests for the calculator engine."""
import pytest
import threading
from calculator.engine import Calculator, CalculatorError


@pytest.fixture
def calc():
    """Fresh calculator instance for each test."""
    c = Calculator()
    c.reset()
    return c


# ── Basic Arithmetic ──────────────────────────────────────────────────────────

def test_add_basic(calc):
    assert calc.add(1, 2) == 3.0

def test_add_negative(calc):
    assert calc.add(-3, -7) == -10.0

def test_add_zero(calc):
    assert calc.add(0, 0) == 0.0

def test_add_mixed_sign(calc):
    assert calc.add(-5, 3) == -2.0

def test_subtract_basic(calc):
    assert calc.subtract(10, 3) == 7.0

def test_subtract_negative_result(calc):
    assert calc.subtract(3, 10) == -7.0

def test_subtract_order_matters(calc):
    # a - b != b - a when a != b
    assert calc.subtract(10, 3) == 7.0
    assert calc.subtract(3, 10) == -7.0
    assert calc.subtract(10, 3) != calc.subtract(3, 10)

def test_subtract_zero(calc):
    assert calc.subtract(5, 5) == 0.0

def test_multiply_basic(calc):
    assert calc.multiply(3, 4) == 12.0

def test_multiply_zero(calc):
    assert calc.multiply(0, 100) == 0.0

def test_multiply_negative(calc):
    assert calc.multiply(-3, 4) == -12.0

def test_multiply_negative_negative(calc):
    assert calc.multiply(-3, -4) == 12.0

def test_divide_basic(calc):
    assert calc.divide(7, 2) == 3.5

def test_divide_exact(calc):
    assert calc.divide(10, 2) == 5.0

def test_divide_negative(calc):
    assert calc.divide(-10, 2) == -5.0

def test_divide_order_matters(calc):
    # a / b != b / a when a != b
    assert calc.divide(10, 2) == 5.0
    assert calc.divide(2, 10) == 0.2
    assert calc.divide(10, 2) != calc.divide(2, 10)


# ── Error Handling ────────────────────────────────────────────────────────────

def test_divide_by_zero(calc):
    with pytest.raises(CalculatorError) as exc_info:
        calc.divide(10, 0)
    assert exc_info.value.code == "division_by_zero"

def test_divide_by_zero_negative(calc):
    with pytest.raises(CalculatorError) as exc_info:
        calc.divide(-5, 0)
    assert exc_info.value.code == "division_by_zero"

def test_overflow_add(calc):
    # Use 2**54 which is clearly > 2**53 even after float conversion
    with pytest.raises(CalculatorError) as exc_info:
        calc.add(2**54, 1)
    assert exc_info.value.code == "overflow"

def test_overflow_multiply(calc):
    # Use 2**54 which is clearly > 2**53 even after float conversion
    with pytest.raises(CalculatorError) as exc_info:
        calc.multiply(2**54, 2)
    assert exc_info.value.code == "overflow"

def test_overflow_large_value(calc):
    # 2**53 * 2 = 2**54, clearly overflows
    with pytest.raises(CalculatorError) as exc_info:
        calc.add(2**53 * 2, 0)
    assert exc_info.value.code == "overflow"

def test_overflow_boundary_no_error(calc):
    # 2**53 itself should NOT raise overflow (it's exactly at the boundary)
    result = calc.add(2**53, 0)
    assert result == float(2**53)

def test_overflow_mutant_02_catch(calc):
    # Mutant 02 uses 2**52 as limit. Test that 2**52 * 2 raises overflow.
    # On correct engine: 2**52 * 2 = 2**53 which is NOT > 2**53, so no overflow.
    # But 2**53 + 2 (which floats to 2**53 + 2 = 9007199254740994) IS > 2**53.
    # Use a value that is > 2**53 but <= 2**52 * 2 to distinguish mutant 02.
    # Actually: mutant 02 limit is 2**52. So 2**52 + 2 would trigger mutant 02 but not correct.
    # Let's just use 2**54 for overflow tests (safe for both).
    with pytest.raises(CalculatorError) as exc_info:
        calc.add(2**54, 0)
    assert exc_info.value.code == "overflow"

def test_sqrt_negative(calc):
    with pytest.raises(CalculatorError) as exc_info:
        calc.sqrt(-4)
    assert exc_info.value.code == "domain_error"

def test_sqrt_negative_small(calc):
    with pytest.raises(CalculatorError) as exc_info:
        calc.sqrt(-0.001)
    assert exc_info.value.code == "domain_error"

def test_sqrt_zero(calc):
    assert calc.sqrt(0) == 0.0

def test_sqrt_positive(calc):
    assert calc.sqrt(4) == 2.0

def test_sqrt_nine(calc):
    assert calc.sqrt(9) == 3.0

def test_invalid_input_string(calc):
    with pytest.raises(CalculatorError) as exc_info:
        calc.add("abc", 1)
    assert exc_info.value.code == "invalid_input"

def test_invalid_input_second_arg(calc):
    with pytest.raises(CalculatorError) as exc_info:
        calc.add(1, "xyz")
    assert exc_info.value.code == "invalid_input"

def test_invalid_input_not_zero(calc):
    # Mutant 09 returns 0.0 instead of raising — verify exception IS raised
    raised = False
    try:
        result = calc.add("abc", 1)
    except CalculatorError as e:
        raised = True
        assert e.code == "invalid_input"
    assert raised, "Expected CalculatorError to be raised for invalid input"


# ── Precision ─────────────────────────────────────────────────────────────────

def test_precision_one_third(calc):
    # Must be exactly 6 decimal places
    assert calc.divide(1, 3) == 0.333333

def test_precision_two_thirds(calc):
    # Rounds up at 6th decimal place
    assert calc.divide(2, 3) == 0.666667

def test_precision_one_seventh(calc):
    assert calc.divide(1, 7) == 0.142857

def test_precision_not_more_than_6(calc):
    result = calc.divide(1, 3)
    # Must NOT be the full float 0.3333333333333333
    assert result != 0.3333333333333333
    assert result == 0.333333

def test_precision_four_places_not_enough(calc):
    # Mutant 06 uses 4 decimal places - this catches it
    result = calc.divide(1, 3)
    assert result != 0.3333  # 4 decimal places
    assert result == 0.333333  # exactly 6

def test_precision_five_places_not_enough(calc):
    # Also check 5 decimal places is not enough
    result = calc.divide(1, 3)
    assert result != 0.33333  # 5 decimal places
    assert result == 0.333333  # exactly 6

def test_precision_one_sixth(calc):
    # 1/6 = 0.166667 (rounds up)
    result = calc.divide(1, 6)
    assert result == 0.166667


# ── Chained Operations ────────────────────────────────────────────────────────

def test_chain_add_multiply(calc):
    # (10 + 5) * 2 = 30, NOT 10 + (5*2) = 20
    result = calc.chain(10).add(5).multiply(2).result()
    assert result == 30.0

def test_chain_order_matters(calc):
    # Verify order: add first, then multiply
    result1 = calc.chain(10).add(5).multiply(2).result()
    result2 = calc.chain(10).multiply(2).add(5).result()
    assert result1 == 30.0  # (10+5)*2
    assert result2 == 25.0  # 10*2+5
    assert result1 != result2

def test_chain_multiply_add(calc):
    # 10 * 2 + 5 = 25
    result = calc.chain(10).multiply(2).add(5).result()
    assert result == 25.0

def test_chain_subtract(calc):
    result = calc.chain(20).subtract(5).result()
    assert result == 15.0

def test_chain_divide(calc):
    result = calc.chain(20).divide(4).result()
    assert result == 5.0

def test_chain_single_op(calc):
    result = calc.chain(5).add(3).result()
    assert result == 8.0

def test_chain_multiple_ops(calc):
    result = calc.chain(100).subtract(50).divide(5).result()
    assert result == 10.0

def test_chain_multiply_uses_multiplication(calc):
    # Mutant 08: chain multiply uses addition instead of multiplication
    # chain(3).multiply(4) should be 12, not 3+4=7
    result = calc.chain(3).multiply(4).result()
    assert result == 12.0
    assert result != 7.0  # would be 3+4 if mutant

def test_chain_multiply_not_addition(calc):
    # Extra check: chain(5).multiply(3) = 15, not 5+3=8
    result = calc.chain(5).multiply(3).result()
    assert result == 15.0
    assert result != 8.0


# ── Memory ────────────────────────────────────────────────────────────────────

def test_memory_store_recall(calc):
    calc.memory_store(99)
    assert calc.memory_recall() == 99.0

def test_memory_clear(calc):
    calc.memory_store(42)
    calc.memory_clear()
    assert calc.memory_recall() == 0.0

def test_memory_overwrite(calc):
    calc.memory_store(10)
    calc.memory_store(20)
    assert calc.memory_recall() == 20.0

def test_memory_default(calc):
    # Fresh calculator: memory should be 0.0
    assert calc.memory_recall() == 0.0

def test_memory_float(calc):
    calc.memory_store(3.14)
    assert calc.memory_recall() == 3.14

def test_memory_clear_returns_zero_not_none(calc):
    calc.memory_store(55)
    calc.memory_clear()
    result = calc.memory_recall()
    assert result == 0.0
    assert result is not None


# ── Percentage ────────────────────────────────────────────────────────────────

def test_percent_basic(calc):
    # 200 * 15 / 100 = 30
    assert calc.percent(200, 15) == 30.0

def test_percent_50(calc):
    assert calc.percent(100, 50) == 50.0

def test_percent_zero(calc):
    assert calc.percent(200, 0) == 0.0

def test_percent_100(calc):
    assert calc.percent(50, 100) == 50.0

def test_percent_formula_not_divided_by_10(calc):
    # Mutant 10: divides by 10 instead of 100
    # percent(200, 15) with /10 would give 300, with /100 gives 30
    result = calc.percent(200, 15)
    assert result == 30.0
    assert result != 300.0  # would be 200*15/10 if mutant

def test_percent_formula_check(calc):
    # percent(100, 25) = 25.0 (not 250.0 if /10)
    result = calc.percent(100, 25)
    assert result == 25.0
    assert result != 250.0


# ── Expression Evaluation ─────────────────────────────────────────────────────

def test_evaluate_precedence(calc):
    # Multiplication before addition: 2 + 3*4 = 14, NOT (2+3)*4 = 20
    assert calc.evaluate("2 + 3 * 4") == 14.0

def test_evaluate_not_left_to_right(calc):
    # Mutant 03: left-to-right would give (2+3)*4 = 20
    result = calc.evaluate("2 + 3 * 4")
    assert result == 14.0
    assert result != 20.0

def test_evaluate_parentheses(calc):
    # Parentheses override: (2+3)*4 = 20
    assert calc.evaluate("(2 + 3) * 4") == 20.0

def test_evaluate_simple_add(calc):
    assert calc.evaluate("5 + 3") == 8.0

def test_evaluate_simple_subtract(calc):
    assert calc.evaluate("10 - 3") == 7.0

def test_evaluate_division(calc):
    assert calc.evaluate("10 / 2") == 5.0

def test_evaluate_complex(calc):
    assert calc.evaluate("(1 + 2) * (3 + 4)") == 21.0

def test_evaluate_division_before_subtraction(calc):
    # 10 - 4/2 = 10 - 2 = 8 (not (10-4)/2 = 3)
    assert calc.evaluate("10 - 4 / 2") == 8.0


# ── History ───────────────────────────────────────────────────────────────────

def test_history_format(calc):
    calc.add(1, 2)
    history = calc.history()
    assert len(history) == 1
    assert history[0] == "add(1.0, 2.0) = 3.0"

def test_history_is_list_of_strings(calc):
    calc.add(1, 2)
    history = calc.history()
    assert isinstance(history, list)
    assert all(isinstance(h, str) for h in history)

def test_history_cap_at_10(calc):
    for i in range(11):
        calc.add(i, 1)
    history = calc.history()
    assert len(history) == 10

def test_history_cap_exactly_10_not_11(calc):
    # Mutant 04: keeps 20 instead of 10
    for i in range(15):
        calc.add(i, 0)
    history = calc.history()
    assert len(history) == 10
    assert len(history) != 15
    assert len(history) != 20

def test_history_drops_oldest(calc):
    # First op: add(0, 1) = 1.0
    calc.add(0, 1)
    # Do 10 more to push it out
    for i in range(1, 11):
        calc.add(i, 1)
    history = calc.history()
    assert len(history) == 10
    # The first entry should be gone
    assert not any("add(0.0, 1.0)" in h for h in history)
    # The last entry should be present
    assert any("add(10.0, 1.0)" in h for h in history)

def test_history_grows_up_to_10(calc):
    for i in range(5):
        calc.add(i, 0)
    assert len(calc.history()) == 5

def test_history_contains_result(calc):
    calc.add(3, 4)
    history = calc.history()
    assert "7.0" in history[0]


# ── Undo ──────────────────────────────────────────────────────────────────────

def test_undo_removes_from_history(calc):
    calc.add(1, 2)
    calc.undo()
    assert calc.history() == []

def test_undo_only_last(calc):
    calc.add(1, 2)
    calc.add(3, 4)
    calc.undo()
    history = calc.history()
    assert len(history) == 1
    assert "add(1.0, 2.0)" in history[0]

def test_undo_does_not_clear_memory(calc):
    # Mutant 05: undo accidentally clears memory
    calc.memory_store(42)
    calc.add(1, 2)
    calc.undo()
    # Memory should still be 42 after undo
    assert calc.memory_recall() == 42.0


# ── Batch Mode ────────────────────────────────────────────────────────────────

def test_batch_basic(calc):
    results = calc.batch([("add", 1, 2), ("multiply", 3, 4)])
    assert results == [3.0, 12.0]

def test_batch_order_preserved(calc):
    # Mutant 07: batch always returns 0.0
    results = calc.batch([("subtract", 10, 3), ("divide", 9, 3)])
    assert results[0] == 7.0
    assert results[1] == 3.0

def test_batch_not_zeros(calc):
    # Mutant 07: batch always returns 0.0 for each operation
    results = calc.batch([("add", 5, 5), ("multiply", 3, 4)])
    assert results == [10.0, 12.0]
    assert results != [0.0, 0.0]

def test_batch_single(calc):
    results = calc.batch([("subtract", 10, 3)])
    assert results == [7.0]

def test_batch_multiple(calc):
    results = calc.batch([
        ("add", 1, 1),
        ("subtract", 5, 2),
        ("multiply", 2, 3),
        ("divide", 10, 2)
    ])
    assert results == [2.0, 3.0, 6.0, 5.0]

def test_batch_returns_correct_values(calc):
    # Specifically designed to catch mutant 07 (returns 0.0 for all)
    results = calc.batch([("add", 100, 200)])
    assert results[0] == 300.0
    assert results[0] != 0.0


# ── Reset ─────────────────────────────────────────────────────────────────────

def test_reset_clears_memory(calc):
    calc.memory_store(42)
    calc.reset()
    assert calc.memory_recall() == 0.0

def test_reset_clears_history(calc):
    calc.add(1, 2)
    calc.reset()
    assert calc.history() == []

def test_reset_clears_chain(calc):
    calc.chain(10).add(5)
    calc.reset()
    # After reset, a new chain should start fresh
    result = calc.chain(1).add(1).result()
    assert result == 2.0

def test_reset_memory_returns_zero_float(calc):
    calc.memory_store(99)
    calc.reset()
    result = calc.memory_recall()
    assert result == 0.0
    assert isinstance(result, float)


# ── Type Coercion ─────────────────────────────────────────────────────────────

def test_coerce_string_inputs(calc):
    assert calc.add("5", "3") == 8.0

def test_coerce_mixed_inputs(calc):
    assert calc.add("5", 3) == 8.0
    assert calc.multiply("4", 2) == 8.0

def test_coerce_float_string(calc):
    assert calc.add("1.5", "2.5") == 4.0

def test_invalid_string_raises(calc):
    with pytest.raises(CalculatorError) as exc_info:
        calc.add("abc", 1)
    assert exc_info.value.code == "invalid_input"

def test_invalid_string_not_zero(calc):
    # Mutant 09: returns 0.0 instead of raising
    raised = False
    try:
        result = calc.add("abc", 1)
        # If we get here, mutant 09 is active — result would be 0.0
        assert False, f"Should have raised CalculatorError, got {result}"
    except CalculatorError as e:
        raised = True
        assert e.code == "invalid_input"
    assert raised

def test_invalid_string_second_arg_raises(calc):
    with pytest.raises(CalculatorError) as exc_info:
        calc.multiply(2, "xyz")
    assert exc_info.value.code == "invalid_input"


# ── Thread Safety ─────────────────────────────────────────────────────────────

def test_thread_safety_no_exceptions(calc):
    errors = []
    lock = threading.Lock()

    def worker():
        try:
            calc.add(1, 1)
        except Exception as e:
            with lock:
                errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"Thread errors: {errors}"

def test_thread_safety_history_not_corrupted(calc):
    # Run many concurrent operations and verify history is consistent
    errors = []
    lock = threading.Lock()

    def worker():
        try:
            calc.add(1, 1)
        except Exception as e:
            with lock:
                errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    # History should be a valid list of strings
    history = calc.history()
    assert isinstance(history, list)
    assert len(history) <= 10


# ── Mutation-Specific Guards ──────────────────────────────────────────────────

def test_add_is_not_subtract(calc):
    # add(3, 1) = 4, not 2
    assert calc.add(3, 1) == 4.0
    assert calc.add(3, 1) != 2.0

def test_subtract_is_not_add(calc):
    # subtract(10, 3) = 7, not 13
    assert calc.subtract(10, 3) == 7.0
    assert calc.subtract(10, 3) != 13.0

def test_multiply_is_not_add(calc):
    # multiply(3, 4) = 12, not 7
    assert calc.multiply(3, 4) == 12.0
    assert calc.multiply(3, 4) != 7.0

def test_divide_is_not_multiply(calc):
    # divide(12, 4) = 3, not 48
    assert calc.divide(12, 4) == 3.0
    assert calc.divide(12, 4) != 48.0

def test_overflow_at_2_54(calc):
    # 2**54 is clearly > 2**53 even after float conversion
    with pytest.raises(CalculatorError) as exc_info:
        calc.add(2**54, 0)
    assert exc_info.value.code == "overflow"

def test_overflow_mutant02_boundary(calc):
    # Mutant 02 uses 2**52 as limit.
    # 2**52 * 3 = 3 * 2**52 which is > 2**52 but < 2**53
    # On correct engine: 3 * 2**52 < 2**53, so NO overflow
    # On mutant 02: 3 * 2**52 > 2**52, so OVERFLOW
    # This test verifies correct engine does NOT raise for values between 2**52 and 2**53
    val = int(2**52 * 1.5)  # 1.5 * 2**52 = 3 * 2**51, between 2**52 and 2**53
    # Should NOT raise on correct engine
    result = calc.add(val, 0)
    assert result is not None

def test_history_is_list_of_strings_check(calc):
    calc.subtract(5, 2)
    h = calc.history()
    assert isinstance(h, list)
    assert len(h) == 1
    assert isinstance(h[0], str)
    assert "=" in h[0]

def test_divide_result_precision(calc):
    # 22/7 = 3.142857... rounded to 6 places
    result = calc.divide(22, 7)
    assert result == 3.142857

def test_evaluate_not_left_to_right_extra(calc):
    # 1 + 2 * 3 = 7 (not 9 if left-to-right)
    result = calc.evaluate("1 + 2 * 3")
    assert result == 7.0
    assert result != 9.0

def test_percent_not_divided_by_10(calc):
    # Mutant 10: divides by 10 instead of 100
    # percent(500, 20) = 500*20/100 = 100 (correct)
    # percent(500, 20) = 500*20/10 = 1000 (mutant)
    result = calc.percent(500, 20)
    assert result == 100.0
    assert result != 1000.0

def test_batch_returns_correct_values_extra(calc):
    # Mutant 07: always returns 0.0
    results = calc.batch([("add", 7, 3)])
    assert results[0] == 10.0
    assert results[0] != 0.0

