"""
KVP Protocol Implementation.

Implement the KVStore class according to the specification in protocol_spec.txt.
Commands: SET, GET, DEL, KEYS, COUNT, EXISTS, FLUSH
Optional: APPEND, TTL, SETEX

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

    # ── Command Dispatcher ──────────────────────────────────────────

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

        if cmd == "SET" and len(args) == 2:
            return self._cmd_set(args[0], args[1])
        elif cmd == "GET" and len(args) == 1:
            return self._cmd_get(args[0])
        elif cmd == "DEL" and len(args) == 1:
            return self._cmd_del(args[0])
        elif cmd == "KEYS" and len(args) == 0:
            return self._cmd_keys()
        elif cmd == "COUNT" and len(args) == 0:
            return self._cmd_count()
        elif cmd == "EXISTS" and len(args) == 1:
            return self._cmd_exists(args[0])
        elif cmd == "FLUSH" and len(args) == 0:
            return self._cmd_flush()
        elif cmd == "APPEND" and len(args) == 2:
            return self._cmd_append(args[0], args[1])
        elif cmd == "TTL" and len(args) == 1:
            return self._cmd_ttl(args[0])
        elif cmd == "SETEX" and len(args) == 3:
            return self._cmd_setex(args[0], args[1], args[2])
        else:
            return "ERR unknown_command"

    # ── Expiry Helpers ──────────────────────────────────────────────

    def _is_expired(self, key: str) -> bool:
        """Check if a key has expired and clean it up if so."""
        if key in self._expiry and self._expiry[key] is not None:
            if time.time() > self._expiry[key]:
                del self._data[key]
                del self._expiry[key]
                return True
        return False

    def _clean_expired(self) -> None:
        """Clean up all expired keys."""
        for key in list(self._data.keys()):
            self._is_expired(key)

    # ── MUST Commands ───────────────────────────────────────────────

    def _cmd_set(self, key: str, value: str) -> str:
        """M1: SET <key> <value> — store a key-value pair."""
        if len(key) > self.MAX_KEY_LENGTH:
            return "ERR key_too_long"
        if len(value) > self.MAX_VALUE_SIZE:
            return "ERR value_too_large"
        if key not in self._data and len(self._data) >= self.MAX_KEYS:
            return "ERR store_full"

        self._data[key] = value
        # SET clears any existing TTL
        self._expiry.pop(key, None)
        return "OK"

    def _cmd_get(self, key: str) -> str:
        """M2: GET <key> — retrieve a value."""
        self._is_expired(key)
        if key in self._data:
            return self._data[key]
        return "ERR key_not_found"

    def _cmd_del(self, key: str) -> str:
        """M3: DEL <key> — remove a key."""
        self._is_expired(key)
        if key in self._data:
            del self._data[key]
            self._expiry.pop(key, None)
            return "OK"
        return "ERR key_not_found"

    def _cmd_keys(self) -> str:
        """M4: KEYS — list all stored keys."""
        self._clean_expired()
        if not self._data:
            return self.END_MARKER
        keys = list(self._data.keys())
        return "\n".join(keys) + "\n" + self.END_MARKER

    def _cmd_count(self) -> str:
        """M5: COUNT — return the number of stored keys."""
        self._clean_expired()
        return f"COUNT {len(self._data)}"

    def _cmd_exists(self, key: str) -> str:
        """M6: EXISTS <key> — check if a key exists."""
        self._is_expired(key)
        return "TRUE" if key in self._data else "FALSE"

    def _cmd_flush(self) -> str:
        """M7: FLUSH — remove all keys."""
        self._data.clear()
        self._expiry.clear()
        return "OK"

    # ── SHOULD Commands ─────────────────────────────────────────────

    def _cmd_append(self, key: str, value: str) -> str:
        """S5: APPEND <key> <value> — append to existing value or create."""
        self._is_expired(key)

        if key in self._data:
            # Append to existing key
            new_value = self._data[key] + value
            if len(new_value) > self.MAX_VALUE_SIZE:
                return "ERR value_too_large"
            self._data[key] = new_value
            return f"OK {len(new_value)}"
        else:
            # New key
            if len(key) > self.MAX_KEY_LENGTH:
                return "ERR key_too_long"
            if len(value) > self.MAX_VALUE_SIZE:
                return "ERR value_too_large"
            if len(self._data) >= self.MAX_KEYS:
                return "ERR store_full"
            self._data[key] = value
            return f"OK {len(value)}"

    def _cmd_ttl(self, key: str) -> str:
        """S3: TTL <key> — return remaining time-to-live in seconds."""
        self._is_expired(key)
        if key not in self._data:
            return "ERR key_not_found"
        if key in self._expiry and self._expiry[key] is not None:
            remaining = int(self._expiry[key] - time.time())
            return str(max(0, remaining))
        return "-1"

    def _cmd_setex(self, key: str, seconds: str, value: str) -> str:
        """S4: SETEX <key> <seconds> <value> — set key with expiration."""
        if len(key) > self.MAX_KEY_LENGTH:
            return "ERR key_too_long"
        if len(value) > self.MAX_VALUE_SIZE:
            return "ERR value_too_large"

        try:
            sec = int(seconds)
        except ValueError:
            return "ERR unknown_command"

        if key not in self._data and len(self._data) >= self.MAX_KEYS:
            return "ERR store_full"

        self._data[key] = value
        self._expiry[key] = time.time() + sec
        return "OK"
