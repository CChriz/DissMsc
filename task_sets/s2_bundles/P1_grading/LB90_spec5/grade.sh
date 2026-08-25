#!/usr/bin/env bash
# Seed-aware grader for SPEC5: Configuration System from Requirements
#
# Reads domain and schema from expected.json (written by generator).
# Tests: all keys loadable, defaults correct, validation rejects invalid values,
#        env override works, type coercion works, CLI priority wins, file override
#        works, invalid values rejected with ConfigValidationError.
#
# Args: $1=WORKSPACE $2=REPORTS $3=SUBMISSION $4=TASK_DIR [$5=EXPECTED_JSON]
set -o pipefail
WORKSPACE="$1"
REPORTS="$2"
SUBMISSION="$3"
TASK_DIR="$4"
EXPECTED="${5:-$REPORTS/expected.json}"

mkdir -p "$REPORTS"

CHECKS=0; PASSED=0; FAILURES=""
check() {
  local label="$1"
  local script="$2"
  CHECKS=$((CHECKS + 1))
  if python3 "$script" "$WORKSPACE" "$EXPECTED" >/dev/null 2>&1; then
    PASSED=$((PASSED + 1))
  else
    FAILURES="${FAILURES:+${FAILURES},}$label"
  fi
}

cd "$WORKSPACE"

# ── Read domain from expected.json ───────────────────────────────────────────
DOMAIN=$(python3 - "$EXPECTED" <<'PYEOF'
import sys, json
e = json.load(open(sys.argv[1]))
print(e.get('domain', 'unknown'))
PYEOF
)

ENV_PREFIX=$(python3 - "$EXPECTED" <<'PYEOF'
import sys, json
e = json.load(open(sys.argv[1]))
print(e.get('env_prefix', 'APP'))
PYEOF
)

# Write all check scripts to a temp directory
TMPDIR_CHECKS=$(mktemp -d)
trap 'rm -rf "$TMPDIR_CHECKS"' EXIT

# ── Check 1: config_system.py exists ─────────────────────────────────────────
cat > "$TMPDIR_CHECKS/c01_exists.py" << 'PYEOF'
import sys, os
ws = sys.argv[1]
assert os.path.isfile(os.path.join(ws, 'config_system.py')), 'config_system.py missing'
print('EXISTS_OK')
PYEOF
check "config_system_missing" "$TMPDIR_CHECKS/c01_exists.py"

# ── Check 2: module imports without error ──────────────────────────────────────
cat > "$TMPDIR_CHECKS/c02_import.py" << 'PYEOF'
import sys
sys.path.insert(0, sys.argv[1])
from config_system import load_config, get_schema, validate_value, ConfigValidationError
print('IMPORT_OK')
PYEOF
check "import_error" "$TMPDIR_CHECKS/c02_import.py"

# ── Check 3: load_config() returns a dict with all schema keys ─────────────────
cat > "$TMPDIR_CHECKS/c03_allkeys.py" << 'PYEOF'
import sys, json
sys.path.insert(0, sys.argv[1])
from config_system import load_config, get_schema
e = json.load(open(sys.argv[2]))
expected_schema = e.get('schema', {})
cfg = load_config()
schema = get_schema()
assert isinstance(cfg, dict), f'load_config() must return dict, got {type(cfg)}'
assert isinstance(schema, dict), f'get_schema() must return dict, got {type(schema)}'
missing = [k for k in expected_schema if k not in cfg]
assert not missing, f'Missing keys in config: {missing}'
print('ALL_KEYS_OK')
PYEOF
check "missing_keys" "$TMPDIR_CHECKS/c03_allkeys.py"

# ── Check 4: default values are correct ────────────────────────────────────────
cat > "$TMPDIR_CHECKS/c04_defaults.py" << 'PYEOF'
import sys, json
sys.path.insert(0, sys.argv[1])
from config_system import load_config
e = json.load(open(sys.argv[2]))
schema = e.get('schema', {})
cfg = load_config()
errors = []
for key, spec in schema.items():
    expected_default = spec.get('default')
    actual = cfg.get(key)
    if actual != expected_default:
        errors.append(f'{key}: expected default {expected_default!r}, got {actual!r}')
