"""Tests for webapp models."""


def test_connection_creates(db):
    """Test that database connection is established."""
    assert db._connection is not None
    assert db._connection["connected"] is True


def test_connection_type(db):
    """Test database type is correct."""
    assert db._connection["type"] == "postgresql"


def test_query_returns_results(db):
    """Test that query returns results."""
    results = db.query("SELECT 1")
    assert len(results) > 0
    assert results[0]["result"] == "ok"


def test_close_clears_connection(db):
    """Test that closing clears the connection."""
    db.close()
    assert db._connection is None
