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
        self._data = {}       # key -> value (str)
        self._expiry = {}     # key -> expiration timestamp (float) or None

    # ── Parsing ─────────────────────────────────────────────────────────

    def _parse(self, command: str):
        """
        Parse a single command line into (cmd, args).

        Returns ("", []) for empty/whitespace-only input.
        """
        stripped = command.strip()
        if not stripped:
            return "", []
        parts = stripped.split()
        cmd = parts[0].upper()
        args = parts[1:]
        return cmd, args

    # ── Expiry helpers ───────────────────────────────────────────────────

    def _is_expired(self, key: str) -> bool:
        """Check whether *key* has expired (does NOT clean up)."""
        if key not in self._expiry or self._expiry[key] is None:
            return False
        return time.time() >= self._expiry[key]

    def _cleanup_expired(self, key: str):
        """Remove *key* from store if it has expired."""
        if key in self._data and self._is_expired(key):
            del self._data[key]
            del self._expiry[key]

    def _cleanup_all_expired(self):
        """Remove every expired key from the store."""
        for key in list(self._data.keys()):
            self._cleanup_expired(key)

    # ── Main dispatcher ─────────────────────────────────────────────────

    def execute(self, command: str) -> str:
        """
        Execute a single KVP command and return the response string.

        Parse the command, dispatch to the appropriate handler,
        and return the response per the protocol specification.
        """
        cmd, args = self._parse(command)

        if cmd == "":
            return ""

        if cmd == "SET":
            return self._cmd_set(args)
        if cmd == "GET":
            return self._cmd_get(args)
        if cmd == "DEL":
            return self._cmd_del(args)
        if cmd == "KEYS":
            return self._cmd_keys(args)
        if cmd == "COUNT":
            return self._cmd_count(args)
        if cmd == "EXISTS":
            return self._cmd_exists(args)
        if cmd == "FLUSH":
            return self._cmd_flush(args)

        # ── SHOULD commands ──
        if cmd == "MSET":
            return self._cmd_mset(args)
        if cmd == "MGET":
            return self._cmd_mget(args)
        if cmd == "TTL":
            return self._cmd_ttl(args)
        if cmd == "SETEX":
            return self._cmd_setex(args)
        if cmd == "APPEND":
            return self._cmd_append(args)

        # ── MAY commands ──
        if cmd == "RENAME":
            return self._cmd_rename(args)
        if cmd == "TYPE":
            return self._cmd_type(args)
        if cmd == "DUMP":
            return self._cmd_dump(args)

        return "ERR unknown_command"

    # ── MUST command handlers ───────────────────────────────────────────

    def _cmd_set(self, args):
        """SET <key> <value> — M1, M8, M10, M11, M12"""
        if len(args) < 2:
            return "ERR wrong_number_of_arguments"
        key = args[0]
        value = " ".join(args[1:])

        if len(key) > self.MAX_KEY_LENGTH:
            return "ERR key_too_long"
        if len(value) > self.MAX_VALUE_SIZE:
            return "ERR value_too_large"

        # Capacity check: only fail for *new* keys
        if key not in self._data and len(self._data) >= self.MAX_KEYS:
            return "ERR store_full"

        self._data[key] = value
        self._expiry.pop(key, None)  # clear any existing expiry
        return "OK"

    def _cmd_get(self, args):
        """GET <key> — M2"""
        if len(args) < 1:
            return "ERR wrong_number_of_arguments"
        key = args[0]

        self._cleanup_expired(key)
        if key not in self._data:
            return "ERR key_not_found"
        return self._data[key]

    def _cmd_del(self, args):
        """DEL <key> — M3, M8"""
        if len(args) < 1:
            return "ERR wrong_number_of_arguments"
        key = args[0]

        self._cleanup_expired(key)
        if key not in self._data:
            return "ERR key_not_found"

        del self._data[key]
        self._expiry.pop(key, None)
        return "OK"

    def _cmd_keys(self, args):
        """KEYS — M4"""
        self._cleanup_all_expired()
        keys = list(self._data.keys())
        if not keys:
            return self.END_MARKER
        return "\n".join(keys) + "\n" + self.END_MARKER

    def _cmd_count(self, args):
        """COUNT — M5"""
        self._cleanup_all_expired()
        return f"COUNT {len(self._data)}"

    def _cmd_exists(self, args):
        """EXISTS <key> — M6"""
        if len(args) < 1:
            return "FALSE"
        key = args[0]
        self._cleanup_expired(key)
        return "TRUE" if key in self._data else "FALSE"

    def _cmd_flush(self, args):
        """FLUSH — M7"""
        self._data.clear()
        self._expiry.clear()
        return "OK"

    # ── SHOULD command handlers ─────────────────────────────────────────

    def _cmd_mset(self, args):
        """MSET <k1> <v1> <k2> <v2> ... — S1 (atomic batch set)"""
        if len(args) < 2 or len(args) % 2 != 0:
            return "ERR wrong_number_of_arguments"

        # Phase 1: validate all pairs before writing (atomicity)
        new_keys = []
        for i in range(0, len(args), 2):
            key = args[i]
            value = args[i + 1]
            if len(key) > self.MAX_KEY_LENGTH:
                return "ERR key_too_long"
            if len(value) > self.MAX_VALUE_SIZE:
                return "ERR value_too_large"
            if key not in self._data:
                new_keys.append(key)

        if len(self._data) + len(new_keys) > self.MAX_KEYS:
            return "ERR store_full"

        # Phase 2: commit
        n = len(args) // 2
        for i in range(0, len(args), 2):
            key = args[i]
            value = args[i + 1]
            self._data[key] = value
            self._expiry.pop(key, None)
        return f"OK {n}"

    def _cmd_mget(self, args):
        """MGET <k1> <k2> ... — S2 (batch get)"""
        if len(args) < 1:
            return self.END_MARKER

        lines = []
        for key in args:
            self._cleanup_expired(key)
            if key in self._data:
                lines.append(self._data[key])
            else:
                lines.append("NIL")
        lines.append(self.END_MARKER)
        return "\n".join(lines)

    def _cmd_ttl(self, args):
        """TTL <key> — S3 (time-to-live)"""
        if len(args) < 1:
            return "ERR wrong_number_of_arguments"
        key = args[0]

        if key not in self._data:
            return "ERR key_not_found"

        self._cleanup_expired(key)
        if key not in self._data:
            return "ERR key_not_found"

        if key not in self._expiry or self._expiry[key] is None:
            return "-1"

        remaining = int(self._expiry[key] - time.time())
        return str(remaining)

    def _cmd_setex(self, args):
        """SETEX <key> <seconds> <value> — S4 (set with expiry)"""
        if len(args) < 3:
            return "ERR wrong_number_of_arguments"
        key = args[0]
        try:
            seconds = int(args[1])
        except ValueError:
            return "ERR invalid_ttl"
        value = " ".join(args[2:])

        if len(key) > self.MAX_KEY_LENGTH:
            return "ERR key_too_long"
        if len(value) > self.MAX_VALUE_SIZE:
            return "ERR value_too_large"

        if key not in self._data and len(self._data) >= self.MAX_KEYS:
            return "ERR store_full"

        self._data[key] = value
        self._expiry[key] = time.time() + seconds
        return "OK"

    def _cmd_append(self, args):
        """APPEND <key> <value> — S5 (append or create)"""
        if len(args) < 2:
            return "ERR wrong_number_of_arguments"
        key = args[0]
        value = " ".join(args[1:])

        self._cleanup_expired(key)

        if key not in self._data:
            # Creating new key → capacity check
            if len(self._data) >= self.MAX_KEYS:
                return "ERR store_full"
            self._data[key] = value
        else:
            self._data[key] += value

        return f"OK {len(self._data[key])}"

    # ── MAY command handlers ────────────────────────────────────────────

    def _cmd_rename(self, args):
        """RENAME <old_key> <new_key> — MAY"""
        if len(args) < 2:
            return "ERR wrong_number_of_arguments"
        old_key, new_key = args[0], args[1]

        self._cleanup_expired(old_key)
        if old_key not in self._data:
            return "ERR key_not_found"

        value = self._data.pop(old_key)
        expiry = self._expiry.pop(old_key, None)
        self._data[new_key] = value
        if expiry is not None:
            self._expiry[new_key] = expiry
        return "OK"

    def _cmd_type(self, args):
        """TYPE <key> — MAY (STRING or INTEGER)"""
        if len(args) < 1:
            return "ERR wrong_number_of_arguments"
        key = args[0]

        self._cleanup_expired(key)
        if key not in self._data:
            return "ERR key_not_found"

        val = self._data[key]
        try:
            int(val)
            return "INTEGER"
        except ValueError:
            return "STRING"

    def _cmd_dump(self, args):
        """DUMP — MAY (all key-value pairs as <key>=<value>)"""
        self._cleanup_all_expired()
        pairs = [f"{k}={v}" for k, v in self._data.items()]
        if not pairs:
            return self.END_MARKER
        return "\n".join(pairs) + "\n" + self.END_MARKER
