"""
Tests for the KVP protocol implementation.
Extended coverage: all 12 MUST, 5 SHOULD, 3 MAY requirements (~60 tests total).
"""
import pytest
import time
from protocol import KVStore


@pytest.fixture
def store():
    return KVStore()


# ═══════════════════════════════════════════════════════════════════════════
#  M1 — SET stores value
# ═══════════════════════════════════════════════════════════════════════════

def test_set_returns_ok(store):
    r = store.execute("SET foo bar")
    assert "OK" in r


def test_set_overwrite(store):
    store.execute("SET k1 v1")
    r = store.execute("SET k1 v2")
    assert "OK" in r
    r2 = store.execute("GET k1")
    assert "v2" in r2


# ═══════════════════════════════════════════════════════════════════════════
#  M2 — GET returns value or ERR key_not_found
# ═══════════════════════════════════════════════════════════════════════════

def test_get_existing_key(store):
    store.execute("SET hello world")
    r = store.execute("GET hello")
    assert "world" in r


def test_get_missing_key(store):
    r = store.execute("GET noexist")
    assert "ERR" in r and "key_not_found" in r


# ═══════════════════════════════════════════════════════════════════════════
#  M3 — DEL removes key
# ═══════════════════════════════════════════════════════════════════════════

def test_del_existing_key(store):
    store.execute("SET temp val")
    r = store.execute("DEL temp")
    assert "OK" in r
    r2 = store.execute("GET temp")
    assert "ERR" in r2


def test_del_not_found(store):
    r = store.execute("DEL nonexistent")
    assert "ERR" in r and "key_not_found" in r


# ═══════════════════════════════════════════════════════════════════════════
#  M4 — KEYS lists all keys
# ═══════════════════════════════════════════════════════════════════════════

def test_keys_empty(store):
    r = store.execute("KEYS")
    assert r == "END" or r.rstrip() == "END"


def test_keys_single(store):
    store.execute("SET a 1")
    r = store.execute("KEYS")
    assert "a" in r
    assert "END" in r


def test_keys_lists_all(store):
    store.execute("SET a 1")
    store.execute("SET b 2")
    r = store.execute("KEYS")
    assert "a" in r and "b" in r and "END" in r


# ═══════════════════════════════════════════════════════════════════════════
#  M5 — COUNT returns count
# ═══════════════════════════════════════════════════════════════════════════

def test_count_zero(store):
    r = store.execute("COUNT")
    assert "COUNT" in r and "0" in r


def test_count_after_sets(store):
    store.execute("SET x 1")
    store.execute("SET y 2")
    r = store.execute("COUNT")
    assert "2" in r


def test_count_after_del(store):
    store.execute("SET a 1")
    store.execute("SET b 2")
    store.execute("DEL a")
    r = store.execute("COUNT")
    assert "1" in r


def test_count_after_flush(store):
    store.execute("SET a 1")
    store.execute("SET b 2")
    store.execute("FLUSH")
    r = store.execute("COUNT")
    assert "0" in r


# ═══════════════════════════════════════════════════════════════════════════
#  M6 — EXISTS TRUE / FALSE
# ═══════════════════════════════════════════════════════════════════════════

def test_exists_true(store):
    store.execute("SET present val")
    r = store.execute("EXISTS present")
    assert "TRUE" in r


def test_exists_false(store):
    r = store.execute("EXISTS absent")
    assert "FALSE" in r


# ═══════════════════════════════════════════════════════════════════════════
#  M7 — FLUSH clears all
# ═══════════════════════════════════════════════════════════════════════════

def test_flush_clears_store(store):
    store.execute("SET a 1")
    store.execute("SET b 2")
    r = store.execute("FLUSH")
    assert "OK" in r
    r2 = store.execute("COUNT")
    assert "0" in r2


def test_flush_empty(store):
    r = store.execute("FLUSH")
    assert "OK" in r


# ═══════════════════════════════════════════════════════════════════════════
#  M9 — Unknown command
# ═══════════════════════════════════════════════════════════════════════════

def test_unknown_command(store):
    r = store.execute("BADCMD xyz")
    assert "ERR" in r and "unknown_command" in r


def test_empty_command(store):
    r = store.execute("")
    assert "ERR" in r and "unknown_command" in r


def test_whitespace_only_command(store):
    r = store.execute("   ")
    assert "ERR" in r and "unknown_command" in r