assert not errors, 'Default value mismatches:\n' + '\n'.join(errors)
print('DEFAULTS_OK')
PYEOF
check "defaults_wrong" "$TMPDIR_CHECKS/c04_defaults.py"

# ── Check 5: env var override ─────────────────────────────────────────────────
cat > "$TMPDIR_CHECKS/c05_env_override.py" << 'PYEOF'
import sys, json
sys.path.insert(0, sys.argv[1])
from config_system import load_config
e = json.load(open(sys.argv[2]))
schema = e.get('schema', {})
# Find first int key with range
int_key = None
for k, v in schema.items():
    if v.get('type') == 'int' and 'min' in v and 'max' in v:
        mn = v['min']; mx = v['max']; mid = (mn + mx) // 2
        if mn < mid < mx:
            int_key = k
            env_var = v['env_var']
            test_val = mid
            break
if int_key is None:
    print('ENV_OVERRIDE_SKIP')
    sys.exit(0)
env = {env_var: str(test_val)}
cfg = load_config(env_vars=env)
actual = cfg.get(int_key)
assert actual == test_val, f'Env override failed: expected {test_val}, got {actual!r}'
print('ENV_OVERRIDE_OK')
PYEOF
check "env_override_fail" "$TMPDIR_CHECKS/c05_env_override.py"

# ── Check 6: CLI args override env vars ────────────────────────────────────────
cat > "$TMPDIR_CHECKS/c06_cli_priority.py" << 'PYEOF'
import sys, json
sys.path.insert(0, sys.argv[1])
from config_system import load_config
e = json.load(open(sys.argv[2]))
schema = e.get('schema', {})
# Find first enum key with at least 2 allowed values
enum_key = None
for k, v in schema.items():
    if v.get('type') == 'enum' and len(v.get('allowed', [])) >= 2:
        enum_key = k
        env_var = v['env_var']
        allowed = v['allowed']
        val_a = allowed[0]
        val_b = allowed[-1]
        break
if enum_key is None:
    print('CLI_PRIORITY_SKIP')
    sys.exit(0)
env = {env_var: val_a}
cli = {enum_key: val_b}
cfg = load_config(env_vars=env, cli_args=cli)
actual = cfg.get(enum_key)
assert actual == val_b, f'CLI should override env: expected {val_b!r}, got {actual!r}'
print('CLI_PRIORITY_OK')
PYEOF
check "cli_priority_fail" "$TMPDIR_CHECKS/c06_cli_priority.py"

# ── Check 7: config file values are loaded ────────────────────────────────────
cat > "$TMPDIR_CHECKS/c07_file_load.py" << 'PYEOF'
import sys, json, tempfile, os
sys.path.insert(0, sys.argv[1])
from config_system import load_config, get_schema
schema = get_schema()
key = next(iter(schema))
spec = schema[key]
file_cfg = {key: spec['default']}
with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
    json.dump(file_cfg, f)
    fname = f.name
try:
    cfg = load_config(config_file=fname, env_vars={})
    assert cfg[key] == spec['default'], f'File load wrong: {cfg[key]!r}'
    print('FILE_LOAD_OK')
finally:
    os.unlink(fname)
PYEOF
check "file_load_fail" "$TMPDIR_CHECKS/c07_file_load.py"

# ── Check 8: int validation — out-of-range raises ConfigValidationError ─────────
cat > "$TMPDIR_CHECKS/c08_int_range.py" << 'PYEOF'
import sys, json
sys.path.insert(0, sys.argv[1])
from config_system import validate_value, ConfigValidationError
e = json.load(open(sys.argv[2]))
schema = e.get('schema', {})
int_key = None
for k, v in schema.items():
    if v.get('type') == 'int' and 'min' in v and 'max' in v:
        int_key = k; mn = v['min']; mx = v['max']
        break
