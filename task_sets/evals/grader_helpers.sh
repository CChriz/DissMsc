#!/usr/bin/env bash
# ============================================================================
# TeamBench Grader Helper Library
#
# Source this file at the top of grade.sh scripts to get common grading
# functions. Reduces boilerplate by ~50 lines per grader.
#
# Usage:
#   #!/usr/bin/env bash
#   set -euo pipefail
#   WORKSPACE="${1:-${WORKSPACE_DIR:-/workspace}}"
#   REPORTS="${2:-${REPORTS_DIR:-/reports}}"
#   source "$(dirname "$0")/../../harness/grader_helpers.sh"
#   init_grader 10   # total number of checks
#   cd "${WORKSPACE}"
#
#   check "C1" "description" "pass"
#   ...
#   finalize_grader
# ============================================================================

# ── State variables ──────────────────────────────────────────────────────────
_GRADER_PASS=true
_GRADER_PARTIAL=0
_GRADER_TOTAL=0
_GRADER_FINDINGS=""

# ── init_grader(total_checks) ───────────────────────────────────────────────
# Initialize the grader with the expected number of checks.
init_grader() {
    _GRADER_TOTAL="${1:?init_grader requires total_checks argument}"
    _GRADER_PASS=true
    _GRADER_PARTIAL=0
    _GRADER_FINDINGS=""

    # Activate venv if available
    source /usr/local/lib/venv/bin/activate 2>/dev/null || true
}

# ── check(id, description, "pass"|"fail") ──────────────────────────────────
# Record a single check result.
check() {
    local id="$1"
    local desc="$2"
    local result="$3"
    if [ "$result" = "pass" ]; then
        _GRADER_PARTIAL=$((_GRADER_PARTIAL + 1))
        _GRADER_FINDINGS="${_GRADER_FINDINGS}{\"id\":\"${id}\",\"ok\":true,\"note\":\"${desc}\"},"
    else
        _GRADER_PASS=false
        _GRADER_FINDINGS="${_GRADER_FINDINGS}{\"id\":\"${id}\",\"ok\":false,\"note\":\"${desc}\"},"
    fi
}

# ── run_pytest_check(check_id, description, test_path, [extra_args...]) ─────
# Run pytest on a test file/directory and record pass/fail.
run_pytest_check() {
    local id="$1"
    local desc="$2"
    local test_path="$3"
    shift 3
    local extra_args=("$@")

    if python -m pytest "$test_path" -q --tb=short "${extra_args[@]}" 2>&1 | tail -5 | grep -qE "passed|no tests"; then
        check "$id" "$desc" "pass"
    else
        check "$id" "$desc" "fail"
    fi
}

# ── run_python_check(check_id, description, python_code) ───────────────────
# Run inline Python code that prints "pass" or "fail" to stdout.
run_python_check() {
    local id="$1"
    local desc="$2"
    local code="$3"

    local result
    result=$(python3 -c "$code" 2>/dev/null || echo "fail")
    check "$id" "$desc" "$result"
}

# ── check_file_exists(check_id, description, filepath) ─────────────────────
# Check that a file exists.
check_file_exists() {
    local id="$1"
    local desc="$2"
    local filepath="$3"

    if [ -f "$filepath" ]; then
        check "$id" "$desc" "pass"
    else
        check "$id" "$desc" "fail"
    fi
}

# ── check_file_contains(check_id, description, filepath, pattern) ──────────
# Check that a file contains a grep pattern.
check_file_contains() {
    local id="$1"
    local desc="$2"
    local filepath="$3"
    local pattern="$4"

    if grep -qE "$pattern" "$filepath" 2>/dev/null; then
        check "$id" "$desc" "pass"
    else
        check "$id" "$desc" "fail"
    fi
}

# ── check_file_not_contains(check_id, description, filepath, pattern) ──────
# Check that a file does NOT contain a grep pattern.
check_file_not_contains() {
    local id="$1"
    local desc="$2"
    local filepath="$3"
    local pattern="$4"

    if grep -qE "$pattern" "$filepath" 2>/dev/null; then
        check "$id" "$desc" "fail"
    else
        check "$id" "$desc" "pass"
    fi
}

# ── check_command_succeeds(check_id, description, command...) ──────────────
# Check that a command exits with status 0.
check_command_succeeds() {
    local id="$1"
    local desc="$2"
    shift 2

    if "$@" >/dev/null 2>&1; then
        check "$id" "$desc" "pass"
    else
        check "$id" "$desc" "fail"
    fi
}

# ── check_go_builds(check_id, description, go_dir) ────────────────────────
# Check that a Go project compiles.
check_go_builds() {
    local id="$1"
    local desc="$2"
    local go_dir="$3"

    if (cd "$go_dir" && go build ./... 2>/dev/null); then
        check "$id" "$desc" "pass"
    else
        check "$id" "$desc" "fail"
    fi
}

# ── run_inline_python(python_code) ─────────────────────────────────────────
# Run inline Python and capture JSON output. Used for complex multi-check
# grading. The Python code should print a JSON dict like {"C2": true, "C3": false}.
run_inline_python() {
    local code="$1"
    local output_file="/tmp/_grader_inline_$$.json"

    (python3 -c "$code") > "$output_file" 2>/tmp/_grader_inline_err_$$.txt || true

    if [ -f "$output_file" ] && [ -s "$output_file" ]; then
        echo "$output_file"
    else
        echo ""
    fi
}

# ── parse_inline_result(output_file, check_id, description) ───────────────
# Parse a single check result from inline Python JSON output.
parse_inline_result() {
    local output_file="$1"
    local id="$2"
    local desc="$3"

    if [ -z "$output_file" ] || [ ! -f "$output_file" ]; then
        check "$id" "$desc" "fail"
        return
    fi

    local val
    val=$(python3 -c "
import json, sys
d = json.load(open('$output_file'))
print('pass' if d.get('$id', False) else 'fail')
" 2>/dev/null || echo "fail")
    check "$id" "$desc" "$val"
}

# ── finalize_grader() ──────────────────────────────────────────────────────
# Write score.json and exit. Call this at the end of every grade.sh.
finalize_grader() {
    local reports_dir="${REPORTS:-/reports}"
    local partial_score
    partial_score=$(python3 -c "print(round($_GRADER_PARTIAL / $_GRADER_TOTAL, 2))")

    # Remove trailing comma from findings
    _GRADER_FINDINGS="${_GRADER_FINDINGS%,}"

    mkdir -p "${reports_dir}"
    cat > "${reports_dir}/score.json" <<EOF
{
  "pass": $( [ "$_GRADER_PASS" = "true" ] && echo "true" || echo "false" ),
  "secondary": {
    "partial_score": $partial_score,
    "checks_passed": $_GRADER_PARTIAL,
    "checks_total": $_GRADER_TOTAL
  },
  "failure_modes": [],
  "checklist": [$_GRADER_FINDINGS]
}
EOF
}