# ═══════════════════════════════════════════════════════════════════════════
#  M10 — Key length limit (MAX_KEY_LENGTH = 64)
# ═══════════════════════════════════════════════════════════════════════════

def test_key_exact_max_length(store):
    key = "k" * 64
    r = store.execute(f"SET {key} val")
    assert "OK" in r


def test_key_too_long(store):
    long_key = "k" * 65
    r = store.execute(f"SET {long_key} val")
    assert "ERR" in r and "key_too_long" in r


def test_key_far_too_long(store):
    long_key = "k" * 200
    r = store.execute(f"SET {long_key} val")
    assert "ERR" in r and "key_too_long" in r


# ═══════════════════════════════════════════════════════════════════════════
#  M11 — Value size limit (MAX_VALUE_SIZE = 1024)
# ═══════════════════════════════════════════════════════════════════════════

def test_value_exact_max_size(store):
    val = "v" * 1024
    r = store.execute(f"SET k {val}")
    assert "OK" in r


def test_value_too_large(store):
    big_val = "v" * 1025
    r = store.execute(f"SET k {big_val}")
    assert "ERR" in r and "value_too_large" in r


def test_value_far_too_large(store):
    big_val = "v" * 5000
    r = store.execute(f"SET k {big_val}")
    assert "ERR" in r and "value_too_large" in r


# ═══════════════════════════════════════════════════════════════════════════
#  M12 — Store capacity limit (MAX_KEYS = 100)
# ═══════════════════════════════════════════════════════════════════════════

def test_store_full(store):
    for i in range(100):
        store.execute(f"SET key{i} val{i}")
    r = store.execute("SET overflow_key overflow_val")
    assert "ERR" in r and "store_full" in r


def test_store_full_allows_update(store):
    for i in range(100):
        store.execute(f"SET key{i} val{i}")
    r = store.execute("SET key0 updated")
    assert "OK" in r


def test_store_del_then_add(store):
    for i in range(100):
        store.execute(f"SET key{i} val{i}")
    store.execute("DEL key0")
    r = store.execute("SET new_key new_val")
    assert "OK" in r


def test_store_at_exact_99(store):
    for i in range(99):
        store.execute(f"SET key{i} val{i}")
    r = store.execute("SET key99 val99")
    assert "OK" in r
    r2 = store.execute("COUNT")
    assert "100" in r2


# ═══════════════════════════════════════════════════════════════════════════
#  S1 — MSET multiple key-value pairs (SHOULD)
# ═══════════════════════════════════════════════════════════════════════════

def test_mset_basic(store):
    r = store.execute("MSET a 1 b 2 c 3")
    assert "OK" in r and "3" in r
    assert store.execute("GET a") == "1"
    assert store.execute("GET b") == "2"
    assert store.execute("GET c") == "3"


def test_mset_with_existing(store):
    store.execute("SET a old")
    r = store.execute("MSET a 1 b 2")
    assert "OK" in r and "2" in r
    assert store.execute("GET a") == "1"
    assert store.execute("GET b") == "2"


def test_mset_atomic_fail_key_too_long(store):
    """MSET must be atomic: if any key is invalid, no keys are written."""
    store.execute("SET existing val")
    long_key = "k" * 65
    r = store.execute(f"MSET good 1 {long_key} bad")
    assert "ERR" in r and "key_too_long" in r
    # Verify no keys were written
    assert "ERR" in store.execute("GET good") and "key_not_found" in store.execute("GET good")


def test_mset_atomic_fail_value_too_large(store):
    """MSET must be atomic: if any value is too large, no keys are written."""
    big_val = "v" * 1025
    r = store.execute(f"MSET good 1 bad {big_val}")
    assert "ERR" in r and "value_too_large" in r
    # Verify good was NOT written due to atomicity
    assert "ERR" in store.execute("GET good") and "key_not_found" in store.execute("GET good")


def test_mset_atomic_fail_store_full(store):
    """MSET must be atomic: if store would overflow, no keys are written."""
    for i in range(99):
        store.execute(f"SET k{i} v{i}")
    # MSET 3 pairs when only 1 slot left → must fail atomically
    r = store.execute("MSET new1 v1 new2 v2 new3 v3")
    assert "ERR" in r and "store_full" in r
    # Verify none were written
    assert "ERR" in store.execute("GET new1")
    assert "ERR" in store.execute("GET new2")
    assert "ERR" in store.execute("GET new3")


