"""
Configuration system for the web service application.

Implements multi-source config loading with priority cascade:
    cli_args > env_vars > config_file > built-in defaults

All 10 config keys with full type coercion and validation.
"""

import copy
import json
import os
from typing import Any


# ---------------------------------------------------------------------------
# 1. ConfigValidationError
# ---------------------------------------------------------------------------

class ConfigValidationError(ValueError):
    """Raised when a config value fails validation."""
    pass


# ---------------------------------------------------------------------------
# 2. Schema definition (module-level constant)
# ---------------------------------------------------------------------------

_SCHEMA: dict[str, dict] = {
    "host": {
        "type": "string",
        "default": "0.0.0.0",
        "env": "WEB_HOST",
        "validate": lambda v: isinstance(v, str) and len(v) > 0,
        "description": "Hostname or IP address to bind",
    },
    "port": {
        "type": "int",
        "default": 6155,
        "env": "WEB_PORT",
        "range": (2048, 49151),
        "description": "TCP port to listen on",
    },
    "log_level": {
        "type": "enum",
        "default": "WARN",
        "env": "WEB_LOG_LEVEL",
        "allowed": ["INFO", "WARN", "ERROR"],
        "description": "Logging verbosity",
    },
    "request_timeout": {
        "type": "int",
        "default": 120,
        "env": "WEB_REQUEST_TIMEOUT",
        "range": (1, 3600),
        "description": "Request timeout in seconds",
    },
    "max_connections": {
        "type": "int",
        "default": 348,
        "env": "WEB_MAX_CONNECTIONS",
        "range": (1, 1000),
        "description": "Maximum concurrent connections",
    },
    "debug_mode": {
        "type": "bool",
        "default": False,
        "env": "WEB_DEBUG",
        "description": "Enable debug mode",
    },
    "static_dir": {
        "type": "string",
        "default": "./static",
        "env": "WEB_STATIC_DIR",
        "validate": lambda v: isinstance(v, str) and len(v) > 0,
        "description": "Path to static files directory",
    },
    "cors_origins": {
        "type": "string",
        "default": "*",
        "env": "WEB_CORS_ORIGINS",
        "description": "Allowed CORS origins, comma-separated",
    },
    "keep_alive_timeout": {
        "type": "int",
        "default": 10,
        "env": "WEB_KEEP_ALIVE_TIMEOUT",
        "range": (1, 300),
        "description": "Keep-alive timeout seconds",
    },
    "ssl_enabled": {
        "type": "bool",
        "default": False,
        "env": "WEB_SSL_ENABLED",
        "description": "Enable SSL/TLS",
    },
}


# ---------------------------------------------------------------------------
# 3. Environment variable → config key reverse mapping
# ---------------------------------------------------------------------------

_ENV_TO_KEY: dict[str, str] = {
    "WEB_HOST": "host",
    "WEB_PORT": "port",
    "WEB_LOG_LEVEL": "log_level",
    "WEB_REQUEST_TIMEOUT": "request_timeout",
    "WEB_MAX_CONNECTIONS": "max_connections",
    "WEB_DEBUG": "debug_mode",
    "WEB_STATIC_DIR": "static_dir",
    "WEB_CORS_ORIGINS": "cors_origins",
    "WEB_KEEP_ALIVE_TIMEOUT": "keep_alive_timeout",
    "WEB_SSL_ENABLED": "ssl_enabled",
}


# ---------------------------------------------------------------------------
# 4. Type coercion helpers
# ---------------------------------------------------------------------------

def _coerce_bool(key: str, value: Any) -> bool:
    """Coerce a value to bool.

    Accepted (case-insensitive strings): true/false, 1/0, yes/no, on/off
    Accepted (numeric): 1, 0
    Accepted (native): True, False
    """
    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        if value in (0, 1):
            return bool(value)
        raise ConfigValidationError(
            f"Invalid value for '{key}': {value!r} — "
            f"bool coercion only accepts 0 or 1 for numeric types"
        )

    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("true", "1", "yes", "on"):
            return True
        if v in ("false", "0", "no", "off"):
            return False

    raise ConfigValidationError(
        f"Invalid value for '{key}': {value!r} — cannot coerce to bool "
        f"(accepted: true/false, 1/0, yes/no, on/off)"
    )


# ---------------------------------------------------------------------------
# 5. get_schema()
# ---------------------------------------------------------------------------

def get_schema() -> dict:
    """Return the full config schema as a deep-copied dict (key → spec dict)."""
    return copy.deepcopy(_SCHEMA)


