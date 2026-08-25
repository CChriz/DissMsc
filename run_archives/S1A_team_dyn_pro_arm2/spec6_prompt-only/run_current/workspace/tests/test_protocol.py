"""
Tests for the KVP protocol implementation.
Tests cover 15 of the 20 requirements. The remaining 5 must be derived from spec.
"""
import pytest
import time
from protocol import KVStore


@pytest.fixture
def store():
    return KVStore()


# ── M1: SET stores value ──────────────────────────────────────────────
def test_set_returns_ok(store):
    r = store.execute("SET foo bar")
    assert "OK" in r


# ── M2: GET returns value or ERR ─────────────────────────────────────
def test_get_existing_key(store):
    store.execute("SET hello world")
    r = store.execute("GET hello")
    assert "world" in r


def test_get_missing_key(store):
    r = store.execute("GET noexist")
    assert "ERR" in r and "key_not_found" in r


# ── M3: DEL removes key ──────────────────────────────────────────────
def test_del_existing_key(store):
    store.execute("SET temp val")
    r = store.execute("DEL temp")
    assert "OK" in r
    r2 = store.execute("GET temp")
    assert "ERR" in r2


# ── M4: KEYS lists keys ──────────────────────────────────────────────
def test_keys_lists_all(store):
    store.execute("SET a 1")
    store.execute("SET b 2")
    r = store.execute("KEYS")
    assert "a" in r and "b" in r and "END" in r


# ── M5: COUNT returns count ──────────────────────────────────────────
def test_count_after_sets(store):
    store.execute("SET x 1")
    store.execute("SET y 2")
    r = store.execute("COUNT")
    assert "2" in r


# ── M6: EXISTS TRUE/FALSE ────────────────────────────────────────────
def test_exists_true(store):
    store.execute("SET present val")
    r = store.execute("EXISTS present")
    assert "TRUE" in r


def test_exists_false(store):
    r = store.execute("EXISTS absent")
    assert "FALSE" in r


# ── M7: FLUSH clears all ─────────────────────────────────────────────
def test_flush_clears_store(store):
    store.execute("SET a 1")
    store.execute("SET b 2")
    r = store.execute("FLUSH")
    assert "OK" in r
    r2 = store.execute("COUNT")
    assert "0" in r2


# ── M9: unknown command ──────────────────────────────────────────────────
def test_unknown_command(store):
    r = store.execute("BADCMD xyz")
    assert "ERR" in r and "unknown_command" in r


# ── M10: key too long ────────────────────────────────────────────────────
def test_key_too_long(store):
    long_key = "k" * (64 + 5)
    r = store.execute(f"SET {long_key} val")
    assert "ERR" in r and "key_too_long" in r


# ── M11: value too large ─────────────────────────────────────────────────
def test_value_too_large(store):
    big_val = "v" * (1024 + 5)
    r = store.execute(f"SET k {big_val}")
    assert "ERR" in r and "value_too_large" in r


# ── M12: store full ──────────────────────────────────────────────────────
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


# ── M3 (supplement): DEL on non-existing key ─────────────────────────
def test_del_missing_key(store):
    r = store.execute("DEL ghost")
    assert r == "ERR key_not_found"


# ── M4 (supplement): KEYS edge cases ─────────────────────────────────
def test_keys_empty_store(store):
    r = store.execute("KEYS")
    assert r == "END"


def test_keys_single_key(store):
    store.execute("SET solo 1")
    r = store.execute("KEYS")
    assert r == "solo\nEND"


# ── M5 (supplement): COUNT edge cases ────────────────────────────────
def test_count_zero_on_empty(store):
    r = store.execute("COUNT")
    assert r == "COUNT 0"


def test_count_after_delete(store):
    store.execute("SET a 1")
    store.execute("SET b 2")
    store.execute("DEL a")
    r = store.execute("COUNT")
    assert r == "COUNT 1"


# ── M8 (supplement): explicit OK on SET and DEL ──────────────────────
def test_set_returns_exact_ok(store):
    r = store.execute("SET exact_key exact_val")
    assert r == "OK"


def test_del_returns_exact_ok(store):
    store.execute("SET to_delete val")
    r = store.execute("DEL to_delete")
    assert r == "OK"


# ── M9 (supplement): empty / whitespace command ──────────────────────
def test_empty_command(store):
    r = store.execute("")
    assert r == "ERR unknown_command"


def test_whitespace_only_command(store):
    r = store.execute("   ")
    assert r == "ERR unknown_command"


def test_case_insensitive_command(store):
    store.execute("SET hello world")
    r = store.execute("get hello")
    assert r == "world"
    r2 = store.execute("Get hello")
    assert r2 == "world"


# ── M10 (supplement): key at exact boundary ──────────────────────────
def test_key_exactly_max_length(store):
    key64 = "k" * 64
    r = store.execute(f"SET {key64} val")
    assert r == "OK"
    r2 = store.execute(f"GET {key64}")
    assert r2 == "val"