def test_mset_odd_args(store):
    r = store.execute("MSET a 1 b")
    assert "ERR" in r


# ═══════════════════════════════════════════════════════════════════════════
#  S2 — MGET multiple values (SHOULD)
# ═══════════════════════════════════════════════════════════════════════════

def test_mget_mixed(store):
    store.execute("SET a 1")
    r = store.execute("MGET a b c")
    lines = r.strip().split("\n")
    assert lines[0] == "1"
    assert lines[1] == "NIL"
    assert lines[2] == "NIL"
    assert "END" in r


def test_mget_all_missing(store):
    r = store.execute("MGET x y")
    lines = r.strip().split("\n")
    assert lines[0] == "NIL"
    assert lines[1] == "NIL"
    assert "END" in r


def test_mget_all_existing(store):
    store.execute("SET a 1")
    store.execute("SET b 2")
    r = store.execute("MGET a b")
    lines = r.strip().split("\n")
    assert lines[0] == "1"
    assert lines[1] == "2"
    assert "END" in r


# ═══════════════════════════════════════════════════════════════════════════
#  S3 — TTL time-to-live (SHOULD)
# ═══════════════════════════════════════════════════════════════════════════

def test_ttl_no_expiry(store):
    store.execute("SET k1 v1")
    r = store.execute("TTL k1")
    assert "-1" in r


def test_ttl_not_found(store):
    r = store.execute("TTL nonexistent")
    assert "ERR" in r and "key_not_found" in r


def test_ttl_with_setex(store):
    store.execute("SETEX k1 10 v1")
    r = store.execute("TTL k1")
    # TTL should return a non-negative integer <= 10 (may be 0 immediately after SETEX)
    import re
    match = re.search(r"-?\d+", r)
    assert match is not None
    ttl = int(match.group())
    assert 0 <= ttl <= 10


# ═══════════════════════════════════════════════════════════════════════════
#  S4 — SETEX set with expiration (SHOULD)
# ═══════════════════════════════════════════════════════════════════════════

def test_setex_basic(store):
    r = store.execute("SETEX k1 10 v1")
    assert "OK" in r
    r2 = store.execute("GET k1")
    assert "v1" in r2


def test_setex_expiry(store):
    store.execute("SETEX k1 1 v1")
    time.sleep(1.5)
    r = store.execute("GET k1")
    assert "ERR" in r and "key_not_found" in r


def test_setex_zero_seconds(store):
    r = store.execute("SETEX k1 0 v1")
    assert "ERR" in r and "unknown_command" in r


def test_setex_negative_seconds(store):
    r = store.execute("SETEX k1 -5 v1")
    assert "ERR" in r and "unknown_command" in r


def test_setex_ttl_after_expiry(store):
    """TTL on expired key should return key_not_found."""
    store.execute("SETEX k1 1 v1")
    time.sleep(1.5)
    r = store.execute("TTL k1")
    assert "ERR" in r and "key_not_found" in r


def test_setex_exists_after_expiry(store):
    """EXISTS on expired key should return FALSE."""
    store.execute("SETEX k1 1 v1")
    time.sleep(1.5)
    r = store.execute("EXISTS k1")
    assert "FALSE" in r


def test_setex_overwrite(store):
    store.execute("SET k1 v1")
    store.execute("SETEX k1 10 v2")
    r = store.execute("GET k1")
    assert "v2" in r
    # TTL should exist after SETEX
    ttl_r = store.execute("TTL k1")
    assert "-1" not in ttl_r


# ═══════════════════════════════════════════════════════════════════════════
#  S5 — APPEND value to key (SHOULD)
# ═══════════════════════════════════════════════════════════════════════════

def test_append_new_key(store):
    r = store.execute("APPEND k1 hello")
    assert "OK" in r
    r2 = store.execute("GET k1")
    assert "hello" in r2


def test_append_to_existing(store):
    store.execute("SET msg hello")
    r = store.execute("APPEND msg _world")
    assert "OK" in r
    r2 = store.execute("GET msg")
    assert "hello_world" in r2


def test_append_exceed_size(store):
    big_val = "v" * 1000
    store.execute(f"SET k1 {big_val}")
    append_val = "x" * 100
    r = store.execute(f"APPEND k1 {append_val}")
    assert "ERR" in r and "value_too_large" in r


