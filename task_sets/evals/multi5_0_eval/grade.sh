#!/usr/bin/env bash
# MULTI5 grader: verify CI/CD pipeline stages are fixed
set -uo pipefail

WORKSPACE="${1:-${WORKSPACE_DIR:-/workspace}}"
REPORTS="${2:-${REPORTS_DIR:-/reports}}"

cd "$WORKSPACE"

pass=true
partial=0
total=10
findings=""

check() {
    local id="$1"
    local desc="$2"
    local result="$3"
    if [ "$result" = "pass" ]; then
        partial=$((partial + 1))
        findings="${findings}{\"id\":\"${id}\",\"ok\":true,\"note\":\"${desc}\"},"
    else
        pass=false
        findings="${findings}{\"id\":\"${id}\",\"ok\":false,\"note\":\"${desc}\"},"
    fi
}

# -------------------------------------------------------------------
# C1: .pylintrc exists and is valid INI
# -------------------------------------------------------------------
if python3 -c "
import configparser, sys
cp = configparser.ConfigParser()
cp.read('.pylintrc')
if not cp.sections():
    sys.exit(1)
sys.exit(0)
" 2>/dev/null; then
    check "C1" ".pylintrc is valid INI with sections" "pass"
else
    check "C1" ".pylintrc missing or invalid" "fail"
fi

# -------------------------------------------------------------------
# C2: pylint max-line-length is reasonable (>=100)
# -------------------------------------------------------------------
if python3 -c "
import configparser, sys
cp = configparser.ConfigParser()
cp.read('.pylintrc')
val = cp.get('format', 'max-line-length', fallback='0')
sys.exit(0 if int(val) >= 100 else 1)
" 2>/dev/null; then
    check "C2" "pylint max-line-length is >= 100" "pass"
else
    check "C2" "pylint max-line-length too restrictive (< 100)" "fail"
fi

# -------------------------------------------------------------------
# C3: App Python files pass pylint with the fixed config
# -------------------------------------------------------------------
if python3 -m pylint --rcfile=.pylintrc --disable=C0114,C0115,C0116,R0903 app/*.py --score=no 2>/dev/null; then
    check "C3" "App files pass pylint with fixed config" "pass"
else
    check "C3" "App files still fail pylint" "fail"
fi

# -------------------------------------------------------------------
# C4: conftest.py exists and is valid Python
# -------------------------------------------------------------------
if python3 -c "import ast; ast.parse(open('tests/conftest.py').read())" 2>/dev/null; then
    check "C4" "tests/conftest.py is valid Python" "pass"
else
    check "C4" "tests/conftest.py missing or invalid" "fail"
fi

# -------------------------------------------------------------------
# C5: conftest.py uses session-scoped db fixture
# -------------------------------------------------------------------
if python3 -c "
import ast, sys
src = open('tests/conftest.py').read()
tree = ast.parse(src)
for node in ast.walk(tree):
    if isinstance(node, ast.Call):
        func_src = ast.unparse(node)
        if 'fixture' in func_src and 'session' in func_src:
            sys.exit(0)
sys.exit(1)
" 2>/dev/null; then
    check "C5" "conftest.py db fixture uses session scope" "pass"
else
    check "C5" "conftest.py db fixture not session-scoped" "fail"
fi

# -------------------------------------------------------------------
# C6: pytest tests pass
# -------------------------------------------------------------------
if python3 -m pytest tests/ -q --tb=no 2>/dev/null | grep -q "passed"; then
    check "C6" "pytest tests pass" "pass"
else
    check "C6" "pytest tests fail" "fail"
fi

# -------------------------------------------------------------------
# C7: Dockerfile exists and is valid
# -------------------------------------------------------------------
if [ -f "Dockerfile" ] && grep -q "^FROM" Dockerfile 2>/dev/null; then
    check "C7" "Dockerfile exists with FROM directive" "pass"
else
    check "C7" "Dockerfile missing or no FROM" "fail"
fi

# -------------------------------------------------------------------
# C8: Dockerfile COPY path references correct source
# -------------------------------------------------------------------
if python3 -c "
import sys
content = open('Dockerfile').read()
# Must copy from app/ directory (the actual source location)
if 'COPY app/' in content or 'COPY ./app/' in content or 'COPY [\"app/' in content:
    sys.exit(0)
sys.exit(1)
" 2>/dev/null; then
    check "C8" "Dockerfile COPY uses correct app/ path" "pass"
else
    check "C8" "Dockerfile COPY uses wrong path" "fail"
fi

# -------------------------------------------------------------------
# C9: Dockerfile has APP_VERSION build arg
# -------------------------------------------------------------------
if grep -qE "^ARG APP_VERSION" Dockerfile 2>/dev/null; then
    check "C9" "Dockerfile has ARG APP_VERSION" "pass"
else
    check "C9" "Dockerfile missing ARG APP_VERSION" "fail"
fi

# -------------------------------------------------------------------
# C10: pipeline.yaml is valid YAML
# -------------------------------------------------------------------
if python3 -c "
import sys
try:
    import yaml
    yaml.safe_load(open('pipeline.yaml'))
except ImportError:
    import json
    # fallback: at least check it is readable text
    open('pipeline.yaml').read()
sys.exit(0)
" 2>/dev/null; then
    check "C10" "pipeline.yaml is valid" "pass"
else
    check "C10" "pipeline.yaml is invalid" "fail"
fi

partial_score=$(awk "BEGIN {printf \"%.4f\", $partial / $total}")
findings="${findings%,}"

mkdir -p "${REPORTS}"
cat > "${REPORTS}/score.json" <<EOF
{
  "pass": $( [ "$pass" = "true" ] && echo "true" || echo "false" ),
  "secondary": {
    "partial_score": $partial_score,
    "checks_passed": $partial,
    "total_checks": $total
  },
  "failure_modes": [],
  "checklist": [$findings]
}
EOF
