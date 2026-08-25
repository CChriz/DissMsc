"""
Configuration system for the Worker Service.

Implements:
- ConfigValidationError: exception class for config validation failures
- load_config(): loads config from all sources with priority cascade
- get_schema(): returns the full config schema
- validate_value(): validates and coerces a single config value
"""

import json
import os
from typing import Any


# =============================================================================
# ConfigValidationError
# =============================================================================

class ConfigValidationError(ValueError):
    """Raised when a config value fails validation."""
    pass


# =============================================================================
# Full Schema Definition (11 keys)
# =============================================================================

_SCHEMA: dict[str, dict[str, Any]] = {
    "queue_url": {
        "type": "string",
        "default": "redis://localhost:6379/0",
        "env_var": "CELERY_QUEUE_URL",
        "validation": {"non_empty": True},
    },
    "concurrency": {
        "type": "int",
        "default": 3,
        "env_var": "CELERY_CONCURRENCY",
        "validation": {"min": 1, "max": 32},
    },
    "max_retries": {
        "type": "int",
        "default": 8,
        "env_var": "CELERY_MAX_RETRIES",
        "validation": {"min": 0, "max": 20},
    },
    "retry_backoff_seconds": {
        "type": "int",
        "default": 1,
        "env_var": "CELERY_RETRY_BACKOFF",
        "validation": {"min": 1, "max": 300},
    },
    "job_timeout": {
        "type": "int",
        "default": 300,
        "env_var": "CELERY_JOB_TIMEOUT",
        "validation": {"min": 1, "max": 3600},
    },
    "log_level": {
        "type": "enum",
        "default": "INFO",
        "env_var": "CELERY_LOG_LEVEL",
        "validation": {"allowed": ["DEBUG", "INFO", "WARN"]},
    },
    "dead_letter_queue": {
        "type": "bool",
        "default": True,
        "env_var": "CELERY_DEAD_LETTER",
        "validation": {},
    },
    "heartbeat_interval": {
        "type": "int",
        "default": 60,
        "env_var": "CELERY_HEARTBEAT",
        "validation": {"min": 5, "max": 300},
    },
    "prefetch_count": {
        "type": "int",
        "default": 10,
        "env_var": "CELERY_PREFETCH",
        "validation": {"min": 1, "max": 100},
    },
    "ack_on_failure": {
        "type": "bool",
        "default": False,
        "env_var": "CELERY_ACK_ON_FAILURE",
        "validation": {},
    },
    "metrics_enabled": {
        "type": "bool",
        "default": True,
        "env_var": "CELERY_METRICS",
        "validation": {},
    },
}


# =============================================================================
# Internal Helpers
# =============================================================================

def _coerce_value(key: str, raw_value: Any, spec: dict[str, Any]) -> Any:
    """Coerce a raw value to the expected type from the schema spec.

    Args:
        key: Configuration key name.
        raw_value: Raw value (typically string from env vars or CLI).
        spec: Schema specification dict for this key.

    Returns:
        Coerced value of the correct type.

    Raises:
        ConfigValidationError: If the value cannot be coerced.
    """
    expected_type = spec["type"]

    if expected_type == "string":
        return str(raw_value)

    elif expected_type == "int":
        try:
            return int(raw_value)
        except (ValueError, TypeError):
            raise ConfigValidationError(
                f"Invalid value for '{key}': {raw_value!r} (not a valid integer)"
            )

    elif expected_type == "float":
        try:
            return float(raw_value)
        except (ValueError, TypeError):
            raise ConfigValidationError(
                f"Invalid value for '{key}': {raw_value!r} (not a valid float)"
            )

    elif expected_type == "bool":
        if isinstance(raw_value, bool):
            return raw_value
        if isinstance(raw_value, str):
            lower = raw_value.strip().lower()
            if lower in ("true", "1", "yes", "on"):
                return True
            elif lower in ("false", "0", "no", "off"):
                return False
        raise ConfigValidationError(
            f"Invalid value for '{key}': {raw_value!r} (not a valid boolean)"
        )

    elif expected_type == "enum":
        value = str(raw_value)
        allowed = spec.get("validation", {}).get("allowed", [])
        if value in allowed:
            return value
        raise ConfigValidationError(
            f"Invalid value for '{key}': {raw_value!r} "
            f"(must be one of {allowed})"
        )

    # Fallback — should not happen with a valid schema
    return raw_value


# =============================================================================
# Public API
# =============================================================================

def validate_value(key: str, value: Any) -> Any:
    """Validate and coerce a single value for the given config key.

    Args:
        key: Configuration key name (must exist in schema).
        value: Raw value to validate and coerce.

    Returns:
        Validated and type-coerced value.

    Raises:
        ConfigValidationError: If key is unknown or value is invalid.
    """
    if key not in _SCHEMA:
        raise ConfigValidationError(f"Unknown config key: '{key}'")

    spec = _SCHEMA[key]
    coerced = _coerce_value(key, value, spec)

    validation = spec.get("validation", {})

    # int range checks
    if spec["type"] == "int":
        if "min" in validation and coerced < validation["min"]:
            raise ConfigValidationError(
                f"Invalid value for '{key}': {coerced} "
                f"(must be in range [{validation['min']}, {validation['max']}])"
            )
        if "max" in validation and coerced > validation["max"]:
            raise ConfigValidationError(
                f"Invalid value for '{key}': {coerced} "
                f"(must be in range [{validation['min']}, {validation['max']}])"
            )

    # string non-empty check
    if spec["type"] == "string":
        if validation.get("non_empty") and len(coerced) == 0:
            raise ConfigValidationError(
                f"Invalid value for '{key}': '' (must not be empty)"
            )

    return coerced


def get_schema() -> dict[str, dict[str, Any]]:
    """Return the config schema as a dict (key -> spec dict)."""
    return dict(_SCHEMA)


def load_config(
    config_file: str | None = None,
    env_vars: dict[str, str] | None = None,
    cli_args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load and validate configuration from all sources.

    Priority cascade (highest first):
        cli_args > env_vars > config_file > built-in defaults

    Args:
        config_file: Optional path to a JSON config file.
        env_vars: Optional dict of environment variables (defaults to os.environ).
        cli_args: Optional dict of CLI arguments.

    Returns:
        Dict with all 11 config keys populated.

    Raises:
        FileNotFoundError: If config_file is specified but does not exist.
        ConfigValidationError: If any value fails validation.
    """
    # Step 1: Start with built-in defaults
    result: dict[str, Any] = {}
    for key, spec in _SCHEMA.items():
        result[key] = spec["default"]

    # Step 2: Config file (overrides defaults)
    if config_file is not None:
        if not os.path.exists(config_file):
            raise FileNotFoundError(f"Config file not found: {config_file}")
        with open(config_file, "r", encoding="utf-8") as f:
            file_data = json.load(f)
        for key, raw_value in file_data.items():
            if key in _SCHEMA:
                result[key] = validate_value(key, raw_value)
            # Unknown keys in config file are silently ignored

    # Step 3: Environment variables (override config file)
    env = env_vars if env_vars is not None else dict(os.environ)
    for key, spec in _SCHEMA.items():
        env_var_name = spec["env_var"]
        if env_var_name in env:
            result[key] = validate_value(key, env[env_var_name])

    # Step 4: CLI arguments (highest priority, override everything)
    if cli_args is not None:
        for key, raw_value in cli_args.items():
            if key in _SCHEMA:
                result[key] = validate_value(key, raw_value)
            # Unknown CLI keys are silently ignored

    return result