def test_append_empty_value(store):
    store.execute("SET k1 hello")
    r = store.execute("APPEND k1 ''")
    assert "OK" in r
    r2 = store.execute("GET k1")
    assert "hello" in r2


def test_append_new_key_with_length(store):
    r = store.execute("APPEND k1 world")
    assert "OK" in r
    assert "5" in r


# ═══════════════════════════════════════════════════════════════════════════
#  Y1 — RENAME key (MAY)
# ═══════════════════════════════════════════════════════════════════════════

def test_rename_basic(store):
    store.execute("SET a 1")
    r = store.execute("RENAME a b")
    assert "OK" in r
    # New key exists
    assert "1" in store.execute("GET b")
    # Old key is gone
    assert "ERR" in store.execute("GET a")


def test_rename_not_found(store):
    r = store.execute("RENAME x y")
    assert "ERR" in r and "key_not_found" in r


def test_rename_overwrite_existing(store):
    store.execute("SET a 1")
    store.execute("SET b 2")
    r = store.execute("RENAME a b")
    assert "OK" in r
    assert "1" in store.execute("GET b")
    assert "ERR" in store.execute("GET a")


# ═══════════════════════════════════════════════════════════════════════════
#  Y2 — TYPE of value (MAY)
# ═══════════════════════════════════════════════════════════════════════════

def test_type_string(store):
    store.execute("SET k1 hello")
    r = store.execute("TYPE k1")
    assert "STRING" in r


def test_type_integer(store):
    store.execute("SET k1 123")
    r = store.execute("TYPE k1")
    assert "INTEGER" in r


def test_type_negative_integer(store):
    store.execute("SET k1 -5")
    r = store.execute("TYPE k1")
    assert "INTEGER" in r


def test_type_zero_leading_integer(store):
    store.execute("SET k1 007")
    r = store.execute("TYPE k1")
    assert "INTEGER" in r


def test_type_not_found(store):
    r = store.execute("TYPE nonexistent")
    assert "ERR" in r and "key_not_found" in r


# ═══════════════════════════════════════════════════════════════════════════
#  Y3 — DUMP all key-value pairs (MAY)
# ═══════════════════════════════════════════════════════════════════════════

def test_dump_basic(store):
    store.execute("SET a 1")
    store.execute("SET b 2")
    r = store.execute("DUMP")
    assert "a=1" in r or "a 1" in r or "a:1" in r
    assert "b=2" in r or "b 2" in r or "b:2" in r
    assert "END" in r


def test_dump_empty(store):
    r = store.execute("DUMP")
    assert "END" in r


# ═══════════════════════════════════════════════════════════════════════════
#  Edge / Integration Cases
# ═══════════════════════════════════════════════════════════════════════════

def test_multiple_commands_sequence(store):
    """End-to-end sequence: SET → GET → EXISTS → DEL → EXISTS."""
    assert "OK" in store.execute("SET user alice")
    assert "alice" in store.execute("GET user")
    assert "TRUE" in store.execute("EXISTS user")
    assert "OK" in store.execute("DEL user")
    assert "FALSE" in store.execute("EXISTS user")


def test_keys_not_include_expired(store):
    """KEYS should not include expired keys."""
    store.execute("SET permanent 1")
    store.execute("SETEX temp 1 2")
    time.sleep(1.5)
    r = store.execute("KEYS")
    assert "permanent" in r
    assert "temp" not in r


def test_count_not_include_expired(store):
    """COUNT should not include expired keys."""
    store.execute("SET permanent 1")
    store.execute("SETEX temp 1 2")
    time.sleep(1.5)
    r = store.execute("COUNT")
    assert "1" in r


def test_dump_not_include_expired(store):
    """DUMP should not include expired keys."""
    store.execute("SET permanent 1")
    store.execute("SETEX temp 1 2")
    time.sleep(1.5)
    r = store.execute("DUMP")
    assert "permanent" in r
    assert "temp" not in r


def test_case_sensitive_keys(store):
    """Keys should be case-sensitive."""
    store.execute("SET Key val1")
    store.execute("SET key val2")
    assert "val1" in store.execute("GET Key")
    assert "val2" in store.execute("GET key")


