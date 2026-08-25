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

    # ── Command Dispatch ───────────────────────────────────────────────

    def execute(self, command: str) -> str:
        """
        Execute a single KVP command and return the response string.

        Parse the command, dispatch to the appropriate handler,
        and return the response per the protocol specification.
        """
        stripped = command.strip()
        if not stripped:
            return "ERR unknown_command"

        parts = stripped.split()
        cmd = parts[0].upper()
        args = parts[1:]

        # Command dispatch table
        handlers = {
            "SET":    self._set,
            "GET":    self._get,
            "DEL":    self._del,
            "KEYS":   self._keys,
            "COUNT":  self._count,
            "EXISTS": self._exists,
            "FLUSH":  self._flush,
            "MSET":   self._mset,
            "MGET":   self._mget,
            "SETEX":  self._setex,
            "APPEND": self._append,
        }

        handler = handlers.get(cmd)
        if handler is None:
            return "ERR unknown_command"

        return handler(args)

    # ── Expiry Helpers ──────────────────────────────────────────────────

    def _is_expired(self, key: str) -> bool:
        """Check if a key has expired and clean it up if so."""
        if key in self._expiry and self._expiry[key] is not None:
            if time.time() > self._expiry[key]:
                del self._data[key]
                del self._expiry[key]
                return True
        return False

    def _cleanup_expired(self) -> None:
        """Remove all expired keys from the store."""
        expired = [
            k for k in list(self._expiry.keys())
            if self._expiry[k] is not None and time.time() > self._expiry[k]
        ]
        for k in expired:
            self._data.pop(k, None)
            self._expiry.pop(k, None)

    # ── MUST Command Handlers ──────────────────────────────────────────

    def _set(self, args: list) -> str:
        """SET <key> <value> — Store value under key."""
        if len(args) < 2:
            return "ERR unknown_command"

        key = args[0]
        value = ' '.join(args[1:])

        # M10: key length check
        if len(key) > self.MAX_KEY_LENGTH:
            return "ERR key_too_long"

        # M11: value size check
        if len(value) > self.MAX_VALUE_SIZE:
            return "ERR value_too_large"

        # Clean up if expired before checking capacity
        self._is_expired(key)

        # M12: capacity check (only for new keys)
        if key not in self._data and len(self._data) >= self.MAX_KEYS:
            return "ERR store_full"

        self._data[key] = value
        self._expiry.pop(key, None)
        return "OK"

    def _get(self, args: list) -> str:
        """GET <key> — Retrieve value for key."""
        if len(args) < 1:
            return "ERR unknown_command"

        key = args[0]
        self._is_expired(key)

        if key not in self._data:
            return "ERR key_not_found"

        return self._data[key]

    def _del(self, args: list) -> str:
        """DEL <key> — Remove key from store."""
        if len(args) < 1:
            return "ERR unknown_command"

        key = args[0]
        self._is_expired(key)

        if key not in self._data:
            return "ERR key_not_found"

        del self._data[key]
        self._expiry.pop(key, None)
        return "OK"

    def _keys(self, args: list) -> str:
        """KEYS — List all stored keys, one per line, terminated by END."""
        self._cleanup_expired()
        keys = list(self._data.keys())
        if not keys:
            return self.END_MARKER
        return '\n'.join(keys) + '\n' + self.END_MARKER

    def _count(self, args: list) -> str:
        """COUNT — Return the number of stored keys."""
        self._cleanup_expired()
        return f"COUNT {len(self._data)}"

    def _exists(self, args: list) -> str:
        """EXISTS <key> — Check if key exists."""
        if len(args) < 1:
            return "ERR unknown_command"

        key = args[0]
        self._is_expired(key)
        return "TRUE" if key in self._data else "FALSE"

    def _flush(self, args: list) -> str:
        """FLUSH — Remove all keys and expiry data."""
        self._data.clear()
        self._expiry.clear()
        return "OK"

    # ── SHOULD Command Handlers ────────────────────────────────────────

    def _mset(self, args: list) -> str:
        """MSET <k1> <v1> <k2> <v2> ... — Atomic batch set."""
        if len(args) < 2 or len(args) % 2 != 0:
            return "ERR unknown_command"

        # Parse pairs
        pairs = []
        for i in range(0, len(args), 2):
            pairs.append((args[i], args[i + 1]))

        # Phase 1: Validate all pairs
        new_keys_count = 0
        for k, v in pairs:
            if len(k) > self.MAX_KEY_LENGTH:
                return "ERR key_too_long"
            if len(v) > self.MAX_VALUE_SIZE:
                return "ERR value_too_large"
            self._is_expired(k)
            if k not in self._data:
                new_keys_count += 1

        # Check capacity
        current_count = len(self._data)
        # Count unique new keys (dedup within the batch itself)
        new_key_names = set()
        for k, v in pairs:
            if k not in self._data:
                new_key_names.add(k)
        if current_count + len(new_key_names) > self.MAX_KEYS:
            return "ERR store_full"

        # Phase 2: Commit all
        for k, v in pairs:
            self._data[k] = v
            self._expiry.pop(k, None)

        # Count unique keys affected
        return f"OK {len(pairs)}"

    def _mget(self, args: list) -> str:
        """MGET <k1> <k2> ... — Get multiple values."""
        if len(args) < 1:
            return "ERR unknown_command"

        lines = []
        for key in args:
            self._is_expired(key)
            if key in self._data:
                lines.append(self._data[key])
            else:
                lines.append("NIL")

        lines.append(self.END_MARKER)
        return '\n'.join(lines)

    def _setex(self, args: list) -> str:
        """SETEX <key> <seconds> <value> — Set with expiration."""
        if len(args) < 3:
            return "ERR unknown_command"

        key = args[0]
        seconds_str = args[1]
        value = ' '.join(args[2:])

        # Parse seconds
        try:
            seconds = int(seconds_str)
        except ValueError:
            return "ERR invalid_seconds"

        if seconds <= 0:
            return "ERR invalid_seconds"

        # Key length check
        if len(key) > self.MAX_KEY_LENGTH:
            return "ERR key_too_long"

        # Value size check
        if len(value) > self.MAX_VALUE_SIZE:
            return "ERR value_too_large"

        # Expired cleanup before capacity check
        self._is_expired(key)

        # Capacity check
        if key not in self._data and len(self._data) >= self.MAX_KEYS:
            return "ERR store_full"

        self._data[key] = value
        self._expiry[key] = time.time() + seconds
        return "OK"

    def _append(self, args: list) -> str:
        """APPEND <key> <value> — Append to existing or create."""
        if len(args) < 2:
            return "ERR unknown_command"

        key = args[0]
        value = ' '.join(args[1:])

        # M10: key length check
        if len(key) > self.MAX_KEY_LENGTH:
            return "ERR key_too_long"

        self._is_expired(key)

        if key in self._data:
            new_value = self._data[key] + value
        else:
            # Capacity check for new key
            if len(self._data) >= self.MAX_KEYS:
                return "ERR store_full"
            new_value = value

        # Value size check on the result
        if len(new_value) > self.MAX_VALUE_SIZE:
            return "ERR value_too_large"

        self._data[key] = new_value
        self._expiry.pop(key, None)
        return f"OK {len(new_value)}"
