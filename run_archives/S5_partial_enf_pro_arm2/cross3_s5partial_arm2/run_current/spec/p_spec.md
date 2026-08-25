# CROSS3: Protocol Bridge — JSON to Message Translation

## Goal
Fix translation bugs and an error mapping bug in the bridge service that translates
Service A's JSON REST API responses into structured messages for Service B's consumer.

## Requirements
1. int64 fields must be translated as Python int (no truncation to 32-bit)
2. bytes fields must be base64-decoded from JSON strings
3. HTTP 404 from Service A must map to NOT_FOUND error code (5) for Service B
4. All tests must pass: `pytest tests/`

## Supporting Documents
- `service_a/models.py` — JSON data models from Service A
- `service_b/schema.py` — Message schema for Service B (proto3-style)
- `bridge/translator.py` — JSON→Message translation
- `bridge/error_mapper.py` — HTTP status → error code

## Background

The bridge service sits between Service A (a REST API returning JSON) and Service B
(a queue consumer expecting structured proto3-style messages). Because JSON and proto3
have different type semantics, every field crossing this boundary needs a careful
type conversion.

### Type Semantic Differences

| JSON Type | Proto3 Type | Issue |
|-----------|-------------|-------|
| number    | int64       | JSON numbers lose precision for values > 2^53; must not be masked to 32-bit |
| string    | bytes       | Binary data is base64-encoded in JSON; must be decoded to bytes |

### Error Code Mapping

Service A returns HTTP status codes. Service B uses gRPC-style integer error codes:

| HTTP Status | Expected Error Code | Code Number |
|-------------|---------------------|-------------|
| 200         | OK                  | 0           |
| 400         | INVALID_ARGUMENT    | 3           |
| 401/403     | INVALID_ARGUMENT    | 3           |
| 404         | NOT_FOUND           | 5           |
| 5xx         | INTERNAL            | 13          |

## Real-World Context
JSON-to-gRPC transcoding bridges are a common integration layer in microservice
architectures, and the bugs in this task reflect bugs documented in real transcoding
implementations:
- **int64 truncation**: JavaScript's `JSON.parse()` silently truncates 64-bit
  integers beyond `Number.MAX_SAFE_INTEGER` (2^53-1). This caused data loss in the
  Twitter Snowflake ID migration (2010) and is documented in the gRPC-Gateway project
  FAQ. Fix: serialize int64 as strings in JSON.
- **bytes base64 handling**: Proto3 `bytes` fields must be base64-encoded in
  JSON (RFC 4648). The gRPC-Gateway library had exactly this bug in v1.x — binary
  fields were passed through raw, corrupting payloads. CVE-class issue in several
  open-source gRPC-JSON bridges.
- **Error code mapping**: gRPC status codes (google.rpc.Code) are a strict mapping
  from HTTP status; 404→NOT_FOUND(5) is specified in google.rpc.Code and commonly
  misimplemented.
