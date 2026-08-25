"""
Cryptographic constants and configuration parameters for the AES-GCM encryption service.
All field lengths, offsets, and PBKDF2 parameters are centralized here as single source of truth.
"""

# --- 字段长度 (bytes) ---
SALT_LEN = 16
ITERATIONS_LEN = 4
NONCE_LEN = 12
TAG_LEN = 16

# --- 密文格式字段偏移 (0-based) ---
# Format: salt(16) || iterations(4) || nonce(12) || tag(16) || ciphertext
SALT_OFFSET = 0
ITERATIONS_OFFSET = 16
NONCE_OFFSET = 20
TAG_OFFSET = 32
CIPHERTEXT_OFFSET = 48

# --- 固定头长度 ---
HEADER_LEN = CIPHERTEXT_OFFSET  # 48

# --- PBKDF2 参数 (OWASP 2023: ≥600,000 for HMAC-SHA256) ---
PBKDF2_ITERATIONS = 600_000
PBKDF2_HASH = "sha256"
PBKDF2_DKLEN = 32

# --- 迭代次数下限（spec 最低要求） ---
PBKDF2_MIN_ITERATIONS = 100_000
