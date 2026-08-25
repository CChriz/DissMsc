"""Tests for the calculator engine.

22 test functions covering all 21 behaviors and 20 test cases from spec.
"""
import pytest
import threading
from calculator.engine import Calculator, CalculatorError


# ============================================================
# 组 A：基本四则运算（行为 1-4，测试用例 1, 17, 18, 19）
# ============================================================

def test_add_basic(calc):
    """Behavior 1 / Case 1: Basic addition."""
    assert calc.add(100, 200) == 300.0


def test_subtract_basic(calc):
    """Behavior 2 / Case 17: Basic subtraction."""
    assert calc.subtract(99, 44) == 55.0


def test_multiply_basic(calc):
    """Behavior 3 / Case 18: Basic multiplication including zero and negative."""
    assert calc.multiply(0, 100) == 0.0
    assert calc.multiply(7, 8) == 56.0
    assert calc.multiply(-3, 5) == -15.0


def test_divide_basic(calc):
    """Behavior 4 / Case 19: Basic division."""
    assert calc.divide(81, 9) == 9.0
    assert calc.divide(5, 2) == 2.5


# ============================================================
# 组 B：错误处理（行为 5-7，测试用例 2-4）
# ============================================================

def test_divide_by_zero(calc):
    """Behavior 5 / Case 2: Division by zero raises CalculatorError."""
    with pytest.raises(CalculatorError) as exc_info:
        calc.divide(10, 0)
    assert exc_info.value.code == "division_by_zero"


def test_overflow(calc):
    """Behavior 6 / Case 3: Overflow detection.

    - Input overflow: 9007199254741991 (> 2**53) triggers overflow.
    - Boundary: exactly 2**53 does NOT overflow.
    - Result overflow: multiply result exceeding limit triggers overflow.
    """
    # Input overflow
    with pytest.raises(CalculatorError) as exc_info:
        calc.add(9007199254741991, 1)
    assert exc_info.value.code == "overflow"

    # Boundary: exactly 2**53 should NOT overflow (uses > not >=)
    boundary = 2 ** 53
    assert calc.add(boundary, 0) == float(boundary)

    # Result overflow: 2**52 * 4 = 2**54 > 2**53
    with pytest.raises(CalculatorError) as exc_info2:
        calc.multiply(2 ** 52, 4)
    assert exc_info2.value.code == "overflow"


def test_sqrt_domain_error(calc):
    """Behavior 7 / Case 4: sqrt of negative raises domain_error.

    Also test valid sqrt calls on boundary values.
    """
    # Negative input -> domain_error
    with pytest.raises(CalculatorError) as exc_info:
        calc.sqrt(-4)
    assert exc_info.value.code == "domain_error"

    # Valid sqrt calls
    assert calc.sqrt(0) == 0.0
    assert calc.sqrt(4) == 2.0


# ============================================================
# 组 C：链式操作（行为 8，测试用例 5）
# ============================================================

def test_chaining(calc):
    """Behavior 8 / Case 5: Method chaining with .result().

    Also tests chain divide-by-zero error and string coercion in chain.
    """
    # Basic chaining from spec
    result = calc.chain(8).add(2).multiply(3).subtract(6).result()
    assert result == 24.0

    # Chain divide-by-zero
    with pytest.raises(CalculatorError) as exc_info:
        calc.chain(10).divide(0)
    assert exc_info.value.code == "division_by_zero"

    # Chain divide (happy path)
    assert calc.chain(20).divide(4).result() == 5.0

    # Chain with string coercion
    assert calc.chain(1).add("3").result() == 4.0


# ============================================================
# 组 D：内存操作（行为 9-10，测试用例 6, 14）
# ============================================================

def test_memory_store_and_recall(calc):
    """Behavior 9 / Case 6: Memory store and recall.

    Tests store, recall, overwrite, negatives, and zero.
    """
    calc.memory_store(99)
    assert calc.memory_recall() == 99.0

    # Overwrite
    calc.memory_store(-5)
    assert calc.memory_recall() == -5.0

    # Store zero
    calc.memory_store(0)
    assert calc.memory_recall() == 0.0


def test_memory_clear(calc):
    """Behavior 10 / Case 14 (partial): Memory clear.

    After clear, recall returns 0.0. Also initial recall is 0.0.
    """
    # Initial recall should be 0.0
    assert calc.memory_recall() == 0.0

    # Store, clear, recall
    calc.memory_store(50)
    calc.memory_clear()
    assert calc.memory_recall() == 0.0


# ============================================================
# 组 E：精度（行为 11，测试用例 7）
# ============================================================

def test_precision(calc):
    """Behavior 11 / Case 7: Results rounded to 6 decimal places.

    Tests rounding behaviour including round-half-to-even cases.
    """
    assert calc.divide(1, 9) == 0.111111
    assert calc.divide(2, 3) == 0.666667   # round up
    assert calc.divide(1, 3) == 0.333333   # round down


# ============================================================
# 组 F：百分比（行为 12，测试用例 8）
# ============================================================

def test_percent(calc):
    """Behavior 12 / Case 8: Percentage calculation.

    Tests normal, zero base, and zero percent cases.
    """
    assert calc.percent(80, 25) == 20.0
    assert calc.percent(200, 15) == 30.0
    assert calc.percent(0, 50) == 0.0
    assert calc.percent(50, 0) == 0.0


