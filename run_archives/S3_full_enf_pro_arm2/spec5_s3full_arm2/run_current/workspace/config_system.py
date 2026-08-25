"""Web Service Configuration System — spec-driven config loader."""
import json
import os


# ── Bool 合法字符串映射（大小写不敏感）───────────────────────────────
_BOOL_TRUE = frozenset({"true", "1", "yes", "on"})
_BOOL_FALSE = frozenset({"false", "0", "no", "off"})


# ── ConfigValidationError ──────────────────────────────────────────
class ConfigValidationError(ValueError):
    """Raised when a config value fails validation or coercion."""
    pass


# ── _SCHEMA（完整 10 键）────────────────────────────────────────────
_SCHEMA = {
    "host": {
        "type": "string",
        "default": "0.0.0.0",
        "env_var": "WEB_HOST",
        "validation": "non_empty",
    },
    "port": {
        "type": "int",
        "default": 6155,
        "env_var": "WEB_PORT",
        "validation": "range",
        "range": [2048, 49151],
    },
    "log_level": {
        "type": "enum",
        "default": "WARN",
        "env_var": "WEB_LOG_LEVEL",
        "allowed": ["INFO", "WARN", "ERROR"],
    },
    "request_timeout": {
        "type": "int",
        "default": 120,
        "env_var": "WEB_REQUEST_TIMEOUT",
        "validation": "range",
        "range": [1, 3600],
    },
    "max_connections": {
        "type": "int",
        "default": 348,
        "env_var": "WEB_MAX_CONNECTIONS",
        "validation": "range",
        "range": [1, 1000],
    },
    "debug_mode": {
        "type": "bool",
        "default": False,
        "env_var": "WEB_DEBUG",
    },
    "static_dir": {
        "type": "string",
        "default": "./static",
        "env_var": "WEB_STATIC_DIR",
        "validation": "non_empty",
    },
    "cors_origins": {
        "type": "string",
        "default": "*",
        "env_var": "WEB_CORS_ORIGINS",
    },
    "keep_alive_timeout": {
        "type": "int",
        "default": 10,
        "env_var": "WEB_KEEP_ALIVE_TIMEOUT",
        "validation": "range",
        "range": [1, 300],
    },
    "ssl_enabled": {
        "type": "bool",
        "default": False,
        "env_var": "WEB_SSL_ENABLED",
    },
}


# ── get_schema ─────────────────────────────────────────────────────
def get_schema() -> dict:
    """Return the config schema as a dict (key -> spec dict)."""
    return dict(_SCHEMA)  # 返回浅拷贝，防止外部修改


# ── _coerce_value ──────────────────────────────────────────────────
def _coerce_value(key: str, raw_value, spec: dict):
    """将 raw_value 转换为 spec['type'] 指定的目标类型。

    Args:
        key: 配置键名（用于错误消息）
        raw_value: 原始值（可能来自任何源）
        spec: 该键的 schema 定义

    Returns:
        转换后的值

    Raises:
        ConfigValidationError: 转换失败
    """
    typ = spec["type"]

    # ---- string: 直接转字符串 ----
    if typ == "string":
        return str(raw_value)

    # ---- int: 解析为整数 ----
    if typ == "int":
        # 如果已经是 int 类型，直接返回（来自 JSON 的数值或 Python 默认值）
        if isinstance(raw_value, int) and not isinstance(raw_value, bool):
            return raw_value
        # 如果是 float，拒绝（防止静默精度丢失）
        if isinstance(raw_value, float):
            raise ConfigValidationError(
                f"Invalid value for '{key}': {raw_value!r} — "
                f"expected int, got float"
            )
        # 字符串解析
        try:
            return int(raw_value)
        except (ValueError, TypeError):
            raise ConfigValidationError(
                f"Invalid value for '{key}': {raw_value!r} — "
                f"cannot convert to int"
            )

    # ---- float ----
    if typ == "float":
        if isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool):
            return float(raw_value)
        try:
            return float(raw_value)
        except (ValueError, TypeError):
            raise ConfigValidationError(
                f"Invalid value for '{key}': {raw_value!r} — "
                f"cannot convert to float"
            )

    # ---- bool: 支持 true/false, 1/0, yes/no, on/off (大小写不敏感) ----
    if typ == "bool":
        # 已经是 bool 类型
        if isinstance(raw_value, bool):
            return raw_value
        # 整数 0/1
        if isinstance(raw_value, int) and not isinstance(raw_value, bool):
            if raw_value == 1:
                return True
            if raw_value == 0:
                return False
            raise ConfigValidationError(
                f"Invalid value for '{key}': {raw_value!r} — "
                f"bool only accepts 0 or 1 as integers"
            )
        # 字符串
        if isinstance(raw_value, str):
            lowered = raw_value.strip().lower()
            if lowered in _BOOL_TRUE:
                return True
            if lowered in _BOOL_FALSE:
                return False
            raise ConfigValidationError(
                f"Invalid value for '{key}': {raw_value!r} — "
                f"accepted bool values: true/false, 1/0, yes/no, on/off"
            )
        # 其他类型拒绝
        raise ConfigValidationError(
            f"Invalid value for '{key}': {raw_value!r} — "
            f"cannot coerce type {type(raw_value).__name__} to bool"
        )

    # ---- enum: 先转字符串，再检查 allowed 集合 ----
    if typ == "enum":
        coerced_str = str(raw_value)
        allowed = spec["allowed"]
        if coerced_str not in allowed:
            raise ConfigValidationError(
                f"Invalid value for '{key}': {raw_value!r} — "
                f"must be one of {allowed}"
            )
        return coerced_str

    # 未知类型
    raise ConfigValidationError(f"Unknown schema type '{typ}' for key '{key}'")