if int_key is None:
    print('INT_RANGE_SKIP')
    sys.exit(0)
try:
    validate_value(int_key, mn - 1)
    assert False, 'Should raise ConfigValidationError for value below min'
except ConfigValidationError:
    pass
try:
    validate_value(int_key, mx + 1)
    assert False, 'Should raise ConfigValidationError for value above max'
except ConfigValidationError:
    pass
print('INT_RANGE_OK')
PYEOF
check "int_range_validation_fail" "$TMPDIR_CHECKS/c08_int_range.py"

# ── Check 9: int boundary — exactly at min and max is valid ──────────────────
cat > "$TMPDIR_CHECKS/c09_int_boundary.py" << 'PYEOF'
import sys, json
sys.path.insert(0, sys.argv[1])
from config_system import validate_value
e = json.load(open(sys.argv[2]))
schema = e.get('schema', {})
int_key = None
for k, v in schema.items():
    if v.get('type') == 'int' and 'min' in v and 'max' in v:
        int_key = k; mn = v['min']; mx = v['max']
        break
if int_key is None:
    print('INT_BOUNDARY_SKIP')
    sys.exit(0)
v_min = validate_value(int_key, mn)
assert v_min == mn, f'Min boundary wrong: {v_min!r}'
v_max = validate_value(int_key, mx)
assert v_max == mx, f'Max boundary wrong: {v_max!r}'
print('INT_BOUNDARY_OK')
PYEOF
check "int_boundary_fail" "$TMPDIR_CHECKS/c09_int_boundary.py"

# ── Check 10: enum validation — invalid value raises ConfigValidationError ─────
cat > "$TMPDIR_CHECKS/c10_enum.py" << 'PYEOF'
import sys, json
sys.path.insert(0, sys.argv[1])
from config_system import validate_value, ConfigValidationError
e = json.load(open(sys.argv[2]))
schema = e.get('schema', {})
enum_key = None
for k, v in schema.items():
    if v.get('type') == 'enum':
        enum_key = k; allowed = v.get('allowed', [])
        break
if enum_key is None:
    print('ENUM_SKIP')
    sys.exit(0)
try:
    validate_value(enum_key, '__INVALID_ENUM_VALUE__')
    assert False, 'Should raise ConfigValidationError for invalid enum'
except ConfigValidationError:
    pass
for val in allowed:
    result = validate_value(enum_key, val)
    assert result == val, f'Valid enum {val!r} should return {val!r}, got {result!r}'
print('ENUM_VALIDATION_OK')
PYEOF
check "enum_validation_fail" "$TMPDIR_CHECKS/c10_enum.py"

# ── Check 11: bool type coercion from string ───────────────────────────────────
cat > "$TMPDIR_CHECKS/c11_bool_coerce.py" << 'PYEOF'
import sys, json
sys.path.insert(0, sys.argv[1])
from config_system import validate_value, ConfigValidationError
e = json.load(open(sys.argv[2]))
schema = e.get('schema', {})
bool_key = None
for k, v in schema.items():
    if v.get('type') == 'bool':
        bool_key = k
        break
if bool_key is None:
    print('BOOL_SKIP')
    sys.exit(0)
assert validate_value(bool_key, 'true') == True,  'true -> True failed'
assert validate_value(bool_key, 'True') == True,  'True -> True failed'
assert validate_value(bool_key, '1')    == True,  '1 -> True failed'
assert validate_value(bool_key, 'yes')  == True,  'yes -> True failed'
assert validate_value(bool_key, 'on')   == True,  'on -> True failed'
assert validate_value(bool_key, 'false') == False, 'false -> False failed'
assert validate_value(bool_key, 'False') == False, 'False -> False failed'
assert validate_value(bool_key, '0')    == False, '0 -> False failed'
assert validate_value(bool_key, 'no')   == False, 'no -> False failed'
assert validate_value(bool_key, 'off')  == False, 'off -> False failed'
assert validate_value(bool_key, True)   == True
assert validate_value(bool_key, False)  == False
print('BOOL_COERCION_OK')
PYEOF
check "bool_coercion_fail" "$TMPDIR_CHECKS/c11_bool_coerce.py"

