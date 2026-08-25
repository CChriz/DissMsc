# SPEC6: RFC-Style Protocol Implementation

## Goal
Implement a simple text-based key-value store protocol from an RFC-style specification. The protocol has 20 requirements classified as MUST, SHOULD, and MAY. All 12 MUST requirements must be satisfied, plus at least 3 of 5 SHOULD requirements to pass.

## Protocol Overview
The protocol (KVP — Key-Value Protocol) is a line-oriented text protocol for a simple in-memory key-value store. Commands and responses are delimited by a configurable delimiter (default newline). Each command is a single line; responses follow a structured format.

## Protocol Specification

### MUST Requirements (12 — all must pass)

**M1**: The server MUST accept a `SET` command in the format `SET <key> <value>` and store the value.

**M2**: The server MUST accept a `GET` command in the format `GET <key>` and return the stored value. If the key does not exist, the server MUST return an error response `ERR key_not_found`.

**M3**: The server MUST accept a `DEL` command in the format `DEL <key>` and remove the key. If the key does not exist, the server MUST return `ERR key_not_found`.

**M4**: The server MUST accept a `KEYS` command (no arguments) and return a list of all stored keys, one per line, terminated by `END`.

**M5**: The server MUST accept a `COUNT` command (no arguments) and return the total number of stored keys as `COUNT <n>`.

**M6**: The server MUST accept a `EXISTS` command in the format `EXISTS <key>` and return `TRUE` if the key exists, `FALSE` otherwise.

**M7**: The server MUST accept a `FLUSH` command (no arguments) that removes all stored keys and returns `OK`.

**M8**: The server MUST return `OK` for successful `SET` and `DEL` operations.

**M9**: The server MUST return `ERR unknown_command` for any unrecognized command.

**M10**: The server MUST enforce a maximum key length. Keys exceeding the limit MUST be rejected with `ERR key_too_long`.

**M11**: The server MUST enforce a maximum value size. Values exceeding the limit MUST be rejected with `ERR value_too_large`.

**M12**: The server MUST enforce a maximum number of stored keys. Attempting to SET when at capacity MUST return `ERR store_full` (unless the key already exists, which is an update).

### SHOULD Requirements (5 — at least 3 must pass)

**S1**: The server SHOULD accept a `MSET` command in the format `MSET <key1> <value1> <key2> <value2> ...` for setting multiple key-value pairs atomically. Returns `OK <n>` where n is the number of keys set.

**S2**: The server SHOULD accept a `MGET` command in the format `MGET <key1> <key2> ...` for retrieving multiple values. Returns each value on a separate line (or `NIL` for missing keys), terminated by `END`.

**S3**: The server SHOULD support a `TTL` command in the format `TTL <key>` that returns the remaining time-to-live in seconds, or `-1` if the key has no expiry, or `ERR key_not_found` if the key does not exist.

**S4**: The server SHOULD accept a `SETEX` command in the format `SETEX <key> <seconds> <value>` that sets a key with an expiration time. Expired keys SHOULD be treated as non-existent.

**S5**: The server SHOULD accept an `APPEND` command in the format `APPEND <key> <value>` that appends to an existing value or creates a new key if it does not exist. Returns `OK <new_length>` where new_length is the length of the resulting value.

### MAY Requirements (3 — optional, bonus)

**Y1**: The server MAY accept a `RENAME` command in the format `RENAME <old_key> <new_key>` to rename a key. Returns `OK` on success or `ERR key_not_found`.

**Y2**: The server MAY accept a `TYPE` command in the format `TYPE <key>` that returns the type of the stored value (e.g., `STRING`, `INTEGER`). Returns `ERR key_not_found` if missing.

**Y3**: The server MAY accept a `DUMP` command (no arguments) that returns all key-value pairs, one per line as `<key>=<value>`, terminated by `END`.

## Response Format
- Success responses: `OK`, `OK <detail>`, `TRUE`, `FALSE`, `COUNT <n>`
- Value responses: the raw value on a line by itself
- List responses: one item per line, terminated by `END`
- Error responses: `ERR <error_code>`

## Grading
- All 12 MUST requirements satisfied: mandatory
- At least 3 of 5 SHOULD requirements: mandatory for pass
- MAY requirements: bonus (partial credit)
- Score = (MUST_passed/12 * 0.6) + (SHOULD_passed/5 * 0.3) + (MAY_passed/3 * 0.1)

## Deliverables
- Complete implementation of `protocol.py` with the `KVStore` class
- All existing tests in `tests/test_protocol.py` must pass
- Verifier must validate compliance with each requirement
