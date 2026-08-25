# Changelog

## core v1.2.0
- Added `BaseProcessor` class in `core.base`
- Moved `process_item()` from `core.processing` to `utils.processing`

## core v1.0
- Initial release with `process_item()` in `core.processing`
- Basic validation and normalization utilities

## models v1.1.0
- Added `UserModel` entity
- Added `helpers.py` with `serialize_entity()` (requires `format_response`)

## api v1.0.0
- REST endpoint definitions
- Response formatters including `format_response()`

## utils v1.1.0
- Received `process_item()` from `core.processing`
- Added `format_response()` in `utils.formatters`
- NOTE: `setup.cfg` still pins `core==1.0` — needs update to `>=1.2`

## worker v1.0.0
- Background job processing
- NOTE: Still imports `process_item` from `core.processing` — needs update
