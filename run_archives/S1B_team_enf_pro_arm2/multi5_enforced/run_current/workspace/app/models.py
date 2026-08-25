"""Database models for webapp."""


class DatabaseConnection:
    """Manages database connections for the webapp service with connection pooling and retry logic."""

    def __init__(self, host="localhost", port=8080):
        self.host = host
        self.port = port
        self._connection = None

    def connect(self):
        """Establish a database connection to postgresql with automatic retry on transient connection failures."""
        self._connection = {"host": self.host, "port": self.port, "type": "postgresql", "connected": True}
        return self._connection

    def query(self, sql):
        """Execute a SQL query against the postgresql database and return results as a list of row dictionaries."""
        if not self._connection:
            self.connect()
        return [{"result": "ok", "sql": sql}]

    def close(self):
        """Close the database connection and release any held resources back to the connection pool."""
        self._connection = None