# ── M11 (supplement): value at exact boundary ────────────────────────
def test_value_exactly_max_size(store):
    val1024 = "v" * 1024
    r = store.execute(f"SET k {val1024}")
    assert r == "OK"
    r2 = store.execute("GET k")
    assert r2 == val1024


# ── S1: MSET ─────────────────────────────────────────────────────────
def test_mset_basic(store):
    r = store.execute("MSET a 1 b 2 c 3")
    assert r == "OK 3"
    assert store.execute("GET a") == "1"
    assert store.execute("GET b") == "2"
    assert store.execute("GET c") == "3"


def test_mset_odd_args(store):
    r = store.execute("MSET a 1 b")
    assert r == "ERR unknown_command"


def test_mset_key_too_long(store):
    long_key = "k" * 65
    r = store.execute(f"MSET {long_key} val x y")
    assert r == "ERR key_too_long"


def test_mset_value_too_large(store):
    big_val = "v" * 1025
    r = store.execute(f"MSET k {big_val} x y")
    assert r == "ERR value_too_large"


def test_mset_store_full(store):
    for i in range(100):
        store.execute(f"SET key{i} val{i}")
    r = store.execute("MSET new1 v1 new2 v2")
    assert r == "ERR store_full"


def test_mset_atomic_rollback(store):
    """MSET should roll back all changes if validation fails."""
    for i in range(99):
        store.execute(f"SET key{i} val{i}")
    # Trying to add 2 new keys when only 1 slot remains
    r = store.execute("MSET new1 v1 new2 v2")
    assert r == "ERR store_full"
    # new1 should NOT be stored (atomic rollback)
    assert store.execute("EXISTS new1") == "FALSE"


# ── S2: MGET ─────────────────────────────────────────────────────────
def test_mget_basic(store):
    store.execute("SET a 1")
    store.execute("SET b 2")
    r = store.execute("MGET a b")
    assert r == "1\n2\nEND"


def test_mget_with_missing(store):
    store.execute("SET a 1")
    r = store.execute("MGET a ghost b")
    assert r == "1\nNIL\nNIL\nEND"


def test_mget_no_args(store):
    r = store.execute("MGET")
    assert r == "ERR unknown_command"


# ── S4: SETEX ────────────────────────────────────────────────────────
def test_setex_basic(store):
    r = store.execute("SETEX temp 3600 myvalue")
    assert r == "OK"
    assert store.execute("GET temp") == "myvalue"


def test_setex_with_expiry(store):
    """SETEX with very short TTL; key should expire."""
    store.execute("SETEX ephemeral 1 short_lived")
    assert store.execute("EXISTS ephemeral") == "TRUE"
    time.sleep(1.1)
    assert store.execute("EXISTS ephemeral") == "FALSE"


def test_setex_invalid_seconds_non_numeric(store):
    r = store.execute("SETEX k abc val")
    assert r == "ERR invalid_seconds"


def test_setex_invalid_seconds_zero(store):
    r = store.execute("SETEX k 0 val")
    assert r == "ERR invalid_seconds"


def test_setex_invalid_seconds_negative(store):
    r = store.execute("SETEX k -5 val")
    assert r == "ERR invalid_seconds"


def test_setex_key_too_long(store):
    long_key = "k" * 65
    r = store.execute(f"SETEX {long_key} 100 v")
    assert r == "ERR key_too_long"


def test_setex_value_too_large(store):
    big_val = "v" * 1025
    r = store.execute(f"SETEX k 100 {big_val}")
    assert r == "ERR value_too_large"


def test_setex_store_full(store):
    for i in range(100):
        store.execute(f"SET key{i} val{i}")
    r = store.execute("SETEX overflow 100 val")
    assert r == "ERR store_full"


# ── S5: APPEND (supplement) ──────────────────────────────────────────
def test_append_to_new_key(store):
    r = store.execute("APPEND newkey hello")
    assert r == "OK 5"
    assert store.execute("GET newkey") == "hello"


def test_append_exceeding_value_limit(store):
    base = "a" * 1000
    store.execute("SET k " + base)
    append_val = "b" * 30
    r = store.execute(f"APPEND k {append_val}")
    assert r == "ERR value_too_large"


def test_append_at_capacity(store):
    for i in range(100):
        store.execute(f"SET key{i} val{i}")
    r = store.execute("APPEND newkey val")
    assert r == "ERR store_full"


def test_append_key_too_long(store):
    """APPEND with an overly long key that does not exist should fail M10."""
    long_key = "k" * 65
    r = store.execute(f"APPEND {long_key} val")
    assert r == "ERR key_too_long"


# ── M2 (supplement): GET returns exact value ─────────────────────────
def test_get_returns_exact_value(store):
    store.execute("SET greeting hello_world")
    r = store.execute("GET greeting")
    assert r == "hello_world"


# ── Edge: value containing command-like content ──────────────────────
def test_value_with_spaces(store):
    store.execute("SET msg hello beautiful world")
    r = store.execute("GET msg")
    assert r == "hello beautiful world"


def test_set_overwrite_existing(store):
    store.execute("SET k v1")
    store.execute("SET k v2")
    r = store.execute("GET k")
    assert r == "v2"
