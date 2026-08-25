"""Tests for the calculator engine. Write comprehensive tests here."""
import pytest
from calculator.engine import Calculator, CalculatorError

# Specification hints:
# - calc.add(100, 200) should return 300.0
# - calc.subtract(99, 44) should return 55.0
# - calc.multiply(12, 12) should return 144.0
# - calc.divide(81, 9) should return 9.0
# - calc.chain(8).add(2).multiply(3).subtract(6).result() should return 24.0
# - calc.percent(80, 25) should return 20.0
# - calc.divide(1, 9) should return 0.111111 (6 decimal places)
# - calc.add(9007199254741991, 1) should raise CalculatorError("overflow")
# - calc.divide(10, 0) should raise CalculatorError("division_by_zero")
# - calc.sqrt(-4) should raise CalculatorError("domain_error")
# - calc.add("abc", 1) should raise CalculatorError("invalid_input")
# - calc.add("5", "3") should return 8.0 (type coercion)
# TODO: Write tests based on the specification above
