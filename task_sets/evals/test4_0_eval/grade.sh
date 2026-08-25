#!/usr/bin/env bash
# Grader for TEST4_property — property-based tests from spec invariants.
# Arguments: WORKSPACE REPORTS SUBMISSION TASK_DIR
# TASK_DIR contains: mutants/<INVARIANT_ID>.py  (one mutant per invariant)
# REPORTS/expected.json has: invariant_ids, min_mutants_caught, min_tests

set -o pipefail
WORKSPACE="$1"
REPORTS="$2"
SUBMISSION="$3"
TASK_DIR="$4"

mkdir -p "$REPORTS"

CHECKS=0; PASSED=0; FAILURES=""
check() {
  CHECKS=$((CHECKS + 1))
  local label="$2"
  if eval "$1" 2>/dev/null; then
    PASSED=$((PASSED + 1))
  else
    FAILURES="${FAILURES:+${FAILURES},}${label}"
  fi
}

cd "$WORKSPACE"

# ── Read expected metadata ────────────────────────────────────────────────────
EXPECTED="$REPORTS/expected.json"
if [ ! -f "$EXPECTED" ]; then
  # Fallback defaults if expected.json not present
  INVARIANT_IDS="[]"
  MIN_TESTS=4
  MIN_CAUGHT=3
else
  INVARIANT_IDS=$(python3 -c "import json; d=json.load(open('$EXPECTED')); print(' '.join(d.get('invariant_ids', [])))")
  MIN_TESTS=$(python3 -c "import json; d=json.load(open('$EXPECTED')); print(d.get('min_tests', 4))")
  MIN_CAUGHT=$(python3 -c "import json; d=json.load(open('$EXPECTED')); print(d.get('min_mutants_caught', 3))")
fi

TEST_FILE="tests/test_properties.py"

# ── Check 1: test file exists ─────────────────────────────────────────────────
check "test -f '$TEST_FILE'" "test_file_missing"

# ── Check 2: hypothesis is imported / @given used ─────────────────────────────
check "python3 -c \"
with open('$TEST_FILE') as f:
    src = f.read()
assert 'hypothesis' in src or 'from hypothesis' in src or '@given' in src, \
    'No hypothesis usage found'
print('HYPOTHESIS_FOUND')
\"" "no_hypothesis_import"

# ── Check 3: has @given decorators ────────────────────────────────────────────
check "python3 -c \"
with open('$TEST_FILE') as f:
    src = f.read()
assert '@given' in src, 'No @given decorator found'
import re
count = len(re.findall(r'@given', src))
assert count >= 1, f'Too few @given decorators: {count}'
print(f'GIVEN_COUNT: {count}')
\"" "no_given_decorators"

# ── Check 4: all tests pass on correct module.py ──────────────────────────────
check "python3 -m pytest '$TEST_FILE' -q --tb=short --timeout=60 2>&1 | tail -3 | grep -qE 'passed|no tests'" \
    "tests_fail_on_correct_module"

# ── Check 5: minimum test function count ──────────────────────────────────────
check "python3 -c \"
import ast
with open('$TEST_FILE') as f:
    tree = ast.parse(f.read())
test_funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name.startswith('test_')]
assert len(test_funcs) >= $MIN_TESTS, f'Only {len(test_funcs)} test functions (need >= $MIN_TESTS)'
print(f'TEST_COUNT: {len(test_funcs)}')
\"" "too_few_tests"

# ── Check 6: uses hypothesis strategies (st.) ─────────────────────────────────
check "python3 -c \"
with open('$TEST_FILE') as f:
    src = f.read()
assert 'st.' in src or 'strategies' in src, 'No hypothesis strategies (st.) used'
print('STRATEGIES_FOUND')
\"" "no_hypothesis_strategies"

# ── Checks 7+: per-mutant detection ───────────────────────────────────────────
# For each mutant in TASK_DIR/mutants/, replace module.py and verify tests FAIL

MUTANTS_DIR="$TASK_DIR/mutants"
MUTANT_CHECK_START=7
TOTAL_MUTANTS=0
CAUGHT_MUTANTS=0

if [ -d "$MUTANTS_DIR" ]; then
  for mutant_file in "$MUTANTS_DIR"/*.py; do
    [ -f "$mutant_file" ] || continue
    TOTAL_MUTANTS=$((TOTAL_MUTANTS + 1))
    mutant_name=$(basename "$mutant_file" .py)
    check "python3 -c \"
import shutil, subprocess, sys, os
# Backup correct module
shutil.copy('module.py', 'module.py.bak')
try:
    # Inject mutant
    shutil.copy('$mutant_file', 'module.py')
    # Run tests — should FAIL (mutant violates invariant)
    result = subprocess.run(
        [sys.executable, '-m', 'pytest', '$TEST_FILE', '-q', '--tb=no', '--timeout=60'],
        capture_output=True, text=True, timeout=90
    )
    caught = result.returncode != 0
    assert caught, f'Mutant {mutant_name} not caught (tests still pass on buggy module)'
    print(f'MUTANT_{mutant_name}_CAUGHT')
finally:
    shutil.copy('module.py.bak', 'module.py')
    os.remove('module.py.bak')
\"" "mutant_${mutant_name}_not_caught"
  done
fi

# ── Check N: overall mutant catch rate ────────────────────────────────────────
# Count how many mutants were caught in the per-mutant checks above (re-run summary)
check "python3 -c \"
import shutil, subprocess, sys, os, glob

mutant_files = sorted(glob.glob('$MUTANTS_DIR/*.py'))
if not mutant_files:
    print('NO_MUTANTS_FOUND — skipping')
    exit(0)

caught = 0
for mf in mutant_files:
    shutil.copy('module.py', 'module.py.bak')
    try:
        shutil.copy(mf, 'module.py')
        result = subprocess.run(
            [sys.executable, '-m', 'pytest', '$TEST_FILE', '-q', '--tb=no', '--timeout=60'],
            capture_output=True, text=True, timeout=90
        )
        if result.returncode != 0:
            caught += 1
    finally:
        shutil.copy('module.py.bak', 'module.py')
        try:
            os.remove('module.py.bak')
        except OSError:
            pass

total = len(mutant_files)
assert caught >= $MIN_CAUGHT, f'Only caught {caught}/{total} mutants (need >= $MIN_CAUGHT)'
print(f'MUTANTS_CAUGHT: {caught}/{total}')
\"" "insufficient_mutation_detection"

# ── Final scoring ─────────────────────────────────────────────────────────────
PARTIAL=$(python3 -c "print(round($PASSED/max(1,$CHECKS), 2))")
if [ "$PASSED" -eq "$CHECKS" ]; then SUCCESS=1; PASS=true; else SUCCESS=0; PASS=false; fi
FM=$(python3 -c "import json; print(json.dumps([x for x in '${FAILURES}'.split(',') if x]))")

cat > "$REPORTS/score.json" <<JSON
{
  "pass": $PASS,
  "primary": {"success": $SUCCESS},
  "secondary": {
    "checks_passed": $PASSED,
    "checks_total": $CHECKS,
    "partial_score": $PARTIAL
  },
  "failure_modes": $FM
}
JSON
