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

        if cmd == "SET":
            return self._handle_set(args)
        elif cmd == "GET":
            return self._handle_get(args)
        elif cmd == "DEL":
            return self._handle_del(args)
        elif cmd == "KEYS":
            return self._handle_keys()
        elif cmd == "COUNT":
            return self._handle_count()
        elif cmd == "EXISTS":
            return self._handle_exists(args)
        elif cmd == "FLUSH":
            return self._handle_flush()
        elif cmd == "APPEND":
            return self._handle_append(args)
        elif cmd == "MSET":
            return self._handle_mset(args)
        elif cmd == "MGET":
            return self._handle_mget(args)
        elif cmd == "TTL":
            return self._handle_ttl(args)
        else:
            return "ERR unknown_command"

    # ── MUST command handlers ──────────────────────────────────────────

    def _handle_set(self, args):
        """SET <key> <value>"""
        if len(args) < 2:
            return "ERR key_not_found"
        key = args[0]
        value = " ".join(args[1:])

        # Validate key length
        if len(key) > self.MAX_KEY_LENGTH:
            return "ERR key_too_long"
        # Validate value size
        if len(value) > self.MAX_VALUE_SIZE:
            return "ERR value_too_large"
        # Check store capacity (only for new keys)
        if len(self._data) >= self.MAX_KEYS and key not in self._data:
            return "ERR store_full"

        self._data[key] = value
        return "OK"

    def _handle_get(self, args):
        """GET <key>"""
        if len(args) < 1:
            return "ERR key_not_found"
        key = args[0]
        self._is_expired(key)
        if key not in self._data:
            return "ERR key_not_found"
        return self._data[key]

    def _handle_del(self, args):
        """DEL <key>"""
        if len(args) < 1:
            return "ERR key_not_found"
        key = args[0]
        if key not in self._data:
            return "ERR key_not_found"
        del self._data[key]
        self._expiry.pop(key, None)
        return "OK"

    def _handle_keys(self):
        """KEYS — list all keys, one per line, terminated by END"""
        # Clean up expired keys first
        self._cleanup_expired()
        lines = list(self._data.keys())
        lines.append(self.END_MARKER)
        return "\n".join(lines)

    def _handle_count(self):
        """COUNT — return current key count"""
        self._cleanup_expired()
        return f"COUNT {len(self._data)}"

    def _handle_exists(self, args):
        """EXISTS <key> — return TRUE or FALSE"""
        if len(args) < 1:
            return "FALSE"
        key = args[0]
        self._is_expired(key)
        return "TRUE" if key in self._data else "FALSE"

    def _handle_flush(self):
        """FLUSH — clear all data and expiry"""
        self._data.clear()
        self._expiry.clear()
        return "OK"

    # ── Additional command handlers (test-covered) ─────────────────────

    def _handle_append(self, args):
        """APPEND <key> <value> — create if new, append if exists"""
        if len(args) < 2:
            return "ERR key_not_found"
        key = args[0]
        value_to_append = " ".join(args[1:])

        self._is_expired(key)

        if key in self._data:
            # Existing key: append and check value size
            new_value = self._data[key] + value_to_append
            if len(new_value) > self.MAX_VALUE_SIZE:
                return "ERR value_too_large"
            self._data[key] = new_value
            return f"OK {len(new_value)}"
        else:
            # New key: create (same constraints as SET)
            if len(key) > self.MAX_KEY_LENGTH:
                return "ERR key_too_long"
            if len(value_to_append) > self.MAX_VALUE_SIZE:
                return "ERR value_too_large"
            if len(self._data) >= self.MAX_KEYS:
                return "ERR store_full"
            self._data[key] = value_to_append
            return f"OK {len(value_to_append)}"

    # ── SHOULD command handlers ────────────────────────────────────────

    def _handle_mset(self, args):
        """MSET <k1> <v1> <k2> <v2> ..."""
        if len(args) % 2 != 0:
            return "ERR wrong_number_of_arguments"

        if len(args) == 0:
            return "OK 0"

        # Parse into key-value pairs
        pairs = [(args[i], args[i + 1]) for i in range(0, len(args), 2)]

        # Pre-validate all pairs
        new_keys = []
        for key, value in pairs:
            # Check key length
            if len(key) > self.MAX_KEY_LENGTH:
                return "ERR key_too_long"
            # Check value size
            if len(value) > self.MAX_VALUE_SIZE:
                return "ERR value_too_large"
            # Track keys that would be newly added
            if key not in self._data:
                new_keys.append(key)

        # Check capacity: all new keys must fit
        available_slots = self.MAX_KEYS - len(self._data)
        if len(new_keys) > available_slots:
            return "ERR store_full"

        # All validations passed — atomic write
        for key, value in pairs:
            self._data[key] = value

        return f"OK {len(pairs)}"

    def _handle_mget(self, args):
        """MGET <k1> <k2> ... — return value or NIL, terminated by END"""
        results = []
        for key in args:
            self._is_expired(key)
            results.append(self._data.get(key, "NIL"))
        results.append(self.END_MARKER)
        return "\n".join(results)

    def _handle_ttl(self, args):
        """TTL <key> — return remaining seconds, -1 if no TTL"""
        if len(args) < 1:
            return "ERR key_not_found"
        key = args[0]
        self._is_expired(key)
        if key not in self._data:
            return "ERR key_not_found"
        if key not in self._expiry or self._expiry[key] is None:
            return "-1"
        remaining = int(self._expiry[key] - time.time())
        return str(max(remaining, 0))

    # ── Helpers ─────────────────────────────────────────────────────────

    def _is_expired(self, key: str) -> bool:
        """Check if a key has expired and clean it up if so."""
        if key in self._expiry and self._expiry[key] is not None:
            if time.time() > self._expiry[key]:
                del self._data[key]
                del self._expiry[key]
                return True
        return False

    def _cleanup_expired(self):
        """Remove all expired keys."""
        expired_keys = []
        for key in list(self._expiry.keys()):
            if self._expiry[key] is not None and time.time() > self._expiry[key]:
                expired_keys.append(key)
        for key in expired_keys:
            self._data.pop(key, None)
            self._expiry.pop(key, None)
