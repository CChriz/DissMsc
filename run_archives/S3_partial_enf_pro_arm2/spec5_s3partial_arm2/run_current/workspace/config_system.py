"""
Configuration system for the web service application.

Implements multi-source configuration loading with priority cascade:
CLI args > environment variables > config file > defaults.
"""
import json
import os
from typing import Any


# ===========================================================================
# 1. Exception
# ===========================================================================
class ConfigValidationError(ValueError):
    """Raised when a config value fails validation or coercion.

    Attributes:
        key: The config key that failed validation.
        value: The raw value that was rejected.
        reason: Human-readable explanation of the failure.
    """

    def __init__(self, key: str, value: object, reason: str) -> None:
        self.key = key
        self.value = value
        self.reason = reason
        super().__init__(f"Invalid value for '{key}': {value!r} — {reason}")


# ===========================================================================
# 2. Schema
# ===========================================================================
_SCHEMA: dict[str, dict] = {
    "host": {
        "type": "string",
        "default": "0.0.0.0",
        "env_var": "WEB_HOST",
        "validation": {"non_empty": True},
    },
    "port": {
        "type": "int",
        "default": 6155,
        "env_var": "WEB_PORT",
        "validation": {"min": 2048, "max": 49151},
    },
    "log_level": {
        "type": "enum",
        "default": "WARN",
        "env_var": "WEB_LOG_LEVEL",
        "validation": {"allowed": ["INFO", "WARN", "ERROR"]},
    },
    "request_timeout": {
        "type": "int",
        "default": 120,
        "env_var": "WEB_REQUEST_TIMEOUT",
        "validation": {"min": 1, "max": 3600},
    },
    "max_connections": {
        "type": "int",
        "default": 348,
        "env_var": "WEB_MAX_CONNECTIONS",
        "validation": {"min": 1, "max": 1000},
    },
    "debug_mode": {
        "type": "bool",
        "default": False,
        "env_var": "WEB_DEBUG",
        "validation": {},
    },
    "static_dir": {
        "type": "string",
        "default": "./static",
        "env_var": "WEB_STATIC_DIR",
        "validation": {"non_empty": True},
    },
    "cors_origins": {
        "type": "string",
        "default": "*",
        "env_var": "WEB_CORS_ORIGINS",
        "validation": {},
    },
    "keep_alive_timeout": {
        "type": "int",
        "default": 10,
        "env_var": "WEB_KEEP_ALIVE_TIMEOUT",
        "validation": {"min": 1, "max": 300},
    },
    "ssl_enabled": {
        "type": "bool",
        "default": False,
        "env_var": "WEB_SSL_ENABLED",
        "validation": {},
    },
}


# ===========================================================================
# 3. Type coercion — private helpers
# ===========================================================================

# Bool coercion constants (case-insensitive after strip)
_BOOL_TRUE_STRINGS = frozenset({"true", "1", "yes", "on"})
_BOOL_FALSE_STRINGS = frozenset({"false", "0", "no", "off"})


def _coerce_int(key: str, raw_value: object) -> int:
    """Coerce *raw_value* to an ``int`` for config *key*.

    Rules:
        - ``int`` (not ``bool``) → returned as-is.
        - ``str`` → parsed via ``int()``.
        - ``float`` → accepted only when ``float.is_integer()`` is True
          (e.g. ``3.0`` → 3, ``3.14`` → error).
        - ``bool`` → explicitly rejected (Python ``bool`` is a subclass of
          ``int``, but boolean values are not valid integer config values).
        - Everything else → ``ConfigValidationError``.
    """
    # Explicit bool check MUST come before int check (bool ⊂ int in Python)
    if isinstance(raw_value, bool):
        raise ConfigValidationError(key, raw_value, "must be a valid integer")

    if isinstance(raw_value, int):
        return raw_value

    if isinstance(raw_value, float):
        if raw_value.is_integer():
            return int(raw_value)
        raise ConfigValidationError(key, raw_value, "must be a valid integer")

    if isinstance(raw_value, str):
        stripped = raw_value.strip()
        if stripped == "":
            raise ConfigValidationError(key, raw_value, "must be a valid integer")
        try:
            return int(stripped)
        except (ValueError, TypeError):
            raise ConfigValidationError(key, raw_value, "must be a valid integer")

    raise ConfigValidationError(key, raw_value, "must be a valid integer")


