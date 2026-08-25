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

    ERROR_KEY_NOT_FOUND = "ERR key_not_found"
    ERROR_KEY_TOO_LONG = "ERR key_too_long"
    ERROR_VALUE_TOO_LARGE = "ERR value_too_large"
    ERROR_STORE_FULL = "ERR store_full"
    ERROR_UNKNOWN_COMMAND = "ERR unknown_command"

    def __init__(self):
        self._data = {}
        self._expiry = {}  # key -> expiration timestamp (or None)
        self._lock = None  # Unused, kept for potential future use

    # ────────────────────── public API ──────────────────────

    def execute(self, command: str) -> str:
        """
        Execute a single KVP command and return the response string.

        Parse the command, dispatch to the appropriate handler,
        and return the response per the protocol specification.
        """
        stripped = command.strip()
        if not stripped:
            return ""

        parts = stripped.split()
        cmd = parts[0].upper()
        args = parts[1:]

        # Dispatch table
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
            "TTL": self._ttl,
            "SETEX": self._setex,
            "APPEND": self._append,
            "RENAME": self._rename,
            "TYPE": self._type,
            "DUMP": self._dump,
        }

        handler = handlers.get(cmd)
        if handler is None:
            return self.ERROR_UNKNOWN_COMMAND

        try:
            return handler(args, stripped)
        except Exception:
            return self.ERROR_UNKNOWN_COMMAND

    # ────────────────────── helper methods ──────────────────────

    def _is_expired(self, key: str) -> bool:
        """Check if a key has expired and clean it up if so."""
        if key in self._expiry and self._expiry[key] is not None:
            if time.time() >= self._expiry[key]:
                del self._data[key]
                del self._expiry[key]
                return True
        return False

    def _parse_set_like(self, args: list, raw: str) -> tuple:
        """
        Parse commands of form: CMD <key> <value>

        For SET, APPEND, SETEX (where the last arg is value that may contain spaces).
        Returns (key, value) or raises ValueError.
        """
        # Find the command and first arg (key) by splitting
        parts = raw.split(None, 2)  # split on whitespace, max 2 splits → [CMD, key, rest]
        if len(parts) < 2:
            raise ValueError("ERR unknown_command")
        key = parts[1]
        value = parts[2] if len(parts) > 2 else ""
        return key, value

    def _parse_setex(self, raw: str) -> tuple:
        """
        Parse SETEX <key> <seconds> <value>
        Returns (key, seconds_int, value) or raises ValueError.
        """
        parts = raw.split(None, 3)  # [SETEX, key, seconds, value]
        if len(parts) < 3:
            raise ValueError("ERR unknown_command")
        key = parts[1]
        try:
            seconds = int(parts[2])
        except ValueError:
            raise ValueError("ERR unknown_command")
        value = parts[3] if len(parts) > 3 else ""
        return key, seconds, value

    def _check_key_length(self, key: str) -> str or None:
        """Return error string if key is too long, else None."""
        if len(key) > self.MAX_KEY_LENGTH:
            return self.ERROR_KEY_TOO_LONG
        return None

    def _check_value_size(self, value: str) -> str or None:
        """Return error string if value is too large, else None."""
        if len(value) > self.MAX_VALUE_SIZE:
            return self.ERROR_VALUE_TOO_LARGE
        return None

    def _check_store_full(self, key: str) -> str or None:
        """
        Check if adding a new key would exceed MAX_KEYS.
        If the key already exists (update), no limit is triggered.
        Return error string if store is full, else None.
        """
        if key not in self._data and len(self._data) >= self.MAX_KEYS:
            return self.ERROR_STORE_FULL
        return None

    def _active_key_count(self) -> int:
        """Count non-expired keys."""
        self._cleanup_expired()
        return len(self._data)

    def _cleanup_expired(self):
        """Remove all expired keys."""
        now = time.time()
        expired_keys = [
            k for k, t in self._expiry.items()
            if t is not None and now >= t
        ]
        for k in expired_keys:
            self._data.pop(k, None)
            self._expiry.pop(k, None)

    # ────────────────────── MUST commands ──────────────────────

    def _set(self, args: list, raw: str) -> str:
        """SET <key> <value> — M1, M8, M10, M11, M12"""
        try:
            key, value = self._parse_set_like(args, raw)
        except ValueError:
            return self.ERROR_UNKNOWN_COMMAND

        # Validate key length
        err = self._check_key_length(key)
        if err:
            return err

        # Validate value size
        err = self._check_value_size(value)
        if err:
            return err

        # Check store capacity (only for new keys)
        err = self._check_store_full(key)
        if err:
            return err

        self._data[key] = value
        # Preserve TTL if key already existed, otherwise no TTL
        if key not in self._expiry:
            self._expiry[key] = None
        return "OK"

    def _get(self, args: list, raw: str) -> str:
        """GET <key> — M2, M10"""
        if not args:
            return self.ERROR_UNKNOWN_COMMAND
        key = args[0]

        err = self._check_key_length(key)
        if err:
            return err

        if self._is_expired(key) or key not in self._data:
            return self.ERROR_KEY_NOT_FOUND

        return self._data[key]

    def _del(self, args: list, raw: str) -> str:
        """DEL <key> — M3, M8, M10"""
        if not args:
            return self.ERROR_UNKNOWN_COMMAND
        key = args[0]

        err = self._check_key_length(key)
        if err:
            return err

        if self._is_expired(key) or key not in self._data:
            return self.ERROR_KEY_NOT_FOUND

        del self._data[key]
        self._expiry.pop(key, None)
        return "OK"

    def _keys(self, args: list, raw: str) -> str:
        """KEYS — M4"""
        self._cleanup_expired()
        if not self._data:
            return self.END_MARKER
        lines = list(self._data.keys()) + [self.END_MARKER]
        return "\n".join(lines)

    def _count(self, args: list, raw: str) -> str:
        """COUNT — M5"""
        n = self._active_key_count()
        return f"COUNT {n}"

    def _exists(self, args: list, raw: str) -> str:
        """EXISTS <key> — M6, M10"""
        if not args:
            return self.ERROR_UNKNOWN_COMMAND
        key = args[0]

        err = self._check_key_length(key)
        if err:
            return err

        if self._is_expired(key) or key not in self._data:
            return "FALSE"
        return "TRUE"

    def _flush(self, args: list, raw: str) -> str:
        """FLUSH — M7"""
        self._data.clear()
        self._expiry.clear()
        return "OK"

    # ────────────────────── SHOULD commands ──────────────────────

    def _mset(self, args: list, raw: str) -> str:
        """MSET <k1> <v1> <k2> <v2> ... — S1, M11, M12"""
        # Parse into key-value pairs
        # MSET parsing: tokens after command form alternating key-value pairs
        # where values can contain spaces. Strategy: split on whitespace,
        # then pair keys and values (values are single tokens in this simple protocol).
        # For values containing spaces, the protocol spec needs clarification.
        # Based on standard KVP convention, values in MSET are single tokens.
        tokens = raw.split()
        if len(tokens) < 3 or len(tokens) % 2 != 1:  # command + (key value)*
            return self.ERROR_UNKNOWN_COMMAND

        pairs = []
        for i in range(1, len(tokens), 2):
            key = tokens[i]
            value = tokens[i + 1] if i + 1 < len(tokens) else ""
            pairs.append((key, value))

        # Phase 1: validate all
        new_keys = set()
        for key, value in pairs:
            err = self._check_key_length(key)
            if err:
                return err
            err = self._check_value_size(value)
            if err:
                return err
            if key not in self._data:
                new_keys.add(key)

        # Check capacity for new keys
        if len(self._data) + len(new_keys) > self.MAX_KEYS:
            return self.ERROR_STORE_FULL

        # Phase 2: atomic write
        for key, value in pairs:
            self._data[key] = value
            if key not in self._expiry:
                self._expiry[key] = None

        return f"OK {len(pairs)}"

    def _mget(self, args: list, raw: str) -> str:
        """MGET <k1> <k2> ... — S2"""
        if not args:
            return self.ERROR_UNKNOWN_COMMAND

        results = []
        for key in args:
            if not self._is_expired(key) and key in self._data:
                results.append(self._data[key])
            else:
                results.append("NIL")

        results.append(self.END_MARKER)
        return "\n".join(results)

    def _ttl(self, args: list, raw: str) -> str:
        """TTL <key> — S3, M10"""
        if not args:
            return self.ERROR_UNKNOWN_COMMAND
        key = args[0]

        err = self._check_key_length(key)
        if err:
            return err

        if self._is_expired(key) or key not in self._data:
            return self.ERROR_KEY_NOT_FOUND

        expiry = self._expiry.get(key)
        if expiry is None:
            return "-1"

        remaining = int(expiry - time.time())
        return str(remaining)

    def _setex(self, args: list, raw: str) -> str:
        """SETEX <key> <seconds> <value> — S4, M10, M11, M12"""
        try:
            key, seconds, value = self._parse_setex(raw)
        except ValueError as e:
            return str(e)

        err = self._check_key_length(key)
        if err:
            return err
        err = self._check_value_size(value)
        if err:
            return err
        err = self._check_store_full(key)
        if err:
            return err

        self._data[key] = value
        self._expiry[key] = time.time() + seconds
        return "OK"

    def _append(self, args: list, raw: str) -> str:
        """APPEND <key> <value> — S5, M10, M11, M12"""
        try:
            key, value = self._parse_set_like(args, raw)
        except ValueError:
            return self.ERROR_UNKNOWN_COMMAND

        err = self._check_key_length(key)
        if err:
            return err

        # Check expiry for existing key
        self._is_expired(key)

        if key in self._data:
            # Append to existing value
            new_value = self._data[key] + value
            if len(new_value) > self.MAX_VALUE_SIZE:
                return self.ERROR_VALUE_TOO_LARGE
            self._data[key] = new_value
        else:
            # Create new key
            err = self._check_value_size(value)
            if err:
                return err
            err = self._check_store_full(key)
            if err:
                return err
            self._data[key] = value
            self._expiry[key] = None

        return f"OK {len(self._data[key])}"

    # ────────────────────── MAY commands ──────────────────────

    def _rename(self, args: list, raw: str) -> str:
        """RENAME <old_key> <new_key> — Y1, M10"""
        if len(args) < 2:
            return self.ERROR_UNKNOWN_COMMAND
        old_key = args[0]
        new_key = args[1]

        err = self._check_key_length(old_key)
        if err:
            return err
        err = self._check_key_length(new_key)
        if err:
            return err

        if self._is_expired(old_key) or old_key not in self._data:
            return self.ERROR_KEY_NOT_FOUND

        # Transfer value and TTL
        value = self._data.pop(old_key)
        ttl = self._expiry.pop(old_key, None)

        self._data[new_key] = value
        self._expiry[new_key] = ttl

        return "OK"

    def _type(self, args: list, raw: str) -> str:
        """TYPE <key> — Y2, M10"""
        if not args:
            return self.ERROR_UNKNOWN_COMMAND
        key = args[0]

        err = self._check_key_length(key)
        if err:
            return err

        if self._is_expired(key) or key not in self._data:
            return self.ERROR_KEY_NOT_FOUND

        value = self._data[key]
        try:
            int(value)
            return "INTEGER"
        except ValueError:
            return "STRING"

    def _dump(self, args: list, raw: str) -> str:
        """DUMP — Y3"""
        self._cleanup_expired()
        if not self._data:
            return self.END_MARKER
        lines = [f"{k}={v}" for k, v in self._data.items()]
        lines.append(self.END_MARKER)
        return "\n".join(lines)
