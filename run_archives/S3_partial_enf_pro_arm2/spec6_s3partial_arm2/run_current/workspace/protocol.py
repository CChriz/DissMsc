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


class KVStore:
    """In-memory key-value store implementing the KVP protocol."""

    MAX_KEY_LENGTH = 64
    MAX_VALUE_SIZE = 1024
    MAX_KEYS = 100
    END_MARKER = "END"

    def __init__(self):
        self._data = {}
        # Audit stats for runtime debugging (suggested by fullstack1)
        self._stats = {
            "flush_count": 0,
            "last_flush_keys": 0,
        }

    # ── Public Entry Point ──────────────────────────────────────────

    def execute(self, command: str) -> str:
        """
        Execute a single KVP command and return the response string.

        Parse the command, dispatch to the appropriate handler,
        and return the response per the protocol specification.
        """
        raw = command.strip()
        if not raw:
            return ""

        parts = raw.split()
        cmd = parts[0].upper()
        args = parts[1:]

        # Route to handler via dispatch table
        handler = self._DISPATCH.get(cmd)
        if handler is None:
            return "ERR unknown_command"
        return handler(self, args)

    # ── Validation Helpers ──────────────────────────────────────────

    def _validate_key(self, key: str) -> str | None:
        """Return error string if key exceeds max length, else None."""
        if len(key) > self.MAX_KEY_LENGTH:
            return "ERR key_too_long"
        return None

    def _validate_value(self, value: str) -> str | None:
        """Return error string if value exceeds max size, else None."""
        if len(value) > self.MAX_VALUE_SIZE:
            return "ERR value_too_large"
        return None

    def _check_capacity(self, key: str) -> str | None:
        """
        Check if store can accept a new key.
        Returns error if store is full and key is new (not updating existing).
        """
        if key not in self._data and len(self._data) >= self.MAX_KEYS:
            return "ERR store_full"
        return None

    @staticmethod
    def _require_args(args: list, min_count: int) -> str | None:
        """Return error if args list has fewer than min_count elements."""
        if len(args) < min_count:
            return "ERR wrong_number_of_arguments"
        return None

    # ── MUST Command Handlers ───────────────────────────────────────

    def _handle_set(self, args: list) -> str:
        """M1: SET <key> <value> — store a key-value pair."""
        err = self._require_args(args, 2)
        if err:
            return err
        key = args[0]
        value = " ".join(args[1:])

        err = self._validate_key(key)
        if err:
            return err
        err = self._validate_value(value)
        if err:
            return err
        err = self._check_capacity(key)
        if err:
            return err

        self._data[key] = value
        return "OK"

    def _handle_get(self, args: list) -> str:
        """M2: GET <key> — retrieve value by key."""
        err = self._require_args(args, 1)
        if err:
            return err
        key = args[0]

        err = self._validate_key(key)
        if err:
            return err

        if key not in self._data:
            return "ERR key_not_found"
        return self._data[key]

    def _handle_del(self, args: list) -> str:
        """M3: DEL <key> — remove a key from the store."""
        err = self._require_args(args, 1)
        if err:
            return err
        key = args[0]

        if key not in self._data:
            return "ERR key_not_found"

        del self._data[key]
        return "OK"

    def _handle_keys(self, _args: list = None) -> str:
        """M4: KEYS — list all stored keys, terminated by END."""
        if not self._data:
            return self.END_MARKER
        keys = list(self._data.keys())
        return "\n".join(keys) + "\n" + self.END_MARKER

    def _handle_count(self, _args: list = None) -> str:
        """M5: COUNT — return the number of stored keys."""
        return f"COUNT {len(self._data)}"

    def _handle_exists(self, args: list) -> str:
        """M6: EXISTS <key> — check if a key exists."""
        err = self._require_args(args, 1)
        if err:
            return err
        key = args[0]
        return "TRUE" if key in self._data else "FALSE"

    def _handle_flush(self, _args: list = None) -> str:
        """M7: FLUSH — remove all keys from the store."""
        self._stats["last_flush_keys"] = len(self._data)
        self._stats["flush_count"] += 1
        self._data.clear()
        return "OK"

    # ── SHOULD Command Handlers ─────────────────────────────────────

    def _handle_mset(self, args: list) -> str:
        """
        S1: MSET <k1> <v1> <k2> <v2> ... — atomic multi-set.

        Validates all pairs first; only writes if every pair is valid.
        """
        if len(args) < 2 or len(args) % 2 != 0:
            return "ERR wrong_number_of_arguments"

        # ── Validation phase (atomic: all-or-nothing) ──
        new_keys_count = 0
        for i in range(0, len(args), 2):
            key = args[i]
            value = args[i + 1]

            err = self._validate_key(key)
            if err:
                return err
            err = self._validate_value(value)
            if err:
                return err
            if key not in self._data:
                new_keys_count += 1

        # Capacity check with projected new keys
        if len(self._data) + new_keys_count > self.MAX_KEYS:
            return "ERR store_full"

        # ── Write phase ──
        n = len(args) // 2
        for i in range(0, len(args), 2):
            key = args[i]
            value = args[i + 1]
            self._data[key] = value

        return f"OK {n}"

    def _handle_mget(self, args: list) -> str:
        """
        S2: MGET <k1> <k2> ... — multi-get.

        Returns value per key or NIL if not found, terminated by END.
        """
        if not args:
            return self.END_MARKER

        lines = []
        for key in args:
            if key in self._data:
                lines.append(self._data[key])
            else:
                lines.append("NIL")
        lines.append(self.END_MARKER)
        return "\n".join(lines)

    def _handle_append(self, args: list) -> str:
        """
        S5: APPEND <key> <value> — append to value or create new key.

        Existing key: concatenates and validates new length.
        New key: validates value size and store capacity (like SET).
        """
        err = self._require_args(args, 2)
        if err:
            return err
        key = args[0]
        value = " ".join(args[1:])

        err = self._validate_key(key)
        if err:
            return err

        if key in self._data:
            # Existing key — concatenate and validate total size
            new_value = self._data[key] + value
            err = self._validate_value(new_value)
            if err:
                return err
            self._data[key] = new_value
            return f"OK {len(new_value)}"
        else:
            # New key — validate value and capacity (mirrors SET logic)
            err = self._validate_value(value)
            if err:
                return err
            err = self._check_capacity(key)
            if err:
                return err
            self._data[key] = value
            return f"OK {len(value)}"

    # ── Dispatch Table ──────────────────────────────────────────────

    _DISPATCH = {
        "SET": _handle_set,
        "GET": _handle_get,
        "DEL": _handle_del,
        "KEYS": _handle_keys,
        "COUNT": _handle_count,
        "EXISTS": _handle_exists,
        "FLUSH": _handle_flush,
        "MSET": _handle_mset,
        "MGET": _handle_mget,
        "APPEND": _handle_append,
    }
