"""
Audit logging module — implements compliant audit trail for FinanceApp.

Required exports:
    log_event(event_type, **fields) -> dict
        Create, store, and return a compliant audit log entry.
        The entry must include ALL required fields for the event type,
        plus the tamper-detection field ('signature').

    get_log() -> list[dict]
        Return all stored audit log entries.

    verify_log(entries) -> list[int]
        Return indices of entries that fail tamper-detection verification.
        Return an empty list if all entries are valid.

Tamper detection method: HMAC-SHA256 Entry Signature
Required tamper-detection field: 'signature'

Read corpus/audit_policy.txt for full field requirements per event type.
"""

import datetime
import hashlib
import hmac
import json
import os
import uuid

# ---------------------------------------------------------------------------
# 全局状态
# ---------------------------------------------------------------------------

_AUDIT_LOG: list[dict] = []       # 内存中的审计日志存储（有序）
_CURRENT_DATE: str | None = None  # 当前活跃文件的日期 (YYYY-MM-DD)


# ---------------------------------------------------------------------------
# 事件类型注册表 — 每类事件的所有必填字段
# ---------------------------------------------------------------------------

EVENT_SCHEMAS: dict[str, list[str]] = {
    "config_changed": [
        "event_type", "log_id", "user_id", "timestamp",
        "config_key", "old_value", "new_value", "user_agent",
    ],
    "user_login": [
        "event_type", "log_id", "user_id", "timestamp",
        "ip_address", "success", "correlation_id",
    ],
    "report_accessed": [
        "event_type", "log_id", "user_id", "timestamp",
        "report_id", "report_type", "request_id",
    ],
    "data_exported": [
        "event_type", "log_id", "user_id", "timestamp",
        "export_format", "record_count", "destination", "user_agent",
    ],
    "payment_initiated": [
        "event_type", "log_id", "user_id", "timestamp",
        "amount", "currency", "recipient_account", "session_id",
    ],
}


# ===================================================================
# 内部辅助函数
# ===================================================================

def _get_hmac_key() -> bytes:
    """获取 HMAC 密钥，优先从环境变量 AUDIT_HMAC_KEY 读取。"""
    key_str = os.environ.get("AUDIT_HMAC_KEY", "default-key")
    return key_str.encode("utf-8")


def _generate_log_id() -> str:
    """生成全局唯一的 log_id（UUID4）。"""
    return str(uuid.uuid4())


def _get_timestamp() -> str:
    """生成 UTC ISO 8601 时间戳，带 +00:00 后缀。"""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _canonical_json(entry: dict) -> str:
    """
    生成 canonical JSON 字符串。

    规则：
    - 字段按 key 字母序排序
    - 紧凑输出（无空格 / 换行）
    - 保留 Unicode 原始字符
    """
    return json.dumps(
        entry,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _compute_signature(entry: dict) -> str:
    """
    对不包含 signature 字段的 entry 计算 HMAC-SHA256 签名。

    返回十六进制摘要字符串 (64 个 hex 字符)。
    """
    canonical = _canonical_json(entry)
    key = _get_hmac_key()
    sig = hmac.new(key, canonical.encode("utf-8"), hashlib.sha256)
    return sig.hexdigest()


def _verify_entry_signature(entry: dict) -> bool:
    """
    验证单条 entry 的 HMAC-SHA256 签名。

    使用 hmac.compare_digest 做常量时间比较，防止时序侧信道攻击。
    """
    if "signature" not in entry:
        return False

    sig_value = entry.get("signature")
    if sig_value is None or sig_value == "":
        return False

    entry_without_sig = {k: v for k, v in entry.items() if k != "signature"}
    expected_sig = _compute_signature(entry_without_sig)

    return hmac.compare_digest(expected_sig, sig_value)


def _rotate_if_needed() -> None:
    """
    每日轮转检查。

    若日期变更：
    1. 将 audit_today.jsonl 重命名为 audit_YYYY-MM-DD.jsonl
    2. 更新 _CURRENT_DATE
    3. 触发过期日志清理
    """
    global _CURRENT_DATE

    today = datetime.date.today().isoformat()

    if _CURRENT_DATE is None:
        _CURRENT_DATE = today
        return

    if _CURRENT_DATE == today:
        return

    old_file = "audit_today.jsonl"
    archive_file = f"audit_{_CURRENT_DATE}.jsonl"

    if os.path.exists(old_file):
        os.rename(old_file, archive_file)

    _CURRENT_DATE = today
    _cleanup_expired_logs()


def _cleanup_expired_logs() -> None:
    """删除超过 2555 天（7 年）的归档日志文件。"""
    cutoff = datetime.date.today() - datetime.timedelta(days=2555)

    try:
        for fname in os.listdir("."):
            if not fname.startswith("audit_") or not fname.endswith(".jsonl"):
                continue
            if fname == "audit_today.jsonl":
                continue

            try:
                date_str = fname[6:16]
                file_date = datetime.date.fromisoformat(date_str)
                if file_date < cutoff:
                    os.remove(fname)
            except (ValueError, IndexError):
                pass
    except OSError:
        pass


def _append_to_file(entry: dict) -> None:
    """将一条完整的 entry（含 signature）以 JSONL 格式追加写入当前日志文件。"""
    try:
        with open("audit_today.jsonl", "a", encoding="utf-8") as f:
            f.write(_canonical_json(entry) + "\n")
    except OSError:
        pass


# ===================================================================
# 公开 API
# ===================================================================

def log_event(event_type: str, **fields) -> dict:
    """
    记录一条审计事件。

    返回包含 log_id、timestamp、signature 等所有字段的完整 entry。

    Raises ValueError: 未知 event_type 或缺少必填字段。
    """
    if event_type not in EVENT_SCHEMAS:
        raise ValueError(f"Unknown event_type: {event_type}")

    entry: dict = {
        "event_type": event_type,
        "log_id": _generate_log_id(),
        "timestamp": _get_timestamp(),
    }
    entry.update(fields)

    expected_fields = EVENT_SCHEMAS[event_type]
    missing = [f for f in expected_fields if f not in entry]
    if missing:
        raise ValueError(f"Missing required fields: {missing}")

    signature = _compute_signature(entry)
    entry["signature"] = signature

    _AUDIT_LOG.append(entry)

    _rotate_if_needed()
    _append_to_file(entry)

    return entry


def get_log() -> list[dict]:
    """返回内存中所有审计日志条目（按记录顺序）。"""
    return list(_AUDIT_LOG)


def verify_log(entries: list[dict]) -> list[int]:
    """
    验证日志完整性，检测被篡改或缺失签名的条目。

    返回签名验证失败的条目索引列表（0-based）。空列表表示全部通过。
    """
    tampered_indices: list[int] = []

    for i, entry in enumerate(entries):
        if not _verify_entry_signature(entry):
            tampered_indices.append(i)

    return tampered_indices