def _coerce_float(key: str, raw_value: object) -> float:
    """Coerce *raw_value* to a ``float`` for config *key*.

    Rules:
        - ``float`` → returned as-is.
        - ``int`` → converted via ``float()``.
        - ``str`` → parsed via ``float()``.
        - ``bool`` → rejected (same rationale as ``_coerce_int``).
        - Everything else → ``ConfigValidationError``.
    """
    if isinstance(raw_value, bool):
        raise ConfigValidationError(key, raw_value, "must be a valid float")

    if isinstance(raw_value, float):
        return raw_value

    if isinstance(raw_value, int):
        return float(raw_value)

    if isinstance(raw_value, str):
        stripped = raw_value.strip()
        if stripped == "":
            raise ConfigValidationError(key, raw_value, "must be a valid float")
        try:
            return float(stripped)
        except (ValueError, TypeError):
            raise ConfigValidationError(key, raw_value, "must be a valid float")

    raise ConfigValidationError(key, raw_value, "must be a valid float")


def _coerce_bool(key: str, raw_value: object) -> bool:
    """Coerce *raw_value* to a ``bool`` for config *key*.

    Rules:
        - ``bool`` → returned as-is.
        - ``int`` → ``0`` → False, non‑zero → True.
        - ``str`` → case‑insensitive match against known truthy/falsy
          strings, after stripping whitespace:
          True:  ``"true"``, ``"1"``, ``"yes"``, ``"on"``
          False: ``"false"``, ``"0"``, ``"no"``, ``"off"``
        - Everything else → ``ConfigValidationError``.
    """
    if isinstance(raw_value, bool):
        return raw_value

    if isinstance(raw_value, int):
        return raw_value != 0

    if isinstance(raw_value, str):
        stripped = raw_value.strip().lower()
        if stripped in _BOOL_TRUE_STRINGS:
            return True
        if stripped in _BOOL_FALSE_STRINGS:
            return False
        raise ConfigValidationError(
            key,
            raw_value,
            "must be a valid boolean (true/false, 1/0, yes/no, on/off)",
        )

    raise ConfigValidationError(
        key, raw_value, "must be a valid boolean (true/false, 1/0, yes/no, on/off)"
    )


def _coerce_enum(key: str, raw_value: object, allowed: list) -> str:
    """Coerce *raw_value* to one of the *allowed* enum values.

    Matching is **case‑sensitive** and exact.  The value is converted to a
    string first (via ``str()``), then compared against *allowed*.
    """
    value_str = str(raw_value) if not isinstance(raw_value, str) else raw_value
    if value_str in allowed:
        return value_str
    raise ConfigValidationError(
        key, raw_value, f"must be one of: {allowed}"
    )


def _coerce_value(key: str, raw_value: object, field_spec: dict) -> object:
    """Dispatch to the correct coercion function based on the schema type."""
    target_type = field_spec["type"]

    if target_type == "int":
        return _coerce_int(key, raw_value)
    elif target_type == "float":
        return _coerce_float(key, raw_value)
    elif target_type == "bool":
        return _coerce_bool(key, raw_value)
    elif target_type == "enum":
        return _coerce_enum(key, raw_value, field_spec["validation"]["allowed"])
    elif target_type == "string":
        return str(raw_value)
    else:
        raise ConfigValidationError(key, raw_value, f"unknown type: {target_type}")