# ── Check 12: bool env var override via string ──────────────────────────────────
cat > "$TMPDIR_CHECKS/c12_bool_env.py" << 'PYEOF'
import sys, json
sys.path.insert(0, sys.argv[1])
from config_system import load_config
e = json.load(open(sys.argv[2]))
schema = e.get('schema', {})
bool_key = None
for k, v in schema.items():
    if v.get('type') == 'bool':
        bool_key = k; bool_env = v['env_var']
        break
if bool_key is None:
    print('BOOL_ENV_SKIP')
    sys.exit(0)
cfg = load_config(env_vars={bool_env: 'false'})
assert cfg[bool_key] == False, f'Bool env override failed: {cfg[bool_key]!r}'
cfg2 = load_config(env_vars={bool_env: '1'})
assert cfg2[bool_key] == True, f'Bool env override (1) failed: {cfg2[bool_key]!r}'
print('BOOL_ENV_OK')
PYEOF
check "bool_env_fail" "$TMPDIR_CHECKS/c12_bool_env.py"

# ── Check 13: invalid bool string raises ConfigValidationError ─────────────────
cat > "$TMPDIR_CHECKS/c13_bool_invalid.py" << 'PYEOF'
import sys, json
sys.path.insert(0, sys.argv[1])
from config_system import validate_value, ConfigValidationError
e = json.load(open(sys.argv[2]))
schema = e.get('schema', {})
bool_key = None
for k, v in schema.items():
    if v.get('type') == 'bool':
        bool_key = k
        break
if bool_key is None:
    print('BOOL_INVALID_SKIP')
    sys.exit(0)
try:
    validate_value(bool_key, 'maybe')
    assert False, 'Should raise ConfigValidationError for invalid bool string'
except ConfigValidationError:
    pass
print('BOOL_INVALID_OK')
PYEOF
check "bool_invalid_fail" "$TMPDIR_CHECKS/c13_bool_invalid.py"

# ── Check 14: int string coercion from env var ────────────────────────────────
cat > "$TMPDIR_CHECKS/c14_int_coerce.py" << 'PYEOF'
import sys, json
sys.path.insert(0, sys.argv[1])
from config_system import load_config
e = json.load(open(sys.argv[2]))
schema = e.get('schema', {})
int_key = None
for k, v in schema.items():
    if v.get('type') == 'int' and 'min' in v and 'max' in v:
        int_key = k; mn = v['min']; env_var = v['env_var']
        break
if int_key is None:
    print('INT_COERCE_SKIP')
    sys.exit(0)
cfg = load_config(env_vars={env_var: str(mn)})
actual = cfg.get(int_key)
assert actual == mn, f'Int coercion from env failed: expected {mn} (int), got {actual!r}'
assert isinstance(actual, int), f'Int coercion must produce int, got {type(actual).__name__}'
print('INT_COERCION_OK')
PYEOF
check "int_coercion_fail" "$TMPDIR_CHECKS/c14_int_coerce.py"

# ── Check 15: FileNotFoundError on missing config file ────────────────────────
cat > "$TMPDIR_CHECKS/c15_file_not_found.py" << 'PYEOF'
import sys
sys.path.insert(0, sys.argv[1])
from config_system import load_config
try:
    load_config(config_file='/tmp/__nonexistent_config_spec5__.json', env_vars={})
    assert False, 'Should raise FileNotFoundError'
except FileNotFoundError:
    pass
print('FILE_NOT_FOUND_OK')
PYEOF
check "file_not_found_fail" "$TMPDIR_CHECKS/c15_file_not_found.py"

# ── Check 16: non-parseable int string raises ConfigValidationError ────────────
cat > "$TMPDIR_CHECKS/c16_int_parse_err.py" << 'PYEOF'
import sys, json
sys.path.insert(0, sys.argv[1])
from config_system import validate_value, ConfigValidationError
e = json.load(open(sys.argv[2]))
schema = e.get('schema', {})
int_key = None
for k, v in schema.items():
    if v.get('type') == 'int':
        int_key = k
        break
