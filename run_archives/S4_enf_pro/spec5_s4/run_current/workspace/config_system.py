"""
Configuration system for the application.

Implements loading and validating configuration from multiple sources
with a four-level priority cascade:

    cli_args > env_vars > config_file > defaults

Provides:
    - ConfigValidationError  — exception class for validation failures
    - load_config()           — merge and validate config from all sources
    - get_schema()            — return the full config schema dict
    - validate_value()        — validate and coerce a single value
"""

import json
import os
from typing import Any

# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------

class ConfigValidationError(ValueError):
    """Raised when a config value fails validation."""

# ---------------------------------------------------------------------------
# Full config schema (10 keys)
# ---------------------------------------------------------------------------

_SCHEMA: dict[str, dict] = {
    "host": {
        "type": "string",
        "default": "0.0.0.0",
        "env_var": "WEB_HOST",
        "description": "Hostname or IP address to bind",
        "validation": {"non_empty": True},
    },
    "port": {
        "type": "int",
        "default": 6155,
        "env_var": "WEB_PORT",
        "description": "TCP port to listen on; must be 2048-49151",
        "validation": {"range": [2048, 49151]},
    },
    "log_level": {
        "type": "enum",
        "default": "WARN",
        "env_var": "WEB_LOG_LEVEL",
        "description": "Logging verbosity; one of ['INFO', 'WARN', 'ERROR']",
        "validation": {"allowed": ["INFO", "WARN", "ERROR"]},
    },
    "request_timeout": {
        "type": "int",
        "default": 120,
        "env_var": "WEB_REQUEST_TIMEOUT",
        "description": "Request timeout in seconds; must be 1-3600",
        "validation": {"range": [1, 3600]},
    },
    "max_connections": {
        "type": "int",
        "default": 348,
        "env_var": "WEB_MAX_CONNECTIONS",
        "description": "Maximum concurrent connections; must be 1-1000",
        "validation": {"range": [1, 1000]},
    },
    "debug_mode": {
        "type": "bool",
        "default": False,
        "env_var": "WEB_DEBUG",
        "description": "Enable debug mode; accepts true/false, 1/0, yes/no, on/off",
        "validation": {},
    },
    "static_dir": {
        "type": "string",
        "default": "./static",
        "env_var": "WEB_STATIC_DIR",
        "description": "Path to static files directory",
        "validation": {"non_empty": True},
    },
    "cors_origins": {
        "type": "string",
        "default": "*",
        "env_var": "WEB_CORS_ORIGINS",
        "description": "Allowed CORS origins, comma-separated",
        "validation": {},
    },
    "keep_alive_timeout": {
        "type": "int",
        "default": 10,
        "env_var": "WEB_KEEP_ALIVE_TIMEOUT",
        "description": "Keep-alive timeout in seconds; must be 1-300",
        "validation": {"range": [1, 300]},
    },
    "ssl_enabled": {
        "type": "bool",
        "default": False,
        "env_var": "WEB_SSL_ENABLED",
        "description": "Enable SSL/TLS; accepts true/false, 1/0, yes/no, on/off",
        "validation": {},
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_schema() -> dict:
    """Return the config schema as a dict (key -> spec dict)."""
    return _SCHEMA


def validate_value(key: str, value: Any) -> Any:
    """
    Validate and coerce a single value against the schema for *key*.

    Steps:
    1. Look up *key* in ``_SCHEMA``; raise ``ConfigValidationError`` if not found.
    2. If *value* is ``None`` → return the default from the schema.
    3. Apply type coercion according to ``_SCHEMA[key]["type"]``.
    4. Apply validation rules from ``_SCHEMA[key]["validation"]``.
    5. Return the coerced (and valid) value.
    """
    if key not in _SCHEMA:
        raise ConfigValidationError(
            f"Unknown config key: '{key}'"
        )

    spec = _SCHEMA[key]
    if value is None:
        return spec["default"]

    schema_type = spec["type"]
    validation = spec.get("validation", {})

    # -- Type coercion -------------------------------------------------------

    if schema_type == "string":
        if not isinstance(value, str):
            value = str(value)
        if validation.get("non_empty") and (not value or value == ""):
            raise ConfigValidationError(
                f"Invalid value for '{key}': {value!r} — must not be empty"
            )

    elif schema_type == "int":
        if not isinstance(value, int):
            try:
                value = int(value)
            except (ValueError, TypeError):
                raise ConfigValidationError(
                    f"Invalid value for '{key}': {value!r} — not a valid integer"
                )
        range_rule = validation.get("range")
        if range_rule:
            low, high = range_rule
            if not (low <= value <= high):
                raise ConfigValidationError(
                    f"Invalid value for '{key}': {value!r} — must be between {low} and {high}"
                )

    elif schema_type == "enum":
        value = str(value)
        allowed = validation.get("allowed", [])
        if value not in allowed:
            raise ConfigValidationError(
                f"Invalid value for '{key}': {value!r} — must be one of {allowed}"
            )

    elif schema_type == "bool":
        if isinstance(value, bool):
            pass  # already a bool, keep it
        elif isinstance(value, int):
            value = bool(value)
        elif isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in ("true", "1", "yes", "on"):
                value = True
            elif lowered in ("false", "0", "no", "off"):
                value = False
            else:
                raise ConfigValidationError(
                    f"Invalid value for '{key}': {value!r} — "
                    f"not a valid boolean (accepted: true/false, 1/0, yes/no, on/off)"
                )
        else:
            raise ConfigValidationError(
                f"Invalid value for '{key}': {value!r} — "
                f"not a valid boolean (accepted: true/false, 1/0, yes/no, on/off)"
            )

    return value


def load_config(
    config_file: str | None = None,
    env_vars: dict | None = None,
    cli_args: dict | None = None,
) -> dict:
    """
    Load and validate configuration from all sources.

    Priority (highest first):
        cli_args  >  env_vars  >  config_file  >  defaults

    Parameters
    ----------
    config_file : str | None
        Path to a JSON config file.  ``None`` → skip file loading.
    env_vars : dict | None
        Environment variable dict.  ``None`` → use ``os.environ``.
    cli_args : dict | None
        CLI argument dict (keyed by schema key name).  ``None`` → skip.

    Returns
    -------
    dict
        Fully resolved and validated configuration (all 10 keys present).
    """
    # --- Step 0: populate with defaults ------------------------------------
    result: dict[str, Any] = {}
    for key, spec in _SCHEMA.items():
        result[key] = spec["default"]

    # --- Step 1: config file (priority 3) ----------------------------------
    if config_file is not None:
        if not os.path.isfile(config_file):
            raise FileNotFoundError(f"Config file not found: {config_file}")
        with open(config_file, "r", encoding="utf-8") as f:
            file_data = json.load(f)
        for key in _SCHEMA:
            if key in file_data and file_data[key] is not None:
                result[key] = validate_value(key, file_data[key])

    # --- Step 2: environment variables (priority 2) ------------------------
    if env_vars is None:
        env_vars = os.environ
    for key, spec in _SCHEMA.items():
        env_name = spec["env_var"]
        if env_name in env_vars:
            raw = env_vars[env_name]
            # empty string means "not set" for env vars
            if raw != "":
                result[key] = validate_value(key, raw)

    # --- Step 3: CLI args (priority 1, highest) ----------------------------
    if cli_args is not None:
        for key in _SCHEMA:
            if key in cli_args and cli_args[key] is not None:
                result[key] = validate_value(key, cli_args[key])

    return result
