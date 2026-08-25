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

    def __init__(
        self,
        max_key_length=MAX_KEY_LENGTH,
        max_value_size=MAX_VALUE_SIZE,
        max_keys=MAX_KEYS,
        delimiter="\n",
    ):
        self._max_key_length = max_key_length
        self._max_value_size = max_value_size
        self._max_keys = max_keys
        self._delimiter = delimiter
        self._data = {}
        self._expiry = {}  # key -> expiration timestamp (unix seconds)

    # ── public API ────────────────────────────────────────────────────
    def execute(self, command: str) -> str:
        """Execute a single KVP command and return the response string.

        The returned response does NOT include a trailing delimiter; the
        caller (or test harness) is responsible for joining lines.
        """
        if command is None:
            return "ERR unknown_command"

        line = command.strip()
        if not line:
            return "ERR unknown_command"

        parts = line.split(None, 1)
        cmd = parts[0].upper()
        rest = parts[1] if len(parts) > 1 else ""

        handler = {
            "SET": self._cmd_set,
            "GET": self._cmd_get,
            "DEL": self._cmd_del,
            "KEYS": self._cmd_keys,
            "COUNT": self._cmd_count,
            "EXISTS": self._cmd_exists,
            "FLUSH": self._cmd_flush,
            "MSET": self._cmd_mset,
            "MGET": self._cmd_mget,
            "SETEX": self._cmd_setex,
            "TTL": self._cmd_ttl,
            "APPEND": self._cmd_append,
            "RENAME": self._cmd_rename,
            "TYPE": self._cmd_type,
            "DUMP": self._cmd_dump,
        }.get(cmd)

        if handler is None:
            return "ERR unknown_command"
        return handler(rest)

    # ── helpers ───────────────────────────────────────────────────────
    def _get_value(self, key):
        """Return the stored value, or None if missing/expired (cleaning up)."""
        if key not in self._data:
            return None
        expiry = self._expiry.get(key)
        if expiry is not None and time.time() > expiry:
            del self._data[key]
            del self._expiry[key]
            return None
        return self._data[key]

    def _purge_expired(self):
        now = time.time()
        for key in [
            k for k, t in self._expiry.items() if t is not None and now > t
        ]:
            self._data.pop(key, None)
            self._expiry.pop(key, None)

    def _list_response(self, items):
        return self._delimiter.join(list(items) + [self.END_MARKER])

    def _is_integer(self, value):
        try:
            int(value)
            return True
        except (ValueError, TypeError):
            return False

    # ── command handlers ──────────────────────────────────────────────
    def _cmd_set(self, rest):
        # value = remainder of line (supports spaces in value)
        parts = rest.split(None, 1)
        if len(parts) < 2:
            return "ERR unknown_command"
        key, value = parts[0], parts[1]

        if len(key) > self._max_key_length:
            return "ERR key_too_long"
        if len(value) > self._max_value_size:
            return "ERR value_too_large"

        self._purge_expired()
        if key not in self._data and len(self._data) >= self._max_keys:
            return "ERR store_full"

        self._data[key] = value
        self._expiry.pop(key, None)
        return "OK"

    def _cmd_get(self, rest):
        args = rest.split()
        if len(args) != 1:
            return "ERR unknown_command"
        value = self._get_value(args[0])
        if value is None:
            return "ERR key_not_found"
        return value

    def _cmd_del(self, rest):
        args = rest.split()
        if len(args) != 1:
            return "ERR unknown_command"
        key = args[0]
        if self._get_value(key) is None:
            return "ERR key_not_found"
        del self._data[key]
        self._expiry.pop(key, None)
        return "OK"

    def _cmd_keys(self, rest):
        if rest.strip():
            return "ERR unknown_command"
        self._purge_expired()
        return self._list_response(list(self._data.keys()))

    def _cmd_count(self, rest):
        if rest.strip():
            return "ERR unknown_command"
        self._purge_expired()
        return f"COUNT {len(self._data)}"

    def _cmd_exists(self, rest):
        args = rest.split()
        if len(args) != 1:
            return "ERR unknown_command"
        return "TRUE" if self._get_value(args[0]) is not None else "FALSE"

    def _cmd_flush(self, rest):
        if rest.strip():
            return "ERR unknown_command"
        self._data.clear()
        self._expiry.clear()
        return "OK"

    def _cmd_mset(self, rest):
        args = rest.split()
        if len(args) < 2 or len(args) % 2 != 0:
            return "ERR unknown_command"
        pairs = [(args[i], args[i + 1]) for i in range(0, len(args), 2)]

        for key, value in pairs:
            if len(key) > self._max_key_length:
                return "ERR key_too_long"
            if len(value) > self._max_value_size:
                return "ERR value_too_large"

        self._purge_expired()
        existing = set(self._data.keys())
        new_keys = set()
        for key, _ in pairs:
            if key not in existing and key not in new_keys:
                new_keys.add(key)
        if len(existing) + len(new_keys) > self._max_keys:
            return "ERR store_full"

        for key, value in pairs:
            self._data[key] = value
            self._expiry.pop(key, None)
        return f"OK {len(pairs)}"

    def _cmd_mget(self, rest):
        keys = rest.split()
        if not keys:
            return "ERR unknown_command"
        lines = []
        for key in keys:
            value = self._get_value(key)
            lines.append(value if value is not None else "NIL")
        return self._list_response(lines)

    def _cmd_setex(self, rest):
        # key, seconds, value (value = remainder, supports spaces)
        parts = rest.split(None, 2)
        if len(parts) < 3:
            return "ERR unknown_command"
        key, seconds_str, value = parts[0], parts[1], parts[2]
        try:
            seconds = int(seconds_str)
        except ValueError:
            return "ERR unknown_command"

        if len(key) > self._max_key_length:
            return "ERR key_too_long"
        if len(value) > self._max_value_size:
            return "ERR value_too_large"

        self._purge_expired()
        if key not in self._data and len(self._data) >= self._max_keys:
            return "ERR store_full"

        self._data[key] = value
        self._expiry[key] = time.time() + seconds
        return "OK"

    def _cmd_ttl(self, rest):
        args = rest.split()
        if len(args) != 1:
            return "ERR unknown_command"
        key = args[0]
        if self._get_value(key) is None:
            return "ERR key_not_found"
        expiry = self._expiry.get(key)
        if expiry is None:
            return "-1"
        remaining = expiry - time.time()
        if remaining <= 0:
            del self._data[key]
            del self._expiry[key]
            return "ERR key_not_found"
        return str(int(remaining))

    def _cmd_append(self, rest):
        parts = rest.split(None, 1)
        if len(parts) < 2:
            return "ERR unknown_command"
        key, value = parts[0], parts[1]

        if len(key) > self._max_key_length:
            return "ERR key_too_long"

        old_value = self._get_value(key)
        if old_value is not None:
            new_value = old_value + value
        else:
            self._purge_expired()
            if len(self._data) >= self._max_keys:
                return "ERR store_full"
            new_value = value

        if len(new_value) > self._max_value_size:
            return "ERR value_too_large"

        self._data[key] = new_value
        self._expiry.pop(key, None)
        return f"OK {len(new_value)}"

    def _cmd_rename(self, rest):
        args = rest.split()
        if len(args) != 2:
            return "ERR unknown_command"
        old, new = args[0], args[1]
        if self._get_value(old) is None:
            return "ERR key_not_found"
        value = self._data.pop(old)
        expiry = self._expiry.pop(old, None)
        self._data[new] = value
        if expiry is not None:
            self._expiry[new] = expiry
        else:
            self._expiry.pop(new, None)
        return "OK"

    def _cmd_type(self, rest):
        args = rest.split()
        if len(args) != 1:
            return "ERR unknown_command"
        key = args[0]
        value = self._get_value(key)
        if value is None:
            return "ERR key_not_found"
        return "INTEGER" if self._is_integer(value) else "STRING"

    def _cmd_dump(self, rest):
        if rest.strip():
            return "ERR unknown_command"
        self._purge_expired()
        lines = [f"{k}={v}" for k, v in self._data.items()]
        return self._list_response(lines)