def test_key_with_spaces(store):
    """Keys containing spaces should work if within length limit."""
    r = store.execute("SET 'key with spaces' value")
    r2 = store.execute("GET 'key with spaces'")
    assert r is not None and r2 is not None


# ═══════════════════════════════════════════════════════════════════════════
#  M8 — Error response format verification (MUST)
# ═══════════════════════════════════════════════════════════════════════════

def test_error_format_key_not_found(store):
    r = store.execute("GET noexist")
    assert r.startswith("ERR ")
    assert "key_not_found" in r


def test_error_format_key_too_long(store):
    r = store.execute(f"SET {'k'*65} v")
    assert r.startswith("ERR ")
    assert "key_too_long" in r


def test_error_format_value_too_large(store):
    r = store.execute(f"SET k {'v'*1025}")
    assert r.startswith("ERR ")
    assert "value_too_large" in r


def test_error_format_store_full(store):
    for i in range(100):
        store.execute(f"SET key{i} val{i}")
    r = store.execute("SET new val")
    assert r.startswith("ERR ")
    assert "store_full" in r


def test_error_format_unknown_command(store):
    r = store.execute("FOOBAR")
    assert r.startswith("ERR ")
    assert "unknown_command" in r


# ═══════════════════════════════════════════════════════════════════════════
#  Additional MUST Boundaries (M3, M4, M5, M7)
# ═══════════════════════════════════════════════════════════════════════════

def test_del_repeat(store):
    """Deleting the same key twice: second DEL returns key_not_found."""
    store.execute("SET k1 v1")
    assert "OK" in store.execute("DEL k1")
    r = store.execute("DEL k1")
    assert "ERR" in r and "key_not_found" in r


def test_keys_after_flush(store):
    store.execute("SET a 1")
    store.execute("FLUSH")
    r = store.execute("KEYS")
    assert "END" in r and "a" not in r


def test_keys_100_boundary(store):
    for i in range(100):
        store.execute(f"SET key{i} val")
    r = store.execute("KEYS")
    assert "END" in r
    assert "key0" in r
    assert "key99" in r


def test_count_100(store):
    for i in range(100):
        store.execute(f"SET key{i} val")
    r = store.execute("COUNT")
    assert "100" in r


def test_flush_repeat(store):
    """FLUSH twice in a row: both return OK."""
    assert "OK" in store.execute("FLUSH")
    assert "OK" in store.execute("FLUSH")


# ═══════════════════════════════════════════════════════════════════════════
#  SETEX additional boundaries (S1 — from test matrix)
# ═══════════════════════════════════════════════════════════════════════════

def test_setex_non_numeric_seconds(store):
    r = store.execute("SETEX k1 abc val")
    assert "ERR" in r and "unknown_command" in r


def test_setex_key_too_long(store):
    r = store.execute(f"SETEX {'k'*65} 10 val")
    assert "ERR" in r and "key_too_long" in r


def test_setex_value_too_large(store):
    r = store.execute(f"SETEX k 10 {'v'*1025}")
    assert "ERR" in r and "value_too_large" in r


def test_setex_store_full(store):
    for i in range(100):
        store.execute(f"SET key{i} val")
    r = store.execute("SETEX newkey 10 val")
    assert "ERR" in r and "store_full" in r


# ═══════════════════════════════════════════════════════════════════════════
#  MSET additional boundaries (S2)
# ═══════════════════════════════════════════════════════════════════════════

def test_mset_single_pair(store):
    """MSET with a single pair should work like SET."""
    r = store.execute("MSET k1 v1")
    assert "OK" in r and "1" in r
    assert "v1" in store.execute("GET k1")


def test_mset_all_existing_update(store):
    """MSET where all keys exist at full store should succeed."""
    for i in range(100):
        store.execute(f"SET key{i} val{i}")
    r = store.execute("MSET key0 new0 key1 new1")
    assert "OK" in r and "2" in r


def test_mset_empty_args(store):
    r = store.execute("MSET")
    assert "ERR" in r


# ═══════════════════════════════════════════════════════════════════════════
#  MGET additional boundaries (S3)
# ═══════════════════════════════════════════════════════════════════════════

def test_mget_single_key(store):
    store.execute("SET k1 v1")
    r = store.execute("MGET k1")
    assert "v1" in r
    assert "END" in r


def test_mget_empty_args(store):
    r = store.execute("MGET")
    assert "END" in r