# ── validate_value ─────────────────────────────────────────────────
def validate_value(key: str, value) -> object:
    """Validate and coerce a single value against the schema for `key`.

    Returns the coerced, validated value.
    Raises ConfigValidationError if invalid.
    """
    schema = get_schema()

    if key not in schema:
        raise ConfigValidationError(
            f"Unknown config key: '{key}'"
        )

    spec = schema[key]
    # 第一步：类型转换
    coerced = _coerce_value(key, value, spec)

    # 第二步：额外校验规则
    validation = spec.get("validation")

    if validation == "non_empty":
        if not isinstance(coerced, str) or coerced.strip() == "":
            raise ConfigValidationError(
                f"Invalid value for '{key}': {coerced!r} — "
                f"must be a non-empty string"
            )

    elif validation == "range":
        lo, hi = spec["range"]
        if not (lo <= coerced <= hi):
            raise ConfigValidationError(
                f"Invalid value for '{key}': {coerced!r} — "
                f"must be in range [{lo}, {hi}]"
            )

    return coerced


# ── load_config ────────────────────────────────────────────────────
def load_config(
    config_file: str | None = None,
    env_vars: dict | None = None,
    cli_args: dict | None = None,
) -> dict:
    """Load and validate configuration from all sources in priority order.

    Priority (highest first):
        1. cli_args
        2. env_vars (defaults to os.environ if None)
        3. config_file (JSON)
        4. schema defaults

    Args:
        config_file: Path to a JSON config file (optional).
        env_vars: Dict of environment variables (defaults to os.environ).
        cli_args: Dict of CLI arguments — highest priority.

    Returns:
        A dict with all 10 config keys populated, validated, and type-coerced.

    Raises:
        ConfigValidationError: If any value fails validation or coercion.
        FileNotFoundError: If config_file is specified but does not exist.
    """
    schema = get_schema()

    # ── 第 4 层：Schema 默认值（最低优先级）──
    raw: dict[str, object] = {}
    for key, spec in schema.items():
        raw[key] = spec["default"]

    # ── 第 3 层：JSON 配置文件 ──
    if config_file is not None:
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                file_data = json.load(f)
        except FileNotFoundError:
            raise  # 原样上抛，不做包装
        except json.JSONDecodeError as e:
            raise ConfigValidationError(
                f"Failed to parse config file '{config_file}': {e}"
            ) from e

        if not isinstance(file_data, dict):
            raise ConfigValidationError(
                f"Config file '{config_file}' must contain a JSON object, "
                f"got {type(file_data).__name__}"
            )

        for key, value in file_data.items():
            if key in schema:
                raw[key] = value
            # 未知键静默忽略

    # ── 第 2 层：环境变量 ──
    if env_vars is None:
        env_vars = dict(os.environ)

    # 构建 env_var → config_key 映射
    env_to_key: dict[str, str] = {}
    for key, spec in schema.items():
        ev = spec.get("env_var")
        if ev:
            env_to_key[ev] = key

    for env_name, config_key in env_to_key.items():
        if env_name in env_vars:
            raw[config_key] = env_vars[env_name]

    # ── 第 1 层：CLI 参数（最高优先级）──
    if cli_args:
        for key, value in cli_args.items():
            if key in schema:
                raw[key] = value

    # ── 最终：对所有键进行类型转换 + 校验 ──
    result: dict[str, object] = {}
    for key in schema:
        result[key] = validate_value(key, raw[key])

    return result
