"""
KVP Protocol Implementation.

Implement the KVStore class according to the specification in protocol_spec.txt.
Commands: SET, GET, DEL, KEYS, COUNT, EXISTS, FLUSH
Optional: MSET, MGET, SETEX, TTL, APPEND, RENAME, TYPE, DUMP

Limits:
  MAX_KEY_LENGTH = 64
  MAX_VALUE_SIZE = 1024
  MAX_KEYS = 100
  END_MARKER = "END"
"""
import time


class KVStore:
    """In-memory key-value store implementing the KVP protocol."""

    MAX_KEY_LENGTH = 64
    MAX_VALUE_SIZE = 1024
    MAX_KEYS = 100
    END_MARKER = "END"

    def __init__(self):
        self._data = {}
        self._expiry = {}  # key -> expiration timestamp (or None)

    def execute(self, command: str) -> str:
        """
        Execute a single KVP command and return the response string.

        Parse the command, dispatch to the appropriate handler,
        and return the response per the protocol specification.
        """
        parts = command.strip().split()
        if not parts:
            return "ERR unknown_command"

        cmd = parts[0].upper()
        args = parts[1:]

        handlers = {
            "SET": self._set,
            "GET": self._get,
            "DEL": self._del,
            "KEYS": self._keys,
            "COUNT": self._count,
            "EXISTS": self._exists,
            "FLUSH": self._flush,
            "APPEND": self._append,
            "MSET": self._mset,
            "MGET": self._mget,
            "TTL": self._ttl,
            "SETEX": self._setex,
        }

        handler = handlers.get(cmd)
        if handler:
            return handler(args)
        return "ERR unknown_command"

    # ── Helper Methods ──────────────────────────────────────────────────

    def _is_expired(self, key: str) -> bool:
        """Check if a key has expired and clean it up if so."""
        if key in self._expiry and self._expiry[key] is not None:
            if time.time() > self._expiry[key]:
                del self._data[key]
                del self._expiry[key]
                return True
        return False

    def _cleanup_expired(self):
        """Batch-clean all expired keys. Called before KEYS and COUNT."""
        expired = [
            k for k in self._data
            if self._expiry.get(k) is not None and time.time() > self._expiry[k]
        ]
        for k in expired:
            del self._data[k]
            del self._expiry[k]

    # ── MUST Command Handlers ───────────────────────────────────────────

    def _set(self, args: list) -> str:
        """SET <key> <value> — store a key-value pair."""
        if len(args) < 2:
            return "ERR unknown_command"
        key = args[0]
        value = " ".join(args[1:])

        if len(key) > self.MAX_KEY_LENGTH:
            return "ERR key_too_long"
        if len(value) > self.MAX_VALUE_SIZE:
            return "ERR value_too_large"
        if key not in self._data and len(self._data) >= self.MAX_KEYS:
            return "ERR store_full"

        self._data[key] = value
        return "OK"

    def _get(self, args: list) -> str:
        """GET <key> — retrieve a stored value."""
        if len(args) != 1:
            return "ERR unknown_command"
        key = args[0]
        self._is_expired(key)
        if key not in self._data:
            return "ERR key_not_found"
        return self._data[key]

    def _del(self, args: list) -> str:
        """DEL <key> — remove a key."""
        if len(args) != 1:
            return "ERR unknown_command"
        key = args[0]
        self._is_expired(key)
        if key not in self._data:
            return "ERR key_not_found"
        del self._data[key]
        self._expiry.pop(key, None)
        return "OK"

    def _keys(self, args: list) -> str:
        """KEYS — list all stored keys, one per line, terminated by END."""
        self._cleanup_expired()
        keys = list(self._data.keys())
        if not keys:
            return self.END_MARKER
        return "\n".join(keys + [self.END_MARKER])

    def _count(self, args: list) -> str:
        """COUNT — return the total number of stored keys."""
        self._cleanup_expired()
        return f"COUNT {len(self._data)}"

    def _exists(self, args: list) -> str:
        """EXISTS <key> — check whether a key exists."""
        if len(args) != 1:
            return "ERR unknown_command"
        key = args[0]
        self._is_expired(key)
        return "TRUE" if key in self._data else "FALSE"

    def _flush(self, args: list) -> str:
        """FLUSH — remove all keys and return OK."""
        self._data.clear()
        self._expiry.clear()
        return "OK"

    # ── SHOULD Command Handlers ─────────────────────────────────────────

    def _append(self, args: list) -> str:
        """APPEND <key> <suffix> — append data to an existing key's value."""
        if len(args) < 2:
            return "ERR unknown_command"
        key = args[0]
        suffix = " ".join(args[1:])
        self._is_expired(key)

        if key in self._data:
            new_value = self._data[key] + suffix
            if len(new_value) > self.MAX_VALUE_SIZE:
                return "ERR value_too_large"
            self._data[key] = new_value
            return f"OK {len(new_value)}"
        else:
            if len(suffix) > self.MAX_VALUE_SIZE:
                return "ERR value_too_large"
            if len(self._data) >= self.MAX_KEYS:
                return "ERR store_full"
            self._data[key] = suffix
            return f"OK {len(suffix)}"

    def _mset(self, args: list) -> str:
        """MSET <k1> <v1> <k2> <v2> ... — set multiple keys atomically."""
        if len(args) < 2 or len(args) % 2 != 0:
            return "ERR unknown_command"

        # Parse into key-value pairs
        pairs = [(args[i], args[i + 1]) for i in range(0, len(args), 2)]

        # Validate all pairs first (atomic)
        for key, value in pairs:
            if len(key) > self.MAX_KEY_LENGTH:
                return "ERR key_too_long"
            if len(value) > self.MAX_VALUE_SIZE:
                return "ERR value_too_large"

        # Capacity check: count new keys
        new_keys = sum(1 for k, _ in pairs if k not in self._data)
        if len(self._data) + new_keys > self.MAX_KEYS:
            return "ERR store_full"

        # Write all pairs
        for key, value in pairs:
            self._data[key] = value

        return f"OK {len(pairs)}"

    def _ttl(self, args: list) -> str:
        """TTL <key> — return remaining TTL seconds, -1 if no expiry, ERR if not found."""
        if len(args) != 1:
            return "ERR unknown_command"
        key = args[0]
        self._is_expired(key)
        if key not in self._data:
            return "ERR key_not_found"
        expiry = self._expiry.get(key)
        if expiry is None:
            return "-1"
        remaining = int(expiry - time.time())
        return str(remaining)

    def _setex(self, args: list) -> str:
        """SETEX <key> <seconds> <value> — set key with expiry in seconds."""
        if len(args) < 3:
            return "ERR unknown_command"
        key = args[0]
        try:
            seconds = int(args[1])
        except ValueError:
            return "ERR unknown_command"
        value = " ".join(args[2:])

        if len(key) > self.MAX_KEY_LENGTH:
            return "ERR key_too_long"
        if len(value) > self.MAX_VALUE_SIZE:
            return "ERR value_too_large"
        if key not in self._data and len(self._data) >= self.MAX_KEYS:
            return "ERR store_full"

        self._data[key] = value
        self._expiry[key] = time.time() + seconds
        return "OK"

    def _mget(self, args: list) -> str:
        """MGET <k1> <k2> ... — retrieve multiple values."""
        if len(args) == 0:
            return "ERR unknown_command"

        lines = []
        for key in args:
            self._is_expired(key)
            if key in self._data:
                lines.append(self._data[key])
            else:
                lines.append("NIL")
        lines.append(self.END_MARKER)
        return "\n".join(lines)
