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

    # ── P0: Dispatch table ─────────────────────────────────────────────
    # Maps command -> (handler_method_name, min_total_parts_including_command)
    COMMAND_MAP = {
        # MUST commands
        "SET":    ("_handle_set",    3),
        "GET":    ("_handle_get",    2),
        "DEL":    ("_handle_del",    2),
        "KEYS":   ("_handle_keys",   1),
        "COUNT":  ("_handle_count",  1),
        "EXISTS": ("_handle_exists", 2),
        "FLUSH":  ("_handle_flush",  1),
        # SHOULD commands
        "MSET":   ("_handle_mset",   3),
        "MGET":   ("_handle_mget",   2),
        "SETEX":  ("_handle_setex",  4),
        "TTL":    ("_handle_ttl",    2),
        "APPEND": ("_handle_append", 3),
        # MAY commands
        "RENAME": ("_handle_rename", 3),
        "TYPE":   ("_handle_type",   2),
        "DUMP":   ("_handle_dump",   1),
    }

    def __init__(self):
        self._data = {}
        self._expiry = {}  # key -> expiration timestamp (or None for no expiry)

    # ── P0: Command dispatch ───────────────────────────────────────────

    def execute(self, command: str) -> str:
        """
        Execute a single KVP command and return the response string.

        Parse the command, dispatch to the appropriate handler via the
        dispatch table, and return the response per the protocol specification.
        """
        parts = command.strip().split()
        if not parts:
            return "ERR unknown_command"

        cmd = parts[0].upper()
        args = parts[1:]

        # Look up command in dispatch table
        entry = self.COMMAND_MAP.get(cmd)
        if entry is None:
            return "ERR unknown_command"

        handler_name, min_parts = entry
        if len(parts) < min_parts:
            return "ERR unknown_command"

        # Dispatch to the handler method
        handler = getattr(self, handler_name)
        return handler(args)

    # ── Expiry helpers ─────────────────────────────────────────────────

    def _is_expired(self, key: str) -> bool:
        """Check if a key has expired and clean it up if so."""
        if key in self._expiry and self._expiry[key] is not None:
            if time.time() > self._expiry[key]:
                del self._data[key]
                del self._expiry[key]
                return True
        return False

    def _cleanup_all_expired(self):
        """Remove all expired keys from the store (used by KEYS/COUNT/DUMP)."""
        for key in list(self._data.keys()):
            self._is_expired(key)

    # ── P1: MUST command handlers ──────────────────────────────────────

    def _handle_set(self, args):
        """SET <key> <value> — store value under key."""
        key = args[0]
        value = " ".join(args[1:])

        # Constraint checks (early-fail order)
        if len(key) > self.MAX_KEY_LENGTH:
            return "ERR key_too_long"
        if len(value) > self.MAX_VALUE_SIZE:
            return "ERR value_too_large"
        if len(self._data) >= self.MAX_KEYS and key not in self._data:
            return "ERR store_full"

        self._data[key] = value
        self._expiry[key] = None
        return "OK"

    def _handle_get(self, args):
        """GET <key> — retrieve value or error."""
        key = args[0]
        self._is_expired(key)
        if key not in self._data:
            return "ERR key_not_found"
        return self._data[key]

    def _handle_del(self, args):
        """DEL <key> [key ...] — remove key(s) atomically from store."""
        # Phase 1: verify all keys exist (any missing → reject all)
        for key in args:
            self._is_expired(key)
            if key not in self._data:
                return "ERR key_not_found"
        # Phase 2: delete all (atomic — no partial deletion)
        count = 0
        for key in args:
            del self._data[key]
            self._expiry.pop(key, None)
            count += 1
        return f"OK {count}"

    def _handle_keys(self, args):
        """KEYS — list all stored keys, terminated by END."""
        self._cleanup_all_expired()
        keys = list(self._data.keys())
        if not keys:
            return "END"
        return "\n".join(keys) + "\nEND"

    def _handle_count(self, args):
        """COUNT — return number of stored keys."""
        self._cleanup_all_expired()
        return f"COUNT {len(self._data)}"

    def _handle_exists(self, args):
        """EXISTS <key> — check if key exists (TRUE/FALSE)."""
        key = args[0]
        self._is_expired(key)
        return "TRUE" if key in self._data else "FALSE"

    def _handle_flush(self, args):
        """FLUSH — remove all keys."""
        self._data.clear()
        self._expiry.clear()
        return "OK"

    # ── P3: SHOULD command handlers ────────────────────────────────────

    def _handle_mset(self, args):
        """MSET <k1> <v1> <k2> <v2> ... — set multiple pairs atomically."""
        if len(args) % 2 != 0:
            return "ERR unknown_command"

        # Phase 1: pre-validate all pairs without modifying store
        pairs = []
        existing_keys = set(self._data.keys())
        new_keys_seen = set()
        new_key_count = 0

        for i in range(0, len(args), 2):
            key = args[i]
            value = args[i + 1]

            if len(key) > self.MAX_KEY_LENGTH:
                return "ERR key_too_long"
            if len(value) > self.MAX_VALUE_SIZE:
                return "ERR value_too_large"

            pairs.append((key, value))

            # Count unique new keys (not in store and not seen before in this MSET)
            if key not in existing_keys and key not in new_keys_seen:
                new_key_count += 1
                new_keys_seen.add(key)

        if len(self._data) + new_key_count > self.MAX_KEYS:
            return "ERR store_full"

        # Phase 2: all checks passed, commit all pairs
        for key, value in pairs:
            self._data[key] = value
            self._expiry[key] = None

        return f"OK {len(pairs)}"

    def _handle_mget(self, args):
        """MGET <k1> <k2> ... — get multiple values, NIL for missing."""
        lines = []
        for key in args:
            self._is_expired(key)
            if key in self._data:
                lines.append(self._data[key])
            else:
                lines.append("NIL")
        lines.append("END")
        return "\n".join(lines)

    def _handle_append(self, args):
        """APPEND <key> <value> — append to existing or create new."""
        key = args[0]
        value = " ".join(args[1:])

        self._is_expired(key)

        if len(key) > self.MAX_KEY_LENGTH:
            return "ERR key_too_long"

        if key in self._data:
            new_value = self._data[key] + value
            if len(new_value) > self.MAX_VALUE_SIZE:
                return "ERR value_too_large"
            self._data[key] = new_value
        else:
            # Creating a new key — need to check value size and store capacity
            if len(value) > self.MAX_VALUE_SIZE:
                return "ERR value_too_large"
            if len(self._data) >= self.MAX_KEYS:
                return "ERR store_full"
            self._data[key] = value

        self._expiry[key] = None
        return f"OK {len(self._data[key])}"

    # ── P4: SETEX + TTL handlers ───────────────────────────────────────

    def _handle_setex(self, args):
        """SETEX <key> <seconds> <value> — set with expiration."""
        key = args[0]
        seconds_str = args[1]
        value = " ".join(args[2:])

        # Parse seconds as integer
        try:
            seconds = int(seconds_str)
        except ValueError:
            return "ERR unknown_command"

        # Constraint checks (same order as SET)
        if len(key) > self.MAX_KEY_LENGTH:
            return "ERR key_too_long"
        if len(value) > self.MAX_VALUE_SIZE:
            return "ERR value_too_large"
        if len(self._data) >= self.MAX_KEYS and key not in self._data:
            return "ERR store_full"

        self._data[key] = value
        self._expiry[key] = time.time() + seconds
        return "OK"

    def _handle_ttl(self, args):
        """TTL <key> — return remaining time-to-live in seconds."""
        key = args[0]
        self._is_expired(key)

        if key not in self._data:
            return "ERR key_not_found"

        expiry = self._expiry.get(key)
        if expiry is None:
            return "-1"

        remaining = int(expiry - time.time())
        if remaining <= 0:
            return "0"
        return str(remaining)

    # ── P5: MAY command handlers ───────────────────────────────────────

    def _handle_rename(self, args):
        """RENAME <old_key> <new_key> — rename a key."""
        old_key = args[0]
        new_key = args[1]

        self._is_expired(old_key)

        if old_key not in self._data:
            return "ERR key_not_found"

        if len(new_key) > self.MAX_KEY_LENGTH:
            return "ERR key_too_long"

        self._data[new_key] = self._data.pop(old_key)
        self._expiry[new_key] = self._expiry.pop(old_key, None)
        return "OK"

    def _handle_type(self, args):
        """TYPE <key> — return the type of the value (STRING or INTEGER)."""
        key = args[0]
        self._is_expired(key)

        if key not in self._data:
            return "ERR key_not_found"

        value = self._data[key]
        # INTEGER: all digits, optionally with leading minus
        if value.isdigit() or (value.startswith('-') and value[1:].isdigit()):
            return "INTEGER"
        return "STRING"

    def _handle_dump(self, args):
        """DUMP — return all key=value pairs, terminated by END."""
        self._cleanup_all_expired()
        lines = [f"{k}={v}" for k, v in self._data.items()]
        if not lines:
            return "END"
        return "\n".join(lines) + "\nEND"
