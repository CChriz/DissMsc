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

    def __init__(self, max_key_length=64, max_value_size=1024, max_keys=100):
        self.max_key_length = max_key_length
        self.max_value_size = max_value_size
        self.max_keys = max_keys
        self._store = {}  # key -> (value, expiry_timestamp | None)

    # ── Parsing & Routing ────────────────────────────────────────────────

    def _parse(self, command_line):
        """Parse a command line into (command, args) tuple."""
        tokens = command_line.strip().split()
        if not tokens:
            return ('', [])
        return (tokens[0].upper(), tokens[1:])

    def execute(self, command_line):
        """Execute a single KVP command and return the response string."""
        cmd, args = self._parse(command_line)
        if not cmd:
            return 'ERR unknown_command'

        handler_map = {
            'SET':    self._handle_set,
            'GET':    self._handle_get,
            'DEL':    self._handle_del,
            'KEYS':   self._handle_keys,
            'COUNT':  self._handle_count,
            'EXISTS': self._handle_exists,
            'FLUSH':  self._handle_flush,
            'MSET':   self._handle_mset,
            'MGET':   self._handle_mget,
            'TTL':    self._handle_ttl,
            'SETEX':  self._handle_setex,
            'APPEND': self._handle_append,
            'RENAME': self._handle_rename,
            'TYPE':   self._handle_type,
            'DUMP':   self._handle_dump,
        }

        handler = handler_map.get(cmd)
        if handler is None:
            return 'ERR unknown_command'

        return handler(args)

    def _is_expired(self, key):
        """Check if a key has expired and clean it up if so.
        Returns True if the key was expired (and has been removed)."""
        entry = self._store.get(key)
        if entry is None:
            return True
        _, expiry = entry
        if expiry is not None and time.time() > expiry:
            del self._store[key]
            return True
        return False

    # ── MUST Commands ────────────────────────────────────────────────────

    def _handle_set(self, args):
        """SET <key> <value> — store a value."""
        if len(args) < 2:
            return 'ERR unknown_command'
        key = args[0]
        value = ' '.join(args[1:])

        if len(key) > self.max_key_length:
            return 'ERR key_too_long'
        if len(value) > self.max_value_size:
            return 'ERR value_too_large'
        if key not in self._store and len(self._store) >= self.max_keys:
            return 'ERR store_full'

        self._store[key] = (value, None)
        return 'OK'

    def _handle_get(self, args):
        """GET <key> — retrieve a value."""
        if len(args) != 1:
            return 'ERR unknown_command'
        key = args[0]

        if self._is_expired(key):
            return 'ERR key_not_found'
        entry = self._store.get(key)
        if entry is None:
            return 'ERR key_not_found'
        return entry[0]

    def _handle_del(self, args):
        """DEL <key> — remove a key."""
        if len(args) != 1:
            return 'ERR unknown_command'
        key = args[0]

        if key not in self._store:
            return 'ERR key_not_found'

        del self._store[key]
        return 'OK'

    def _handle_keys(self, args):
        """KEYS — list all stored keys, terminated by END."""
        if len(args) != 0:
            return 'ERR unknown_command'

        keys = [k for k in self._store if not self._is_expired(k)]
        return '\n'.join(keys + ['END'])

    def _handle_count(self, args):
        """COUNT — return the number of stored keys."""
        if len(args) != 0:
            return 'ERR unknown_command'

        count = sum(1 for k in self._store if not self._is_expired(k))
        return f'COUNT {count}'

    def _handle_exists(self, args):
        """EXISTS <key> — check if a key exists."""
        if len(args) != 1:
            return 'ERR unknown_command'
        key = args[0]

        if key in self._store and not self._is_expired(key):
            return 'TRUE'
        return 'FALSE'

    def _handle_flush(self, args):
        """FLUSH — remove all keys."""
        if len(args) != 0:
            return 'ERR unknown_command'

        self._store.clear()
        return 'OK'

    # ── SHOULD Commands ──────────────────────────────────────────────────

    def _handle_mset(self, args):
        """MSET <k1> <v1> <k2> <v2> ... — set multiple key-value pairs atomically."""
        if len(args) < 2 or len(args) % 2 != 0:
            return 'ERR unknown_command'

        # Parse into (key, value) pairs
        pairs = [(args[i], args[i + 1]) for i in range(0, len(args), 2)]

        # Precheck: validate all keys and values
        unique_keys = set()
        for k, v in pairs:
            if len(k) > self.max_key_length:
                return 'ERR key_too_long'
            if len(v) > self.max_value_size:
                return 'ERR value_too_large'
            unique_keys.add(k)

        # Capacity check: only count keys that are new to the store
        new_keys = [k for k in unique_keys if k not in self._store]
        if len(self._store) + len(new_keys) > self.max_keys:
            return 'ERR store_full'

        # Atomic write
        for k, v in pairs:
            self._store[k] = (v, None)

        return f'OK {len(unique_keys)}'

    def _handle_mget(self, args):
        """MGET <k1> <k2> ... — get multiple values, terminated by END."""
        if len(args) < 1:
            return 'ERR unknown_command'

        lines = []
        for key in args:
            if key in self._store and not self._is_expired(key):
                lines.append(self._store[key][0])
            else:
                lines.append('NIL')
        lines.append('END')
        return '\n'.join(lines)

    def _handle_ttl(self, args):
        """TTL <key> — return remaining time-to-live in seconds."""
        if len(args) != 1:
            return 'ERR unknown_command'
        key = args[0]

        entry = self._store.get(key)
        if entry is None:
            return 'ERR key_not_found'

        _, expiry = entry
        if expiry is None:
            return '-1'

        remaining = int(expiry - time.time())
        if remaining <= 0:
            del self._store[key]
            return 'ERR key_not_found'

        return str(remaining)

    def _handle_setex(self, args):
        """SETEX <key> <seconds> <value> — set a key with expiration."""
        if len(args) < 3:
            return 'ERR unknown_command'

        key = args[0]
        seconds_str = args[1]
        value = ' '.join(args[2:])

        # Validate seconds
        try:
            seconds = int(seconds_str)
        except ValueError:
            return 'ERR unknown_command'
        if seconds < 0:
            return 'ERR unknown_command'

        if len(key) > self.max_key_length:
            return 'ERR key_too_long'
        if len(value) > self.max_value_size:
            return 'ERR value_too_large'
        if key not in self._store and len(self._store) >= self.max_keys:
            return 'ERR store_full'

        self._store[key] = (value, time.time() + seconds)
        return 'OK'

    def _handle_append(self, args):
        """APPEND <key> <value> — append to existing value or create new."""
        if len(args) < 2:
            return 'ERR unknown_command'

        key = args[0]
        append_value = ' '.join(args[1:])

        entry = self._store.get(key)
        if entry is not None and not self._is_expired(key):
            # Key exists and is not expired — append
            existing_value, expiry = entry
            new_value = existing_value + append_value
        else:
            # Key doesn't exist or has expired — treat as new
            new_value = append_value
            expiry = None
            if key not in self._store and len(self._store) >= self.max_keys:
                return 'ERR store_full'
            if len(key) > self.max_key_length:
                return 'ERR key_too_long'

        if len(new_value) > self.max_value_size:
            return 'ERR value_too_large'

        self._store[key] = (new_value, expiry)
        return f'OK {len(new_value)}'

    # ── MAY Commands ─────────────────────────────────────────────────────

    def _handle_rename(self, args):
        """RENAME <old_key> <new_key> — rename a key."""
        if len(args) != 2:
            return 'ERR unknown_command'

        old_key = args[0]
        new_key = args[1]

        if old_key not in self._store:
            return 'ERR key_not_found'
        if len(new_key) > self.max_key_length:
            return 'ERR key_too_long'

        self._store[new_key] = self._store.pop(old_key)
        return 'OK'

    def _handle_type(self, args):
        """TYPE <key> — return the type of the value (STRING or INTEGER)."""
        if len(args) != 1:
            return 'ERR unknown_command'

        key = args[0]
        if key not in self._store or self._is_expired(key):
            return 'ERR key_not_found'

        value = self._store[key][0]
        try:
            int(value)
            return 'INTEGER'
        except ValueError:
            return 'STRING'

    def _handle_dump(self, args):
        """DUMP — return all key-value pairs, terminated by END."""
        if len(args) != 0:
            return 'ERR unknown_command'

        lines = []
        for key in self._store:
            if not self._is_expired(key):
                lines.append(f'{key}={self._store[key][0]}')
        lines.append('END')
        return '\n'.join(lines)
