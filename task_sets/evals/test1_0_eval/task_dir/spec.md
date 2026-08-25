# TEST1: Write Tests from Specification

## Goal
Write comprehensive tests for the calculator engine that catch bugs through mutation testing.

## Calculator Specification — 20 Behaviors

### Basic Arithmetic
1. `calc.add(a, b)` returns the sum of `a` and `b`
2. `calc.subtract(a, b)` returns the difference `a` minus `b`
3. `calc.multiply(a, b)` returns the product of `a` and `b`
4. `calc.divide(a, b)` returns the quotient `a` divided by `b`

### Error Handling
5. Dividing by zero raises `CalculatorError` with code `"division_by_zero"`
6. Numbers exceeding 2^53 raise `CalculatorError` with code `"overflow"`
7. Taking the square root of a negative number raises `CalculatorError` with code `"domain_error"`

### Chained Operations
8. The calculator supports method chaining starting from an initial value; each chained operation applies to the running result; calling `.result()` returns the final value

### Memory
9. A value stored with `memory_store` is returned by a subsequent `memory_recall`
10. After `memory_clear`, `memory_recall` returns `0.0`

### Precision
11. All results are rounded to exactly 6 decimal places (e.g., one-third is `0.333333`, not a longer repeating decimal)

### Percentage
12. `calc.percent(value, pct)` returns the given percentage of the value

### Expression Parsing
13. `calc.evaluate(expr)` parses and evaluates arithmetic expressions following standard operator precedence (multiplication and division before addition and subtraction)
14. Parentheses in expressions override default precedence

### History
15. `calc.history()` returns a list of the last 10 operations as strings in the format `"op(a, b) = result"`; operations beyond 10 cause the oldest to be dropped

### Undo
16. After an operation, calling `calc.undo()` reverses that operation and removes its entry from history

### Batch Mode
17. `calc.batch(ops)` accepts a list of `(operation, arg1, arg2)` tuples and returns a list of results in the same order

### Reset
18. `calc.reset()` clears history, memory, and any chain state

### Type Coercion
19. Numeric string inputs (e.g., `"5"`) are automatically converted to numbers
20. Non-numeric string inputs raise `CalculatorError` with code `"invalid_input"`

### Thread Safety
21. Concurrent operations from multiple threads must not corrupt calculator state or raise exceptions

## Test Cases Table

| # | Operation | Expected | Notes |
|---|-----------|----------|-------|
| 1 | add(1, 2) | 3.0 | Basic |
| 2 | divide(10, 0) | CalculatorError("division_by_zero") | Error |
| 3 | add(2**53 + 1, 1) | CalculatorError("overflow") | Boundary |
| 4 | sqrt(-4) | CalculatorError("domain_error") | Domain |
| 5 | chain(10).add(5).multiply(2).result() | 30.0 | Chaining |
| 6 | memory_store(99); memory_recall() | 99.0 | Memory |
| 7 | divide(1, 3) | 0.333333 | Precision |
| 8 | percent(200, 15) | 30.0 | Percentage |
| 9 | evaluate("2 + 3 * 4") | 14.0 | Precedence |
| 10 | evaluate("(2 + 3) * 4") | 20.0 | Parentheses |
| 11 | 11 operations; history() length | 10 | History cap |
| 12 | add(1,2); undo(); history() | [] | Undo |
| 13 | batch([("add",1,2),("multiply",3,4)]) | [3.0, 12.0] | Batch |
| 14 | reset(); memory_recall() | 0.0 | Reset |
| 15 | add("5", "3") | 8.0 | Coercion |
| 16 | add("abc", 1) | CalculatorError("invalid_input") | Bad input |
| 17 | subtract(10, 3) | 7.0 | Basic |
| 18 | multiply(0, 100) | 0.0 | Zero |
| 19 | divide(7, 2) | 3.5 | Float |
| 20 | 10 threads each calling add(1,1) | No exceptions | Thread safety |

## Grading
- Phase 1: All tests must pass on correct engine (pytest passes, branch coverage > 80%)
- Phase 2: Tests must catch at least 7/10 mutant engines (each has one subtle bug)

## Deliverables
- `calculator/test_engine.py` with at least 15 test functions
- Verifier must run tests and verify coverage + mutation detection