# ---------------------------------------------------------------------------
# 6. validate_value()
# ---------------------------------------------------------------------------

def validate_value(key: str, value: Any) -> Any:
    """Validate and coerce a single value against the schema for *key*.

    Returns the coerced value.  Raises ``ConfigValidationError`` if the value
    is invalid or cannot be coerced.
    """
    if key not in _SCHEMA:
        raise ConfigValidationError(f"Unknown config key: {key!r}")

    spec = _SCHEMA[key]
    target_type = spec["type"]

    # --- Step 1: Type coercion ---
    if target_type == "int":
        try:
            coerced = int(value)
        except (ValueError, TypeError):
            raise ConfigValidationError(
                f"Invalid value for '{key}': {value!r} — expected integer"
            )
    elif target_type == "bool":
        coerced = _coerce_bool(key, value)
    elif target_type == "enum":
        if not isinstance(value, str):
            raise ConfigValidationError(
                f"Invalid value for '{key}': {value!r} — expected string for enum"
            )
        coerced = value
    elif target_type == "string":
        coerced = str(value)
    elif target_type == "float":
        try:
            coerced = float(value)
        except (ValueError, TypeError):
            raise ConfigValidationError(
                f"Invalid value for '{key}': {value!r} — expected float"
            )
    else:
        raise ConfigValidationError(
            f"Unknown type '{target_type}' for key '{key}'"
        )

    # --- Step 2: Post-coercion validation ---
    if target_type == "int" and "range" in spec:
        lo, hi = spec["range"]
        if not (lo <= coerced <= hi):
            raise ConfigValidationError(
                f"Invalid value for '{key}': {coerced!r} — "
                f"must be in range [{lo}, {hi}]"
            )
    elif target_type == "string":
        # host and static_dir require non-empty; cors_origins has no extra check
        if "validate" in spec:
            if not spec["validate"](coerced):
                raise ConfigValidationError(
                    f"Invalid value for '{key}': {coerced!r} — "
                    f"must be a non-empty string"
                )
    elif target_type == "enum":
        if coerced not in spec["allowed"]:
            raise ConfigValidationError(
                f"Invalid value for '{key}': {coerced!r} — "
                f"must be one of {spec['allowed']}"
            )

    return coerced


# ---------------------------------------------------------------------------
# 7. load_config()
# ---------------------------------------------------------------------------

def load_config(
    config_file: str | None = None,
    env_vars: dict | None = None,
    cli_args: dict | None = None,
) -> dict:
    """Load and validate configuration from all sources in priority order.

    Priority cascade (highest to lowest):
        1. CLI args   (*cli_args* dict)
        2. Env vars   (*env_vars* dict, defaults to ``os.environ``)
        3. Config file (JSON file path, *config_file*)
        4. Built-in defaults (from ``_SCHEMA``)

    Parameters
    ----------
    config_file:
        Path to a JSON config file.  If *None*, the file layer is skipped.
    env_vars:
        Dict of environment variables.  If *None*, ``os.environ`` is used.
    cli_args:
        Dict of CLI-supplied overrides (keys are config key names, not env
        var names).  If *None*, the CLI layer is skipped.

    Returns
    -------
    dict
        Resolved configuration dict with all 10 keys populated.

    Raises
    ------
    ConfigValidationError
        If any value fails type coercion or validation.
    FileNotFoundError
        If *config_file* is provided but does not exist on disk.
    """
    result: dict[str, object] = {}

    # Layer 4 (lowest): built-in defaults
    for key, spec in _SCHEMA.items():
        result[key] = spec["default"]

    # Layer 3: config file
    if config_file is not None:
        if not os.path.isfile(config_file):
            raise FileNotFoundError(f"Config file not found: {config_file}")
        with open(config_file, "r", encoding="utf-8") as f:
            file_data = json.load(f)
        for key, raw_value in file_data.items():
            if key in _SCHEMA:          # unknown keys are silently ignored
                result[key] = validate_value(key, raw_value)

    # Layer 2: environment variables
    if env_vars is None:
        env_vars = dict(os.environ)
    for env_name, key in _ENV_TO_KEY.items():
        if env_name in env_vars:
            result[key] = validate_value(key, env_vars[env_name])

    # Layer 1 (highest): CLI args
    if cli_args is not None:
        for key, raw_value in cli_args.items():
            if key in _SCHEMA:
                result[key] = validate_value(key, raw_value)

    return result
