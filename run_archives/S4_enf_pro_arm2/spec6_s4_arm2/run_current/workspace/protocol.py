"""
KVP Protocol Implementation.

Implements the KVStore class according to the RFC-style KVP specification.
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
        self._store: dict[str, str] = {}        # key → value
        self._expiry: dict[str, float] = {}     # key → expiry_timestamp (epoch seconds)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(self, command: str) -> str:
        """
        Execute a single KVP command and return the response string (no trailing newline).

        Parse the command, dispatch to the appropriate handler,
        and return the response per the protocol specification.
        All errors are returned as "ERR ..." strings — execute() never raises.
        """
        if not command or not command.strip():
            return "ERR unknown_command"

        parts = command.strip().split()
        cmd = parts[0].upper()
        args = parts[1:]

        handlers = {
            "SET":    self._handle_set,
            "GET":    self._handle_get,
            "DEL":    self._handle_del,
            "KEYS":   self._handle_keys,
            "COUNT":  self._handle_count,
            "EXISTS": self._handle_exists,
            "FLUSH":  self._handle_flush,
            "MSET":   self._handle_mset,
            "MGET":   self._handle_mget,
            "TTL":    self._handle_ttl,
            "SETEX":  self._handle_setex,
            "APPEND": self._handle_append,
            "RENAME": self._handle_rename,
            "TYPE":   self._handle_type,
            "DUMP":   self._handle_dump,
        }

        handler = handlers.get(cmd)
        if handler is None:
            return "ERR unknown_command"

        return handler(args)

    # ------------------------------------------------------------------
    # MUST command handlers (M1–M12)
    # ------------------------------------------------------------------

    def _handle_set(self, args: list[str]) -> str:
        """SET <key> <value> — M1, M8, M10, M11, M12."""
        if len(args) < 2:
            return "ERR unknown_command"

        key = args[0]
        value = " ".join(args[1:])

        err = self._check_key(key)
        if err:
            return err

        err = self._check_value(value)
        if err:
            return err

        # Capacity check: only enforced for new keys (not updates)
        if key not in self._store and len(self._store) >= self.MAX_KEYS:
            return "ERR store_full"

        self._store[key] = value
        # Clear any existing expiry when doing a plain SET
        self._expiry.pop(key, None)
        return "OK"

    def _handle_get(self, args: list[str]) -> str:
        """GET <key> — M2."""
        if len(args) != 1:
            return "ERR unknown_command"

        key = args[0]
        val = self._get_valid(key)
        if val is None:
            return "ERR key_not_found"
        return val

    def _handle_del(self, args: list[str]) -> str:
        """DEL <key> — M3, M8."""
        if len(args) != 1:
            return "ERR unknown_command"

        key = args[0]
        if key not in self._store:
            return "ERR key_not_found"
        if self._is_expired(key):
            self._evict(key)
            return "ERR key_not_found"

        del self._store[key]
        self._expiry.pop(key, None)
        return "OK"

    def _handle_keys(self, args: list[str]) -> str:
        """KEYS — M4."""
        if len(args) != 0:
            return "ERR unknown_command"

        self._evict_expired()
        lines = list(self._store.keys()) + [self.END_MARKER]
        return "\n".join(lines)

    def _handle_count(self, args: list[str]) -> str:
        """COUNT — M5."""
        if len(args) != 0:
            return "ERR unknown_command"

        self._evict_expired()
        return f"COUNT {len(self._store)}"

    def _handle_exists(self, args: list[str]) -> str:
        """EXISTS <key> — M6."""
        if len(args) != 1:
            return "ERR unknown_command"

        key = args[0]
        val = self._get_valid(key)
        return "TRUE" if val is not None else "FALSE"

    def _handle_flush(self, args: list[str]) -> str:
        """FLUSH — M7."""
        if len(args) != 0:
            return "ERR unknown_command"

        self._store.clear()
        self._expiry.clear()
        return "OK"

    # ------------------------------------------------------------------
    # SHOULD command handlers (S1–S5)
    # ------------------------------------------------------------------

    def _handle_mset(self, args: list[str]) -> str:
        """MSET <key1> <value1> <key2> <value2> ... — S1."""
        if len(args) < 2 or len(args) % 2 != 0:
            return "ERR unknown_command"

        # Atomic validation phase — validate all pairs before writing
        new_keys = 0
        for i in range(0, len(args), 2):
            key, value = args[i], args[i + 1]
            err = self._check_key(key)
            if err:
                return err
            err = self._check_value(value)
            if err:
                return err
            if key not in self._store:
                new_keys += 1

        # Capacity check for new keys
        if len(self._store) + new_keys > self.MAX_KEYS:
            return "ERR store_full"

        # All checks passed — commit atomically
        for i in range(0, len(args), 2):
            key, value = args[i], args[i + 1]
            self._store[key] = value
            self._expiry.pop(key, None)

        n = len(args) // 2
        return f"OK {n}"

    def _handle_mget(self, args: list[str]) -> str:
        """MGET <key1> <key2> ... — S2."""
        if len(args) < 1:
            return "ERR unknown_command"

        lines = []
        for key in args:
            val = self._get_valid(key)
            lines.append(val if val is not None else "NIL")
        lines.append(self.END_MARKER)
        return "\n".join(lines)

    def _handle_ttl(self, args: list[str]) -> str:
        """TTL <key> — S3."""
        if len(args) != 1:
            return "ERR unknown_command"

        key = args[0]
        if key not in self._store:
            return "ERR key_not_found"
        if self._is_expired(key):
            self._evict(key)
            return "ERR key_not_found"

        if key not in self._expiry or self._expiry[key] is None:
            return "-1"
        remaining = int(self._expiry[key] - time.time())
        return str(max(0, remaining))

    def _handle_setex(self, args: list[str]) -> str:
        """SETEX <key> <seconds> <value> — S4."""
        if len(args) < 3:
            return "ERR unknown_command"

        key = args[0]
        seconds_str = args[1]
        value = " ".join(args[2:])

        # seconds must be a positive integer
        try:
            seconds = int(seconds_str)
        except ValueError:
            return "ERR unknown_command"
        if seconds <= 0:
            return "ERR unknown_command"

        err = self._check_key(key)
        if err:
            return err

        err = self._check_value(value)
        if err:
            return err

        # Capacity check for new keys
        if key not in self._store and len(self._store) >= self.MAX_KEYS:
            return "ERR store_full"

        self._store[key] = value
        self._expiry[key] = time.time() + seconds
        return "OK"

    def _handle_append(self, args: list[str]) -> str:
        """APPEND <key> <value> — S5."""
        if len(args) < 2:
            return "ERR unknown_command"

        key = args[0]
        value = " ".join(args[1:])

        err = self._check_key(key)
        if err:
            return err

        if key not in self._store:
            # Check expiry before treating as new
            if self._is_expired(key):
                self._evict(key)
            # If key still doesn't exist, create it
            if key not in self._store:
                if len(self._store) >= self.MAX_KEYS:
                    return "ERR store_full"
                self._store[key] = value
                return f"OK {len(self._store[key])}"
            # else: key was re-created after eviction? shouldn't happen,
            # but treat as existing key append
        else:
            if self._is_expired(key):
                self._evict(key)
                # After eviction, treat as new key
                if len(self._store) >= self.MAX_KEYS:
                    return "ERR store_full"
                self._store[key] = value
                return f"OK {len(self._store[key])}"

        new_value = self._store[key] + value
        if len(new_value) > self.MAX_VALUE_SIZE:
            return "ERR value_too_large"

        self._store[key] = new_value
        return f"OK {len(self._store[key])}"

    # ------------------------------------------------------------------
    # MAY command handlers (Y1–Y3)
    # ------------------------------------------------------------------

    def _handle_rename(self, args: list[str]) -> str:
        """RENAME <old_key> <new_key> — Y1."""
        if len(args) != 2:
            return "ERR unknown_command"

        old_key, new_key = args[0], args[1]

        # Old key must exist and not be expired
        if old_key not in self._store:
            return "ERR key_not_found"
        if self._is_expired(old_key):
            self._evict(old_key)
            return "ERR key_not_found"

        err = self._check_key(new_key)
        if err:
            return err

        # Move value
        self._store[new_key] = self._store.pop(old_key)

        # Migrate expiry if present
        if old_key in self._expiry:
            self._expiry[new_key] = self._expiry.pop(old_key)
        else:
            self._expiry.pop(new_key, None)

        return "OK"

    def _handle_type(self, args: list[str]) -> str:
        """TYPE <key> — Y2."""
        if len(args) != 1:
            return "ERR unknown_command"

        key = args[0]
        val = self._get_valid(key)
        if val is None:
            return "ERR key_not_found"

        # Try to interpret as integer
        try:
            int(val)
            return "INTEGER"
        except ValueError:
            return "STRING"

    def _handle_dump(self, args: list[str]) -> str:
        """DUMP — Y3 (no-argument form dumps all key-value pairs)."""
        if len(args) > 0:
            return "ERR unknown_command"

        self._evict_expired()
        lines = [f"{k}={v}" for k, v in self._store.items()]
        lines.append(self.END_MARKER)
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Constraint helpers
    # ------------------------------------------------------------------

    def _check_key(self, key: str) -> str | None:
        """Validate key against length constraint. Returns error string or None."""
        if len(key) > self.MAX_KEY_LENGTH:
            return "ERR key_too_long"
        return None

    def _check_value(self, value: str) -> str | None:
        """Validate value against size constraint. Returns error string or None."""
        if len(value) > self.MAX_VALUE_SIZE:
            return "ERR value_too_large"
        return None

    # ------------------------------------------------------------------
    # Expiry helpers
    # ------------------------------------------------------------------

    def _is_expired(self, key: str) -> bool:
        """Check whether a key has expired without evicting it."""
        if key not in self._expiry:
            return False
        return time.time() >= self._expiry[key]

    def _evict(self, key: str) -> None:
        """Evict a single expired key from store and expiry tracking."""
        self._store.pop(key, None)
        self._expiry.pop(key, None)

    def _evict_expired(self) -> None:
        """Batch-evict all expired keys."""
        now = time.time()
        expired = [k for k, t in self._expiry.items() if now >= t]
        for k in expired:
            self._store.pop(k, None)
            self._expiry.pop(k, None)

    def _get_valid(self, key: str) -> str | None:
        """
        Get the value for a key if it exists and has not expired.
        Evicts the key if it has expired. Returns None if not found or expired.
        """
        if key not in self._store:
            return None
        if self._is_expired(key):
            self._evict(key)
            return None
        return self._store[key]