if int_key is None:
    print('INT_PARSE_SKIP')
    sys.exit(0)
try:
    validate_value(int_key, 'not_an_int')
    assert False, 'Should raise ConfigValidationError for non-parseable int'
except ConfigValidationError:
    pass
print('INT_PARSE_ERROR_OK')
PYEOF
check "int_parse_error_fail" "$TMPDIR_CHECKS/c16_int_parse_err.py"

# ── Check 17: get_schema() returns correct structure ──────────────────────────
cat > "$TMPDIR_CHECKS/c17_schema_struct.py" << 'PYEOF'
import sys, json
sys.path.insert(0, sys.argv[1])
from config_system import get_schema
e = json.load(open(sys.argv[2]))
expected_schema = e.get('schema', {})
schema = get_schema()
assert isinstance(schema, dict), f'get_schema() must return dict'
missing = [k for k in expected_schema if k not in schema]
assert not missing, f'Schema missing keys: {missing}'
for k, v in schema.items():
    assert 'type' in v, f'Schema entry for {k!r} missing type'
    assert 'default' in v, f'Schema entry for {k!r} missing default'
print('SCHEMA_STRUCTURE_OK')
PYEOF
check "schema_structure_fail" "$TMPDIR_CHECKS/c17_schema_struct.py"

# ── Check 18: CLI args override file config ───────────────────────────────────
cat > "$TMPDIR_CHECKS/c18_cli_file.py" << 'PYEOF'
import sys, json, tempfile, os
sys.path.insert(0, sys.argv[1])
from config_system import load_config, get_schema
schema = get_schema()
key = next(iter(schema))
spec = schema[key]
default_val = spec['default']
file_cfg = {key: default_val}
with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
    json.dump(file_cfg, f)
    fname = f.name
try:
    cfg = load_config(config_file=fname, env_vars={}, cli_args={key: default_val})
    assert cfg[key] == default_val, f'CLI+file override wrong: {cfg[key]!r}'
    print('CLI_FILE_PRIORITY_OK')
finally:
    os.unlink(fname)
PYEOF
check "cli_file_priority_fail" "$TMPDIR_CHECKS/c18_cli_file.py"

# ── Check 19: unknown keys in config file do not cause errors ─────────────────
cat > "$TMPDIR_CHECKS/c19_unknown_keys.py" << 'PYEOF'
import sys, json, tempfile, os
sys.path.insert(0, sys.argv[1])
from config_system import load_config
file_cfg = {'__unknown_key_xyz__': 'should_be_ignored', '__another_unknown__': 42}
with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
    json.dump(file_cfg, f)
    fname = f.name
try:
    cfg = load_config(config_file=fname, env_vars={})
    assert isinstance(cfg, dict), 'load_config must return dict even with unknown file keys'
    print('UNKNOWN_KEYS_OK')
finally:
    os.unlink(fname)
PYEOF
check "unknown_keys_error" "$TMPDIR_CHECKS/c19_unknown_keys.py"

# ── Score ─────────────────────────────────────────────────────────────────────
PARTIAL=$(python3 -c "print(round($PASSED/max(1,$CHECKS), 2))")
if [ "$PASSED" -eq "$CHECKS" ]; then
    SUCCESS=1; PASS=true
else
    SUCCESS=0; PASS=false
fi
FM=$(python3 -c "import json; print(json.dumps([x for x in '${FAILURES}'.split(',') if x]))")

cat > "$REPORTS/score.json" <<JSON
{
  "pass": $PASS,
  "primary": {"success": $SUCCESS},
  "secondary": {
    "checks_passed": $PASSED,
    "checks_total": $CHECKS,
    "partial_score": $PARTIAL,
    "domain": "$DOMAIN"
  },
  "failure_modes": $FM
}
JSON
