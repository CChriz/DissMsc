# Analysis Guidance — CROSS3_protocol_bridge

## Tools to run
- `cat service_a/models.py` — JSON field types from Service A
- `cat service_b/schema.py` — Message schema for Service B
- `cat bridge/translator.py` — find all 4 translation bugs
- `cat bridge/error_mapper.py` — find 2 error mapping bugs

## The 4 Translation Bugs

### Bug 1: int64 truncation (bridge/translator.py)
JSON sends large integers (e.g., 9007199254740993) that fit in int64 but not int32.
**Current**: `msg.record_id = int(data["record_id"]) & 0xFFFFFFFF`  # truncates!
**Fix**: `msg.record_id = int(data["record_id"])`  # use full int64 value

### Bug 2: bytes field not base64-decoded (bridge/translator.py)
Service A sends binary data as base64 strings; Service B expects bytes.
**Current**: `msg.payload = data["payload"]`  # string, not bytes!
**Fix**: `import base64; msg.payload = base64.b64decode(data["payload"])`

### Bug 3: oneof field — multiple variants set (bridge/translator.py)
The message has a oneof field {content_text, content_binary}. Code sets both.
**Current**: `msg.content_text = data.get("text_content", ""); msg.content_binary = data.get("binary_content", b"")`
**Fix**: Only set one variant based on which field is present in data

### Bug 4: enum field string → int mapping (bridge/translator.py)
Service A sends enum values as strings ("STATUS_ACTIVE"); Service B needs integers (1).
**Current**: `msg.status = data["status"]`  # string, not int!
**Fix**: Use STATUS_MAP dict to convert: `msg.status = STATUS_MAP[data["status"]]`

## The 2 Error Mapping Bugs

### Bug 5: HTTP 404 → wrong error code (bridge/error_mapper.py)
**Current**: `if status_code == 404: return StatusMessage(code=ErrorCode.INVALID_ARGUMENT, ...)`  # code 3
**Fix**: `if status_code == 404: return StatusMessage(code=ErrorCode.NOT_FOUND, ...)`  # code 5

### Bug 6: HTTP 429 → wrong error code (bridge/error_mapper.py)
**Current**: `if status_code == 429: return StatusMessage(code=ErrorCode.INTERNAL, ...)`  # code 13
**Fix**: `if status_code == 429: return StatusMessage(code=ErrorCode.RESOURCE_EXHAUSTED, ...)`  # code 8

## Tell Executor
Fix bugs in bridge/translator.py and bridge/error_mapper.py only.
Do not change service_a/ or service_b/ files.