# ===========================================================================
# 4. Validation — private helper
# ===========================================================================
def _validate_rules(key: str, coerced: object, field_spec: dict) -> None:
    """Apply post‑coercion validation rules (non_empty, min/max, allowed)."""
    validation = field_spec.get("validation", {})

    # non_empty — applies to string-typed keys
    if validation.get("non_empty") and isinstance(coerced, str) and coerced == "":
        raise ConfigValidationError(key, coerced, "must be a non-empty string")

    # min / max — applies to int / float
    if "min" in validation and isinstance(coerced, (int, float)):
        if coerced < validation["min"]:
            raise ConfigValidationError(
                key,
                coerced,
                f"must be in range [{validation['min']}, {validation['max']}]",
            )
    if "max" in validation and isinstance(coerced, (int, float)):
        if coerced > validation["max"]:
            raise ConfigValidationError(
                key,
                coerced,
                f"must be in range [{validation['min']}, {validation['max']}]",
            )


# ===========================================================================
# 5. Public API
# ===========================================================================
def get_schema() -> dict:
    """Return the full configuration schema.

    The returned dict is a **shallow copy** — callers may read freely but
    mutations will not affect the module‑level ``_SCHEMA``.
    """
    return dict(_SCHEMA)


def validate_value(key: str, value: object) -> object:
    """Validate and coerce a single config value against the schema.

    Args:
        key: Config key (must exist in the schema).
        value: Raw value from any source (string, int, bool, …).

    Returns:
        The coerced value (type as defined by the schema).

    Raises:
        ConfigValidationError: If the value cannot be coerced or fails
            validation rules.
    """
    schema = get_schema()
    if key not in schema:
        raise ConfigValidationError(key, value, f"unknown config key: '{key}'")

    field_spec = schema[key]

    # Step 1 — type coercion
    coerced = _coerce_value(key, value, field_spec)

    # Step 2 — validation rules
    _validate_rules(key, coerced, field_spec)

    return coerced


# ===========================================================================
# 6. Integration modules (executor3 — configuration integration specialist)
# ===========================================================================

# Env var prefix for this application domain
_ENV_PREFIX = "WEB_"


def parse_cli_args(args: dict[str, Any] | None) -> dict[str, Any]:
    """Normalise CLI argument keys into internal config key names.

    Conventions applied:
        - Strip leading ``--`` (e.g. ``--log-level`` → ``log-level``)
        - Replace hyphens with underscores (``log-level`` → ``log_level``)
        - Keys already in underscore form are left unchanged.

    Args:
        args: Raw CLI argument dict (key may be ``--foo-bar``, ``foo_bar``,
            or ``foo-bar``).  ``None`` is treated as an empty dict.

    Returns:
        Dict mapping internal config key → raw value (still a string).
        Empty dict when ``args`` is ``None``.
    """
    if args is None:
        return {}

    result: dict[str, Any] = {}
    for key, value in args.items():
        # 1. Strip leading dashes
        normalised = key.lstrip("-")
        # 2. Hyphens → underscores
        normalised = normalised.replace("-", "_")
        result[normalised] = value
    return result


def read_env_vars(
    env_vars: dict[str, str] | None = None,
    schema: dict | None = None,
) -> dict[str, Any]:
    """Read environment variables prefixed with ``WEB_`` and map them to
    internal config keys.

    Two mapping strategies, combined in order of preference:

    1. **Schema‑aware reverse lookup** (preferred): when *schema* is
       provided, the ``env_var`` field of each entry builds a
       ``{ENV_VAR_NAME → internal_key}`` reverse map.  This handles
       cases where heuristic ``strip‑prefix + lowercase`` produces an
       incorrect key — e.g. ``WEB_DEBUG`` → ``debug_mode`` (not
       ``debug``).

    2. **Heuristic fallback**: for env var names not found in the
       reverse map, the legacy ``strip‑prefix + lowercase`` rule is
       applied.  This keeps the function compatible with environment
       variables not yet registered in the schema.

    Args:
        env_vars: Environment dict to scan.  ``None`` → use ``os.environ``.
        schema: Optional config schema (as returned by ``get_schema()``).
            When provided, precise env‑var → config‑key mapping is derived
            from the schema's ``env_var`` fields.

    Returns:
        Dict mapping internal config key → raw env-var value (string).
        Empty dict when no matching variables are found.
    """
    source = env_vars if env_vars is not None else os.environ
    prefix_len = len(_ENV_PREFIX)

    # Build reverse map from schema (env var name → internal key)
    reverse_map: dict[str, str] = {}
    if schema is not None:
        for internal_key, spec in schema.items():
            env_name = spec.get("env_var")
            if env_name:
                reverse_map[env_name] = internal_key

    result: dict[str, Any] = {}
    for key, value in source.items():
        if not key.startswith(_ENV_PREFIX):
            continue

        # 1. Schema-aware reverse lookup (authoritative)
        if key in reverse_map:
            result[reverse_map[key]] = value
            continue

        # 2. Heuristic fallback: strip prefix + lowercase
        internal_key = key[prefix_len:].lower()
        result[internal_key] = value

    return result


