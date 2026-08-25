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

        # Dispatch to the appropriate command handler
        if cmd == "SET":
            return self._cmd_set(args)
        elif cmd == "GET":
            return self._cmd_get(args)
        elif cmd == "DEL":
            return self._cmd_del(args)
        elif cmd == "KEYS":
            return self._cmd_keys()
        elif cmd == "COUNT":
            return self._cmd_count()
        elif cmd == "EXISTS":
            return self._cmd_exists(args)
        elif cmd == "FLUSH":
            return self._cmd_flush()
        elif cmd == "MSET":
            return self._cmd_mset(args)
        elif cmd == "MGET":
            return self._cmd_mget(args)
        elif cmd == "TTL":
            return self._cmd_ttl(args)
        elif cmd == "SETEX":
            return self._cmd_setex(args)
        elif cmd == "APPEND":
            return self._cmd_append(args)
        elif cmd == "RENAME":
            return self._cmd_rename(args)
        elif cmd == "TYPE":
            return self._cmd_type(args)
        elif cmd == "DUMP":
            return self._cmd_dump()
        else:
            return "ERR unknown_command"

    def _is_expired(self, key: str) -> bool:
        """Check if a key has expired and clean it up if so."""
        if key in self._expiry and self._expiry[key] is not None:
            if time.time() > self._expiry[key]:
                del self._data[key]
                del self._expiry[key]
                return True
        return False

    # ── Command Handlers (MUST) ──────────────────────────────────────────

    def _cmd_set(self, args: list) -> str:
        """SET <key> <value> — M1 + M8 + M10 + M11 + M12"""
        if len(args) < 2:
            return "ERR unknown_command"

        key = args[0]
        value = args[1]

        # M10: check key length
        if len(key) > self.MAX_KEY_LENGTH:
            return "ERR key_too_long"

        # M11: check value size
        if len(value) > self.MAX_VALUE_SIZE:
            return "ERR value_too_large"

        # Check if key already exists (and is not expired)
        key_exists = key in self._data and not self._is_expired(key)

        # M12: capacity check for new keys only
        if not key_exists:
            self._cleanup_expired()
            if len(self._data) >= self.MAX_KEYS:
                return "ERR store_full"

        # Store the value
        self._data[key] = value
        self._expiry[key] = None  # No expiration for plain SET

        return "OK"

    def _cmd_get(self, args: list) -> str:
        """GET <key> — M2"""
        if len(args) < 1:
            return "ERR unknown_command"

        key = args[0]

        if key in self._data and not self._is_expired(key):
            return self._data[key]
        else:
            return "ERR key_not_found"

    def _cmd_del(self, args: list) -> str:
        """DEL <key> — M3 + M8"""
        if len(args) < 1:
            return "ERR unknown_command"

        key = args[0]

        if key in self._data and not self._is_expired(key):
            del self._data[key]
            if key in self._expiry:
                del self._expiry[key]
            return "OK"
        else:
            return "ERR key_not_found"

    def _cmd_keys(self) -> str:
        """KEYS — M4"""
        # Build list of non-expired keys
        active_keys = [
            key for key in self._data if not self._is_expired(key)
        ]
        if not active_keys:
            return self.END_MARKER
        return "\n".join(active_keys) + "\n" + self.END_MARKER

    def _cmd_count(self) -> str:
        """COUNT — M5"""
        # Count non-expired keys
        count = sum(1 for key in self._data if not self._is_expired(key))
        return f"COUNT {count}"

    def _cmd_exists(self, args: list) -> str:
        """EXISTS <key> — M6"""
        if len(args) < 1:
            return "ERR unknown_command"

        key = args[0]

        if key in self._data and not self._is_expired(key):
            return "TRUE"
        else:
            return "FALSE"

    def _cmd_flush(self) -> str:
        """FLUSH — M7"""
        self._data.clear()
        self._expiry.clear()
        return "OK"

    # ── Command Handlers (SHOULD) ────────────────────────────────────────

    def _cmd_mset(self, args: list) -> str:
        """MSET <key1> <value1> [<key2> <value2> ...] — S1"""
        if len(args) < 2 or len(args) % 2 != 0:
            return "ERR unknown_command"

        # Parse pairs
        pairs = [(args[i], args[i + 1]) for i in range(0, len(args), 2)]

        # ── Atomic validation phase (check only, no mutations) ──
        for key, value in pairs:
            if len(key) > self.MAX_KEY_LENGTH:
                return "ERR key_too_long"
            if len(value) > self.MAX_VALUE_SIZE:
                return "ERR value_too_large"

        # Capacity check: count new keys (not already present and not expired)
        new_keys = set()
        for key, _ in pairs:
            if key not in self._data or self._is_expired(key):
                new_keys.add(key)

        current_active = sum(1 for k in self._data if not self._is_expired(k))
        if current_active + len(new_keys) > self.MAX_KEYS:
            return "ERR store_full"

        # ── Atomic execution phase ──
        for key, value in pairs:
            self._data[key] = value
            self._expiry[key] = None

        return f"OK {len(pairs)}"

    def _cmd_mget(self, args: list) -> str:
        """MGET <key1> [<key2> ...] — S2"""
        if len(args) < 1:
            return "ERR unknown_command"

        lines = []
        for key in args:
            if key in self._data and not self._is_expired(key):
                lines.append(self._data[key])
            else:
                lines.append("NIL")
        lines.append(self.END_MARKER)
        return "\n".join(lines)

    def _cmd_ttl(self, args: list) -> str:
        """TTL <key> — S3"""
        if len(args) < 1:
            return "ERR unknown_command"

        key = args[0]
        if key not in self._data or self._is_expired(key):
            return "ERR key_not_found"

        if key in self._expiry and self._expiry[key] is not None:
            remaining = int(self._expiry[key] - time.time())
            if remaining < 0:
                return "0"
            return str(remaining)
        else:
            return "-1"

    def _cmd_setex(self, args: list) -> str:
        """SETEX <key> <seconds> <value> — S4"""
        if len(args) < 3:
            return "ERR unknown_command"

        key = args[0]
        try:
            seconds = int(args[1])
        except ValueError:
            return "ERR unknown_command"

        # value may contain spaces — join remaining args
        value = " ".join(args[2:])

        # Same validations as SET
        if len(key) > self.MAX_KEY_LENGTH:
            return "ERR key_too_long"
        if len(value) > self.MAX_VALUE_SIZE:
            return "ERR value_too_large"

        key_exists = key in self._data and not self._is_expired(key)
        if not key_exists:
            self._cleanup_expired()
            if len(self._data) >= self.MAX_KEYS:
                return "ERR store_full"

        self._data[key] = value
        self._expiry[key] = time.time() + seconds
        return "OK"

    def _cmd_append(self, args: list) -> str:
        """APPEND <key> <value> — S5"""
        if len(args) < 2:
            return "ERR unknown_command"

        key = args[0]
        # value may contain spaces — join remaining args
        value_to_append = " ".join(args[1:])

        key_exists = key in self._data and not self._is_expired(key)

        if key_exists:
            existing = self._data[key]
            new_value = existing + value_to_append
        else:
            new_value = value_to_append
            self._cleanup_expired()
            if len(self._data) >= self.MAX_KEYS:
                return "ERR store_full"

        if len(new_value) > self.MAX_VALUE_SIZE:
            return "ERR value_too_large"

        self._data[key] = new_value
        self._expiry[key] = None

        return f"OK {len(new_value)}"

    # ── Command Handlers (MAY) ───────────────────────────────────────────

    def _cmd_rename(self, args: list) -> str:
        """RENAME <old_key> <new_key> — Y1"""
        if len(args) < 2:
            return "ERR unknown_command"

        old_key = args[0]
        new_key = args[1]

        if old_key not in self._data or self._is_expired(old_key):
            return "ERR key_not_found"

        value = self._data[old_key]
        expiry = self._expiry.get(old_key, None)

        del self._data[old_key]
        self._expiry.pop(old_key, None)

        self._data[new_key] = value
        self._expiry[new_key] = expiry

        return "OK"

    def _cmd_type(self, args: list) -> str:
        """TYPE <key> — Y2"""
        if len(args) < 1:
            return "ERR unknown_command"

        key = args[0]
        if key not in self._data or self._is_expired(key):
            return "ERR key_not_found"

        value = self._data[key]
        try:
            int(value)
            return "INTEGER"
        except ValueError:
            return "STRING"

    def _cmd_dump(self) -> str:
        """DUMP — Y3"""
        lines = []
        for key in self._data:
            if not self._is_expired(key):
                lines.append(f"{key}={self._data[key]}")
        lines.append(self.END_MARKER)
        return "\n".join(lines)

    # ── Utility ──────────────────────────────────────────────────────────

    def _cleanup_expired(self) -> None:
        """Remove all expired keys from the store."""
        expired_keys = [
            key for key, exp in self._expiry.items()
            if exp is not None and time.time() > exp
        ]
        for key in expired_keys:
            if key in self._data:
                del self._data[key]
            del self._expiry[key]
