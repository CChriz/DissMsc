# Analysis Guidance for Expertise-Asymmetry Condition

## Recommended Analysis Tools
- `cd /workspace && python -m pytest --collect-only 2>&1` — show existing test structure
- `cd /workspace && python -m pytest --cov=calculator --cov-branch --cov-report=term-missing 2>&1` — coverage map
- `find /workspace -name "*.py" | head -20` — explore structure

## Expected Findings
Coverage analysis will show which of the 21 behaviors lack test coverage:
- Happy paths likely covered (add, subtract, basic operations)
- Uncovered branches: error handling paths, memory operations, chaining, thread safety

## False Positives to Ignore
None — all coverage gaps represent genuinely untested behaviors from the spec.

## Key Insight
The spec lists exactly 20 behaviors + thread safety. Coverage tool shows which branches the existing tests miss. Focus on behaviors 5-21 (chaining, memory, precision, etc.) which are likely undertested.
