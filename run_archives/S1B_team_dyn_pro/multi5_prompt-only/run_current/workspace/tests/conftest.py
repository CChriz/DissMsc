"""Pytest fixtures for webapp tests."""
import pytest
from app.models import DatabaseConnection


@pytest.fixture(scope="session")
def db():
    """Create a database connection for testing.

    NOTE: This fixture creates a new connection for every test function.
    With many tests, this exhausts the connection pool on postgresql.
    """
    conn = DatabaseConnection(host="localhost", port=8080)
    conn.connect()
    yield conn
    conn.close()


@pytest.fixture
def sample_data():
    """Provide sample test data."""
    return {"query": "SELECT * FROM test_table", "expected_rows": 5}
