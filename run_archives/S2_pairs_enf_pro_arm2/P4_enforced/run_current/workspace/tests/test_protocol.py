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


# ── S5: APPEND ───────────────────────────────────────────────────────
def test_append_to_existing(store):
    store.execute("SET msg hello")
    r = store.execute("APPEND msg _world")
    assert "OK" in r
    r2 = store.execute("GET msg")
    assert "hello_world" in r2