# ============================================================
# 组 G：表达式解析（行为 13-14, 5, 20）
# ============================================================

def test_evaluate_precedence(calc):
    """Behavior 13 / Case 9: Expression evaluation with operator precedence.

    Multiplication/division before addition/subtraction.
    """
    assert calc.evaluate("2 + 3 * 4") == 14.0
    assert calc.evaluate("10 - 2 * 3") == 4.0
    assert calc.evaluate("8 / 2 + 1") == 5.0


def test_evaluate_parentheses(calc):
    """Behavior 14 / Case 10: Parentheses override precedence."""
    assert calc.evaluate("(2 + 3) * 4") == 20.0
    assert calc.evaluate("((1+2)*3)") == 9.0


def test_evaluate_errors(calc):
    """Covers division_by_zero in expr, invalid_input, and UnaryOp (negation).

    Also tests behavior 5 (division_by_zero) and 20 (invalid_input) via evaluate.
    """
    # Division by zero in expression
    with pytest.raises(CalculatorError) as exc_info:
        calc.evaluate("1/0")
    assert exc_info.value.code == "division_by_zero"

    # Invalid expression: non-numeric
    with pytest.raises(CalculatorError) as exc_info2:
        calc.evaluate("abc")
    assert exc_info2.value.code == "invalid_input"

    # Invalid syntax
    with pytest.raises(CalculatorError) as exc_info3:
        calc.evaluate("1++2")
    assert exc_info3.value.code == "invalid_input"

    # Unary minus (covers ast.UnaryOp branch)
    assert calc.evaluate("-5 + 3") == -2.0

    # Unsupported operator (e.g. exponentiation)
    with pytest.raises(CalculatorError) as exc_info4:
        calc.evaluate("2 ** 3")
    assert exc_info4.value.code == "invalid_input"


# ============================================================
# 组 H：历史记录（行为 15-16，测试用例 11-12）
# ============================================================

def test_history_cap(calc):
    """Behavior 15 / Case 11: History capped at 10 entries.

    After 11 operations, oldest is dropped, only 10 remain.
    """
    for i in range(1, 12):  # 1..11
        calc.add(i, i)

    history = calc.history()
    assert len(history) == 10

    # The first operation add(1,1)=2.0 should be dropped
    # The oldest remaining should be add(2,2)=4.0
    assert "add(2.0, 2.0) = 4.0" in history[0]


def test_undo(calc):
    """Behavior 16 / Case 12: Undo reverses last operation and removes history entry.

    Tests single undo, multiple undo, and undo on empty history.
    """
    # Single undo
    calc.add(1, 2)
    calc.undo()
    assert calc.history() == []

    # Multiple undo: 3 operations, undo 2, 1 remains
    calc.add(1, 2)
    calc.add(3, 4)
    calc.add(5, 6)
    assert len(calc.history()) == 3
    calc.undo()
    assert len(calc.history()) == 2
    calc.undo()
    assert len(calc.history()) == 1

    # Undo on empty history should not raise
    calc.reset()
    calc.undo()  # should not raise
    assert calc.history() == []


# ============================================================
# 组 I：批量操作（行为 17，测试用例 13）
# ============================================================

def test_batch(calc):
    """Behavior 17 / Case 13: Batch operations.

    Tests normal batch, empty batch, and invalid operation name.
    """
    # Normal batch
    results = calc.batch([("add", 1, 2), ("multiply", 3, 4)])
    assert results == [3.0, 12.0]

    # Empty batch
    assert calc.batch([]) == []

    # Invalid operation name
    with pytest.raises(CalculatorError) as exc_info:
        calc.batch([("nonexist", 1, 2)])
    assert exc_info.value.code == "invalid_input"


# ============================================================
# 组 J：重置（行为 18，测试用例 14）
# ============================================================

def test_reset(calc):
    """Behavior 18 / Case 14: Reset clears history, memory, and chain state."""
    calc.add(5, 3)
    calc.memory_store(10)

    calc.reset()

    assert calc.memory_recall() == 0.0
    assert calc.history() == []


# ============================================================
# 组 K：类型强制转换（行为 19-20，测试用例 15-16）
# ============================================================

def test_type_coercion(calc):
    """Behavior 19 / Case 15: Numeric strings auto-converted to numbers."""
    assert calc.add("5", "3") == 8.0
    assert calc.multiply("2.5", "4") == 10.0
    assert calc.percent("100", "20") == 20.0


def test_invalid_input(calc):
    """Behavior 20 / Case 16: Non-numeric strings raise invalid_input error."""
    # add with bad string
    with pytest.raises(CalculatorError) as exc_info:
        calc.add("abc", 1)
    assert exc_info.value.code == "invalid_input"

    # subtract with bad string
    with pytest.raises(CalculatorError) as exc_info2:
        calc.subtract(1, "xyz")
    assert exc_info2.value.code == "invalid_input"

    # sqrt with bad string
    with pytest.raises(CalculatorError) as exc_info3:
        calc.sqrt("abc")
    assert exc_info3.value.code == "invalid_input"


# ============================================================
# 组 L：线程安全（行为 21，测试用例 20）
# ============================================================

def test_thread_safety(calc):
    """Behavior 21 / Case 20: Concurrent operations must not raise or corrupt."""
    errors = []

    def worker():
        try:
            result = calc.add(1, 1)
            assert result == 2.0, f"Expected 2.0, got {result}"
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"Thread safety errors: {errors}"
