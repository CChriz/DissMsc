"""Tests for the calculator engine. Comprehensive tests covering 21 behaviors and 20 test cases."""
import pytest
import threading
from calculator.engine import Calculator, CalculatorError


# ============================================================
# 一、基本算术运算 (4 tests)
# ============================================================

def test_add_basic(calc):
    """行为#1, 用例#1: 基本加法验证."""
    assert calc.add(100, 200) == 300.0


def test_subtract_basic(calc):
    """行为#2, 用例#17: 基本减法验证."""
    assert calc.subtract(99, 44) == 55.0


def test_multiply_basic(calc):
    """行为#3: 基本乘法验证（非0乘数）."""
    assert calc.multiply(7, 8) == 56.0


def test_divide_basic(calc):
    """行为#4, 用例#19: 基本除法验证."""
    assert calc.divide(81, 9) == 9.0


# ============================================================
# 二、零值边界测试 (1 test)
# ============================================================

def test_multiply_by_zero(calc):
    """行为#3, 用例#18: 零乘任何数得零."""
    assert calc.multiply(0, 100) == 0.0
    assert calc.multiply(100, 0) == 0.0


# ============================================================
# 三、错误处理 (3 tests)
# ============================================================

def test_divide_by_zero(calc):
    """行为#5, 用例#2: 除零抛出 CalculatorError."""
    with pytest.raises(CalculatorError) as exc_info:
        calc.divide(10, 0)
    assert exc_info.value.code == "division_by_zero"


def test_overflow(calc):
    """行为#6, 用例#3: 溢出抛出 CalculatorError."""
    with pytest.raises(CalculatorError) as exc_info:
        calc.add(9007199254741991, 1)
    assert exc_info.value.code == "overflow"


def test_sqrt_domain_error(calc):
    """行为#7, 用例#4: 负数平方根抛出 domain_error."""
    with pytest.raises(CalculatorError) as exc_info:
        calc.sqrt(-4)
    assert exc_info.value.code == "domain_error"


# ============================================================
# 四、链式操作 (1 test)
# ============================================================

def test_chain_operations(calc):
    """行为#8, 用例#5: 链式调用 ((8+2)*3)-6 = 24."""
    result = calc.chain(8).add(2).multiply(3).subtract(6).result()
    assert result == 24.0


# ============================================================
# 五、内存操作 (2 tests)
# ============================================================

def test_memory_store_recall(calc):
    """行为#9, 用例#6: memory_store 后 memory_recall 返回存储值."""
    calc.memory_store(99)
    assert calc.memory_recall() == 99.0


def test_memory_clear(calc):
    """行为#10: memory_clear 后 memory_recall 返回 0.0."""
    calc.memory_store(50)
    calc.memory_clear()
    assert calc.memory_recall() == 0.0


# ============================================================
# 六、精度测试 (1 test)
# ============================================================

def test_precision_rounding(calc):
    """行为#11, 用例#7: 结果精确到 6 位小数."""
    assert calc.divide(1, 9) == 0.111111
    assert calc.divide(2, 3) == 0.666667


# ============================================================
# 七、百分比 (1 test)
# ============================================================

def test_percent(calc):
    """行为#12, 用例#8: 百分比计算."""
    assert calc.percent(80, 25) == 20.0
    assert calc.percent(200, 10) == 20.0
    assert calc.percent(0, 50) == 0.0


# ============================================================
# 八、表达式求值 (3 tests)
# ============================================================

def test_evaluate_precedence(calc):
    """行为#13, 用例#9: 乘除优先于加减."""
    assert calc.evaluate("2 + 3 * 4") == 14.0


def test_evaluate_parentheses(calc):
    """行为#14, 用例#10: 括号覆盖默认优先级."""
    assert calc.evaluate("(2 + 3) * 4") == 20.0


def test_evaluate_complex_expression(calc):
    """行为#13,#14: 混合运算确保优先级正确."""
    # 10 - 2*3 + 8/4 = 10 - 6 + 2 = 6
    assert calc.evaluate("10 - 2 * 3 + 8 / 4") == 6.0


# ============================================================
# 九、历史记录 (2 tests)
# ============================================================

def test_history_cap(calc):
    """行为#15, 用例#11: 历史记录上限为 10 条."""
    for i in range(11):
        calc.add(1, 1)
    history = calc.history()
    assert len(history) == 10
    assert history[0] == "add(1.0, 1.0) = 2.0"


def test_history_format(calc):
    """行为#15: 验证历史记录格式."""
    calc.add(3, 5)
    history = calc.history()
    assert history == ["add(3.0, 5.0) = 8.0"]


# ============================================================
# 十、撤销操作 (2 tests)
# ============================================================

def test_undo_basic(calc):
    """行为#16, 用例#12: undo 后历史记录为空."""
    calc.add(1, 2)
    calc.undo()
    assert calc.history() == []


def test_undo_restores_state(calc):
    """行为#16: undo 应恢复操作前的状态."""
    calc.add(1, 2)  # 先产生一条历史记录
    calc.undo()
    # undo 后历史应为空
    assert calc.history() == []


# ============================================================
# 十一、批量模式 (1 test)
# ============================================================

def test_batch(calc):
    """行为#17, 用例#13: 批量执行操作."""
    results = calc.batch([("add", 1, 2), ("multiply", 3, 4)])
    assert results == [3.0, 12.0]


# ============================================================
# 十二、重置 (1 test)
# ============================================================

def test_reset_complete(calc):
    """行为#18, 用例#14: reset 清除内存、历史和链式状态."""
    calc.memory_store(42)
    calc.add(1, 2)
    calc.reset()
    assert calc.memory_recall() == 0.0
    assert calc.history() == []


# ============================================================
# 十三、类型强制转换 (3 tests)
# ============================================================

def test_type_coercion_numeric(calc):
    """行为#19, 用例#15: 数字字符串自动转换."""
    assert calc.add("5", "3") == 8.0


def test_type_coercion_invalid(calc):
    """行为#20, 用例#16: 非法字符串抛出 invalid_input."""
    with pytest.raises(CalculatorError) as exc_info:
        calc.add("abc", 1)
    assert exc_info.value.code == "invalid_input"


def test_coercion_all_operations(calc):
    """行为#19,#20: 类型强制转换在所有基本运算中生效."""
    assert calc.subtract("10", "3") == 7.0
    assert calc.multiply("4", "5") == 20.0
    assert calc.divide("20", "4") == 5.0
    with pytest.raises(CalculatorError) as exc_info:
        calc.subtract("xyz", 1)
    assert exc_info.value.code == "invalid_input"


# ============================================================
# 十四、线程安全 (1 test)
# ============================================================

def test_thread_safety(calc):
    """行为#21, 用例#20: 多线程并发不抛异常."""
    errors = []

    def worker():
        try:
            calc.add(1, 1)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"Thread safety errors: {errors}"