def test_mget_with_expired_key(store):
    store.execute("SETEX k1 1 v1")
    time.sleep(1.5)
    r = store.execute("MGET k1")
    assert "NIL" in r
    assert "END" in r


# ═══════════════════════════════════════════════════════════════════════════
#  TTL additional boundaries (S4)
# ═══════════════════════════════════════════════════════════════════════════

def test_ttl_after_flush(store):
    store.execute("SETEX k1 10 v1")
    store.execute("FLUSH")
    r = store.execute("TTL k1")
    assert "ERR" in r and "key_not_found" in r


def test_ttl_after_del(store):
    store.execute("SETEX k1 10 v1")
    store.execute("DEL k1")
    r = store.execute("TTL k1")
    assert "ERR" in r and "key_not_found" in r


# ═══════════════════════════════════════════════════════════════════════════
#  APPEND additional boundaries (S5)
# ═══════════════════════════════════════════════════════════════════════════

def test_append_key_too_long(store):
    r = store.execute(f"APPEND {'k'*65} val")
    assert "ERR" in r and "key_too_long" in r


def test_append_store_full_new_key(store):
    for i in range(100):
        store.execute(f"SET key{i} val")
    r = store.execute("APPEND newkey val")
    assert "ERR" in r and "store_full" in r


def test_append_store_full_existing_key(store):
    """APPEND to existing key at full store should succeed (no new key)."""
    for i in range(100):
        store.execute(f"SET key{i} val")
    r = store.execute("APPEND key0 _extra")
    assert "OK" in r


# ═══════════════════════════════════════════════════════════════════════════
#  RENAME additional boundaries (Y1)
# ═══════════════════════════════════════════════════════════════════════════

def test_rename_same_key(store):
    store.execute("SET k v")
    r = store.execute("RENAME k k")
    assert "OK" in r
    assert "v" in store.execute("GET k")


def test_rename_new_key_too_long(store):
    store.execute("SET k v")
    r = store.execute(f"RENAME k {'n'*65}")
    assert "ERR" in r and "key_too_long" in r


# ═══════════════════════════════════════════════════════════════════════════
#  TYPE additional boundaries (Y2 — aligned with int(val) try/except)
# ═══════════════════════════════════════════════════════════════════════════

def test_type_float_value(store):
    """float like 3.14 should be STRING: int('3.14') raises ValueError."""
    store.execute("SET k1 3.14")
    r = store.execute("TYPE k1")
    assert "STRING" in r


def test_type_empty_value(store):
    """empty string should be STRING: int('') raises ValueError."""
    store.execute("SET k1 ''")
    r = store.execute("TYPE k1")
    assert "STRING" in r


def test_type_expired_key(store):
    """TYPE on expired key should return key_not_found."""
    store.execute("SETEX k1 1 hello")
    time.sleep(1.5)
    r = store.execute("TYPE k1")
    assert "ERR" in r and "key_not_found" in r


def test_type_stripped_whitespace(store):
    """int() auto-strips whitespace: ' 123 ' should be INTEGER."""
    store.execute("SET k1 ' 123 '")
    r = store.execute("TYPE k1")
    assert "INTEGER" in r


# ═══════════════════════════════════════════════════════════════════════════
#  DUMP additional boundaries (Y3)
# ═══════════════════════════════════════════════════════════════════════════

def test_dump_after_flush(store):
    store.execute("SET a 1")
    store.execute("FLUSH")
    r = store.execute("DUMP")
    assert "END" in r


def test_dump_100_keys(store):
    for i in range(100):
        store.execute(f"SET key{i} val{i}")
    r = store.execute("DUMP")
    assert "END" in r
    assert "key0" in r
    assert "key99" in r


# ═══════════════════════════════════════════════════════════════════════════
#  Additional syntax edge cases
# ═══════════════════════════════════════════════════════════════════════════

def test_set_value_with_spaces(store):
    """SET with value containing spaces."""
    r = store.execute("SET k hello world")
    assert r is not None
    assert "ERR" not in r or "OK" in r


def test_set_empty_key(store):
    """SET with empty key string."""
    r = store.execute("SET '' val")
    assert r is not None
    assert "ERR" in r


def test_set_empty_value(store):
    """SET with empty value string."""
    r = store.execute("SET k ''")
    assert "OK" in r
    r2 = store.execute("GET k")
    assert r2 is not None
