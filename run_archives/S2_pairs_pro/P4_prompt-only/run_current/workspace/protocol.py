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
import threading


class KVStore:
    """In-memory key-value store implementing the KVP protocol."""

    MAX_KEY_LENGTH = 64
    MAX_VALUE_SIZE = 1024
    MAX_KEYS = 100
    END_MARKER = "END"

    def __init__(self):
        self._data = {}
        self._expiry = {}  # key -> expiration timestamp (or None)
        self._lock = threading.Lock()

    # ── Public API ──────────────────────────────────────────────────────

    def execute(self, command: str) -> str:
        """
        Execute a single KVP command and return the response string.

        Parse the command, dispatch to the appropriate handler,
        and return the response per the protocol specification.
        """
        line = command.strip()
        if not line:
            return "ERR unknown_command"

        parts = line.split()
        cmd = parts[0].upper()
        args = parts[1:]

        # Lazy eviction of expired keys before every command
        self._evict_expired()

        # Dispatch table
        handlers = {
            'SET':    self._cmd_set,
            'GET':    self._cmd_get,
            'DEL':    self._cmd_del,
            'KEYS':   self._cmd_keys,
            'COUNT':  self._cmd_count,
            'EXISTS': self._cmd_exists,
            'FLUSH':  self._cmd_flush,
            'MSET':   self._cmd_mset,
            'MGET':   self._cmd_mget,
            'SETEX':  self._cmd_setex,
            'TTL':    self._cmd_ttl,
            'APPEND': self._cmd_append,
            'RENAME': self._cmd_rename,
            'TYPE':   self._cmd_type,
            'DUMP':   self._cmd_dump,
        }

        handler = handlers.get(cmd)
        if handler is None:
            return "ERR unknown_command"

        try:
            return handler(line, args)
        except Exception:
            return "ERR unknown_command"

    # ── Expiration ──────────────────────────────────────────────────────

    def _evict_expired(self):
        """Remove all expired keys from the store."""
        now = time.time()
        expired = [k for k, t in self._expiry.items() if t is not None and t <= now]
        for k in expired:
            self._data.pop(k, None)
            self._expiry.pop(k, None)

    def _is_expired(self, key: str) -> bool:
        """Check if a key has expired and clean it up if so."""
        if key in self._expiry and self._expiry[key] is not None:
            if time.time() > self._expiry[key]:
                del self._data[key]
                del self._expiry[key]
                return True
        return False

    # ── Validation helpers ──────────────────────────────────────────────

    def _check_key_length(self, key: str) -> str | None:
        """Return error string if key is too long, else None."""
        if len(key) > self.MAX_KEY_LENGTH:
            return "ERR key_too_long"
        return None

    def _check_value_size(self, value: str) -> str | None:
        """Return error string if value is too large (UTF-8 bytes), else None."""
        if len(value.encode('utf-8')) > self.MAX_VALUE_SIZE:
            return "ERR value_too_large"
        return None

    def _check_store_full(self, key: str) -> str | None:
        """Return error string if adding a new key would exceed capacity, else None."""
        if key not in self._data and len(self._data) >= self.MAX_KEYS:
            return "ERR store_full"
        return None

    # ── M1 + M8 + M10 + M11 + M12: SET ──────────────────────────────────

    def _cmd_set(self, raw_line: str, args: list[str]) -> str:
        if len(args) < 2:
            return "ERR unknown_command"
        key = args[0]
        # Value is everything after the key in the original line
        # Reconstruct: skip "SET " (4 chars) then skip the key
        value_start = raw_line.find(key) + len(key) + 1
        value = raw_line[value_start:] if value_start < len(raw_line) else ""

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
        # Clear any existing expiry for this key (SET overwrites without TTL)
        self._expiry.pop(key, None)
        return "OK"

    # ── M2: GET ─────────────────────────────────────────────────────────

    def _cmd_get(self, raw_line: str, args: list[str]) -> str:
        if len(args) < 1:
            return "ERR unknown_command"
        key = args[0]
        if key not in self._data:
            return "ERR key_not_found"
        if self._is_expired(key):
            return "ERR key_not_found"
        return self._data[key]

    # ── M3 + M8: DEL ────────────────────────────────────────────────────

    def _cmd_del(self, raw_line: str, args: list[str]) -> str:
        if len(args) < 1:
            return "ERR unknown_command"
        key = args[0]
        if key not in self._data:
            return "ERR key_not_found"
        if self._is_expired(key):
            return "ERR key_not_found"
        self._data.pop(key, None)
        self._expiry.pop(key, None)
        return "OK"

    # ── M4: KEYS ────────────────────────────────────────────────────────

    def _cmd_keys(self, raw_line: str, args: list[str]) -> str:
        keys = list(self._data.keys())
        if not keys:
            return self.END_MARKER
        return "\n".join(keys) + "\n" + self.END_MARKER

    # ── M5: COUNT ───────────────────────────────────────────────────────

    def _cmd_count(self, raw_line: str, args: list[str]) -> str:
        return f"COUNT {len(self._data)}"

    # ── M6: EXISTS ──────────────────────────────────────────────────────

    def _cmd_exists(self, raw_line: str, args: list[str]) -> str:
        if len(args) < 1:
            return "ERR unknown_command"
        key = args[0]
        if key not in self._data:
            return "FALSE"
        if self._is_expired(key):
            return "FALSE"
        return "TRUE"

    # ── M7: FLUSH ───────────────────────────────────────────────────────

    def _cmd_flush(self, raw_line: str, args: list[str]) -> str:
        self._data.clear()
        self._expiry.clear()
        return "OK"

    # ── S1: MSET ────────────────────────────────────────────────────────

    def _cmd_mset(self, raw_line: str, args: list[str]) -> str:
        # Must have even number of args (key-value pairs)
        if len(args) < 2 or len(args) % 2 != 0:
            return "ERR wrong_number_of_arguments"

        pairs = []
        for i in range(0, len(args), 2):
            pairs.append((args[i], args[i + 1]))

        # Pre-validation phase (under lock for atomicity)
        with self._lock:
            for key, value in pairs:
                err = self._check_key_length(key)
                if err:
                    return err
                err = self._check_value_size(value)
                if err:
                    return err
                err = self._check_store_full(key)
                if err:
                    return err

            # All checks passed, perform writes
            for key, value in pairs:
                self._data[key] = value
                self._expiry.pop(key, None)

        return f"OK {len(pairs)}"

    # ── S2: MGET ────────────────────────────────────────────────────────

    def _cmd_mget(self, raw_line: str, args: list[str]) -> str:
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

    # ── S4: SETEX ───────────────────────────────────────────────────────

    def _cmd_setex(self, raw_line: str, args: list[str]) -> str:
        if len(args) < 3:
            return "ERR unknown_command"
        key = args[0]
        seconds_str = args[1]

        # Parse and validate TTL
        try:
            seconds = int(seconds_str)
        except ValueError:
            return "ERR invalid_ttl"
        if seconds <= 0:
            return "ERR invalid_ttl"

        # Value is everything after key + seconds
        key_plus_sec_len = len(key) + 1 + len(seconds_str) + 1
        # Find the position in raw_line
        setex_pos = raw_line.upper().find("SETEX")
        if setex_pos != -1:
            value = raw_line[setex_pos + 6:].strip()  # skip "SETEX "
            # Now skip key and seconds
            parts_rest = value.split(None, 2)  # split on whitespace, max 3 parts
            if len(parts_rest) >= 3:
                value = parts_rest[2]
            else:
                return "ERR unknown_command"
        else:
            return "ERR unknown_command"

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

    # ── TTL ─────────────────────────────────────────────────────────────

    def _cmd_ttl(self, raw_line: str, args: list[str]) -> str:
        if len(args) < 1:
            return "ERR unknown_command"
        key = args[0]
        if key not in self._data:
            return "ERR key_not_found"
        if self._is_expired(key):
            return "ERR key_not_found"
        if key not in self._expiry or self._expiry[key] is None:
            return "-1"
        remaining = int(self._expiry[key] - time.time())
        return str(max(remaining, 0))

    # ── S5: APPEND ──────────────────────────────────────────────────────

    def _cmd_append(self, raw_line: str, args: list[str]) -> str:
        if len(args) < 2:
            return "ERR unknown_command"
        key = args[0]
        # Value is everything after the key
        value_start = raw_line.find(key) + len(key) + 1
        value = raw_line[value_start:] if value_start < len(raw_line) else ""

        err = self._check_key_length(key)
        if err:
            return err

        if key in self._data and not self._is_expired(key):
            new_value = self._data[key] + value
        else:
            new_value = value
            err = self._check_store_full(key)
            if err:
                return err

        err = self._check_value_size(new_value)
        if err:
            return err

        self._data[key] = new_value
        self._expiry.pop(key, None)
        new_len = len(new_value.encode('utf-8'))
        return f"OK {new_len}"

    # ── Y1: RENAME ──────────────────────────────────────────────────────

    def _cmd_rename(self, raw_line: str, args: list[str]) -> str:
        if len(args) < 2:
            return "ERR unknown_command"
        old_key = args[0]
        new_key = args[1]

        if old_key not in self._data:
            return "ERR key_not_found"
        if self._is_expired(old_key):
            return "ERR key_not_found"

        # If new_key already exists, delete it first
        self._data.pop(new_key, None)
        self._expiry.pop(new_key, None)

        self._data[new_key] = self._data.pop(old_key)
        if old_key in self._expiry:
            self._expiry[new_key] = self._expiry.pop(old_key)

        return "OK"

    # ── Y2: TYPE ────────────────────────────────────────────────────────

    def _cmd_type(self, raw_line: str, args: list[str]) -> str:
        if len(args) < 1:
            return "ERR unknown_command"
        key = args[0]
        if key not in self._data:
            return "ERR key_not_found"
        if self._is_expired(key):
            return "ERR key_not_found"

        value = self._data[key]
        # Try to parse as integer (positive or negative)
        try:
            int(value)
            return "INTEGER"
        except ValueError:
            return "STRING"

    # ── Y3: DUMP ────────────────────────────────────────────────────────

    def _cmd_dump(self, raw_line: str, args: list[str]) -> str:
        lines = []
        for key, value in self._data.items():
            if not self._is_expired(key):
                lines.append(f"{key}={value}")
        if not lines:
            return self.END_MARKER
        return "\n".join(lines) + "\n" + self.END_MARKER
