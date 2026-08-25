"""
KVP Protocol Implementation.

Implements the KVStore class according to the KVP (Key-Value Protocol) specification.
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

    def __init__(
        self,
        max_key_length: int = 64,
        max_value_size: int = 1024,
        max_keys: int = 100,
        delimiter: str = "\n",
    ):
        self.max_key_length = max_key_length
        self.max_value_size = max_value_size
        self.max_keys = max_keys
        self.delimiter = delimiter
        self._data: dict[str, str] = {}       # key -> value
        self._expiry: dict[str, float] = {}   # key -> expiration timestamp

    def execute(self, command: str) -> str:
        """
        Execute a single KVP command and return the response string.

        Parses the command line, dispatches to the appropriate handler,
        and returns the response per the protocol specification.
        The command should not include a trailing delimiter;
        the response does not include a trailing delimiter.
        """
        command = command.strip()
        if not command:
            return "ERR unknown_command"

        # Split into command name and the rest
        parts = command.split()
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
            "MSET": self._mset,
            "MGET": self._mget,
            "SETEX": self._setex,
            "TTL": self._ttl,
            "APPEND": self._append,
            "RENAME": self._rename,
            "TYPE": self._type,
            "DUMP": self._dump,
        }

        handler = handlers.get(cmd)
        if handler is None:
            return "ERR unknown_command"

        try:
            return handler(args)
        except (IndexError, ValueError):
            return "ERR unknown_command"

    # ── Expiry helpers ──────────────────────────────────────────────

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
        now = time.time()
        expired = [
            k for k, t in self._expiry.items()
            if t is not None and now > t
        ]
        for k in expired:
            self._data.pop(k, None)
            self._expiry.pop(k, None)

    # ── Validation helpers ──────────────────────────────────────────

    def _validate_key(self, key: str) -> str | None:
        """Validate key length. Returns error string or None if valid."""
        if len(key) > self.max_key_length:
            return "ERR key_too_long"
        return None

    def _validate_value(self, value: str) -> str | None:
        """Validate value size. Returns error string or None if valid."""
        if len(value) > self.max_value_size:
            return "ERR value_too_large"
        return None

    def _active_count(self) -> int:
        """Return the number of non-expired keys."""
        self._cleanup_expired()
        return len(self._data)

    # ── M1: SET <key> <value> ─────────────────────────────────────

    def _set(self, args):
        if len(args) < 2:
            return "ERR unknown_command"
        key = args[0]
        value = args[1]

        err = self._validate_key(key) or self._validate_value(value)
        if err:
            return err

        # Clean up if key exists and is expired
        self._is_expired(key)

        # Check store full only for new keys
        if key not in self._data and len(self._data) >= self.max_keys:
            return "ERR store_full"

        self._data[key] = value
        self._expiry.pop(key, None)  # Clear any previous expiry
        return "OK"

    # ── M2: GET <key> ─────────────────────────────────────────────

    def _get(self, args):
        if len(args) < 1:
            return "ERR unknown_command"
        key = args[0]

        err = self._validate_key(key)
        if err:
            return err

        if key not in self._data or self._is_expired(key):
            return "ERR key_not_found"
        return self._data[key]

    # ── M3: DEL <key> ─────────────────────────────────────────────

    def _del(self, args):
        if len(args) < 1:
            return "ERR unknown_command"
        key = args[0]

        if key not in self._data or self._is_expired(key):
            return "ERR key_not_found"

        del self._data[key]
        self._expiry.pop(key, None)
        return "OK"

    # ── M4: KEYS ──────────────────────────────────────────────────

    def _keys(self, args):
        self._cleanup_expired()
        keys = sorted(self._data.keys())
        return "\n".join(keys + [self.END_MARKER])

    # ── M5: COUNT ─────────────────────────────────────────────────

    def _count(self, args):
        self._cleanup_expired()
        return f"COUNT {len(self._data)}"

    # ── M6: EXISTS <key> ──────────────────────────────────────────

    def _exists(self, args):
        if len(args) < 1:
            return "ERR unknown_command"
        key = args[0]

        if key in self._data and not self._is_expired(key):
            return "TRUE"
        return "FALSE"

    # ── M7: FLUSH ─────────────────────────────────────────────────

    def _flush(self, args):
        self._data.clear()
        self._expiry.clear()
        return "OK"

    # ── S1: MSET <key1> <value1> ... ──────────────────────────────

    def _mset(self, args):
        if len(args) < 2 or len(args) % 2 != 0:
            return "ERR unknown_command"

        pairs = []
        for i in range(0, len(args), 2):
            key = args[i]
            value = args[i + 1]

            err = self._validate_key(key) or self._validate_value(value)
            if err:
                return err

            pairs.append((key, value))

        # Atomic validation: check store capacity for new keys
        self._cleanup_expired()
        new_keys = set(k for k, _ in pairs if k not in self._data)
        if len(self._data) + len(new_keys) > self.max_keys:
            return "ERR store_full"

        # All valid — commit
        for key, value in pairs:
            self._data[key] = value
            self._expiry.pop(key, None)

        return f"OK {len(pairs)}"

    # ── S2: MGET <key1> <key2> ... ────────────────────────────────

    def _mget(self, args):
        if len(args) < 1:
            return "ERR unknown_command"

        # Validate all keys first
        for key in args:
            err = self._validate_key(key)
            if err:
                return err

        lines = []
        for key in args:
            if key in self._data and not self._is_expired(key):
                lines.append(self._data[key])
            else:
                lines.append("NIL")

        lines.append(self.END_MARKER)
        return "\n".join(lines)

    # ── S3: TTL <key> ─────────────────────────────────────────────

    def _ttl(self, args):
        if len(args) < 1:
            return "ERR unknown_command"
        key = args[0]

        err = self._validate_key(key)
        if err:
            return err

        if key not in self._data or self._is_expired(key):
            return "ERR key_not_found"

        if key not in self._expiry or self._expiry[key] is None:
            return "-1"

        remaining = int(self._expiry[key] - time.time())
        return str(remaining)

    # ── S4: SETEX <key> <seconds> <value> ─────────────────────────

    def _setex(self, args):
        if len(args) < 3:
            return "ERR unknown_command"
        key = args[0]
        try:
            seconds = int(args[1])
        except ValueError:
            return "ERR unknown_command"
        value = args[2]

        err = self._validate_key(key) or self._validate_value(value)
        if err:
            return err

        if seconds <= 0:
            return "ERR unknown_command"

        self._is_expired(key)

        if key not in self._data and len(self._data) >= self.max_keys:
            return "ERR store_full"

        self._data[key] = value
        self._expiry[key] = time.time() + seconds
        return "OK"

    # ── S5: APPEND <key> <value> ──────────────────────────────────

    def _append(self, args):
        if len(args) < 2:
            return "ERR unknown_command"
        key = args[0]
        value = args[1]

        err = self._validate_key(key)
        if err:
            return err

        existing = key in self._data and not self._is_expired(key)
        if existing:
            new_value = self._data[key] + value
        else:
            if len(self._data) >= self.max_keys:
                return "ERR store_full"
            new_value = value

        err = self._validate_value(new_value)
        if err:
            return err

        self._data[key] = new_value
        self._expiry.pop(key, None)  # Clear any previous expiry
        return f"OK {len(new_value)}"

    # ── Y1: RENAME <old_key> <new_key> ────────────────────────────

    def _rename(self, args):
        if len(args) < 2:
            return "ERR unknown_command"
        old_key = args[0]
        new_key = args[1]

        if old_key not in self._data or self._is_expired(old_key):
            return "ERR key_not_found"

        err = self._validate_key(new_key)
        if err:
            return err

        self._data[new_key] = self._data.pop(old_key)
        if old_key in self._expiry:
            self._expiry[new_key] = self._expiry.pop(old_key)
        else:
            self._expiry.pop(new_key, None)

        return "OK"

    # ── Y2: TYPE <key> ────────────────────────────────────────────

    def _type(self, args):
        if len(args) < 1:
            return "ERR unknown_command"
        key = args[0]

        err = self._validate_key(key)
        if err:
            return err

        if key not in self._data or self._is_expired(key):
            return "ERR key_not_found"

        value = self._data[key]
        try:
            int(value)
            return "INTEGER"
        except ValueError:
            return "STRING"

    # ── Y3: DUMP ──────────────────────────────────────────────────

    def _dump(self, args):
        self._cleanup_expired()
        lines = [f"{k}={self._data[k]}" for k in sorted(self._data)]
        lines.append(self.END_MARKER)
        return "\n".join(lines)