def load_config_file(path: str | None) -> dict[str, Any]:
    """Load a JSON configuration file.

    Behaviour:
        - ``None`` → return ``{}`` (no file specified is not an error)
        - Missing file → raise ``FileNotFoundError`` (explicit path was
          given — caller expected the file to exist)
        - Invalid JSON → raise ``json.JSONDecodeError`` with the file path
          in the message for debuggability
        - Unknown / extra keys → returned as-is (caller is responsible for
          filtering against the schema)

    Args:
        path: Absolute or relative path to a JSON config file, or ``None``.

    Returns:
        Parsed JSON dict.  Empty dict when ``path`` is ``None``.

    Raises:
        FileNotFoundError: If ``path`` is provided but does not exist.
        json.JSONDecodeError: If the file contains invalid JSON.
    """
    if path is None:
        return {}

    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        raise
    except json.JSONDecodeError as exc:
        # Re-raise with path context for debuggability
        raise json.JSONDecodeError(
            f"Invalid JSON in config file '{path}': {exc.msg}",
            exc.doc,
            exc.pos,
        ) from exc

    if not isinstance(data, dict):
        # Defensive: if someone puts a list or scalar at the root, treat as empty
        return {}

    return data


# ===========================================================================
# 7. Main pipeline — load_config (core orchestration)
# ===========================================================================
def load_config(
    config_file: str | None = None,
    env_vars: dict | None = None,
    cli_args: dict | None = None,
) -> dict:
    """Load and validate configuration from all sources.

    Priority cascade (highest first):
        cli_args > env_vars > config_file > defaults

    Args:
        config_file: Path to a JSON config file, or ``None`` to skip.
        env_vars: Environment dict (``None`` → use ``os.environ``).
        cli_args: CLI argument dict (``None`` → skip CLI layer).

    Returns:
        ``dict`` with all 10 schema keys, each value coerced and validated.

    Raises:
        FileNotFoundError: *config_file* is given but does not exist.
        ConfigValidationError: Any value fails coercion or validation.
        json.JSONDecodeError: Config file contains invalid JSON.
    """
    schema = get_schema()
    known_keys = set(schema.keys())

    # ---- Layer 4: built-in defaults (lowest priority) ----
    result: dict[str, Any] = {key: spec["default"] for key, spec in schema.items()}

    # ---- Layer 3: JSON config file ----
    file_raw = load_config_file(config_file)
    for k, v in file_raw.items():
        if k in known_keys:
            result[k] = v

    # ---- Layer 2: environment variables ----
    env_raw = read_env_vars(env_vars, schema=schema)
    for k, v in env_raw.items():
        if k in known_keys:
            result[k] = v

    # ---- Layer 1: CLI arguments (highest priority) ----
    cli_raw = parse_cli_args(cli_args)
    for k, v in cli_raw.items():
        if k in known_keys:
            result[k] = v

    # ---- Validate & coerce every key ----
    for key in list(result.keys()):
        result[key] = validate_value(key, result[key])

    return result
