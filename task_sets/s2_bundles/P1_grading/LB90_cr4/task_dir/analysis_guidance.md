# Analysis Guidance for Expertise-Asymmetry Condition

## Recommended Analysis Tools
- `find /workspace -name "*.py" | head -20`
- `ruff check /workspace --select=E,F,B 2>&1`
- `python -m py_compile` on API files
- `grep -n "def \|class \|@" /workspace/app/*.py 2>&1 | head -40` — API surface

## Expected Findings
API review tasks commonly surface:
- Missing input validation
- Wrong HTTP status codes
- Missing required response fields
- Breaking changes to existing endpoints

## False Positives to Ignore
Intentional API design choices documented in spec.md.

## Key Insight
This is a code review task — compare the actual API implementation against the spec's API contract requirements. Static analysis finds structural issues; the review checklist in spec.md drives the verification.
