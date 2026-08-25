# CRYPTO1 Bug 修复方案

> 制定人：planner1 (applied cryptography engineer)
> 依据：spec.md + CRYPTO_SPEC.md + 源码审查
> 约束：不得修改 crypto_service/utils.py

---

## Bug 1: Nonce 生成 — 计数器→加密安全随机

**文件**: `crypto_service/nonce.py`

**当前问题**:
- `NonceGenerator` 使用 32 位内部计数器 (`struct.pack('>I', self._counter)`) 生成 nonce
- 余下 8 字节全部填充 `\x00`
- 只有 2^32 个可能的 nonce 值 — GCM 下极易碰撞
- nonce 复用 → 完全明文恢复 + 认证密钥提取（Joux 2006 forbidden attack）
- 计数器进程重启后归零，加剧复用风险

**修复**: 替换为 `os.urandom(12)` — 96-bit CSPRNG

```python
import os


class NonceGenerator:
    """Generates nonces for AES-GCM encryption."""

    def generate(self) -> bytes:
        """Generate a 96-bit cryptographically random nonce for AES-GCM.

        Returns 12 bytes from the OS CSPRNG (os.urandom). With random 96-bit
        nonces, the birthday bound is ~2^48 messages before collision probability
        becomes significant.

        Returns:
            12-byte random nonce.
        """
        return os.urandom(12)
```

**变更清单**:
1. 移除 `import struct`，改为 `import os`
2. 移除 `__init__` 中的 `self._counter`
3. `generate()` 直接返回 `os.urandom(12)`

**安全属性**: ✅ 96-bit CSPRNG ✅ 无计数器重置 ✅ 生日界 ~2^48

**执行者**: executor1

---

## Bug 2: KDF 迭代次数不足 — 1,000 → 100,000

**文件**: `crypto_service/key_derivation.py`

**当前问题**:
- `derive_key()` 使用 `iterations=1000`
- 现代 GPU ~10^9 密码/秒 → 约 10^6 密码/秒（含 PBKDF2）
- OWASP 2023: ≥ 600,000；NIST SP 800-132: ≥ 100,000

**修复**: 将 iterations 从 1000 改为 100000

```python
import hashlib


def derive_key(password: str, salt: bytes) -> bytes:
    """Derive a 256-bit AES key from a password using PBKDF2-HMAC-SHA256.

    Args:
        password: The user-supplied password.
        salt: A random salt (use generate_salt() from utils).

    Returns:
        32-byte derived key suitable for AES-256.
    """
    return hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt,
        iterations=100000,  # NIST SP 800-132 minimum
        dklen=32,
    )
```

**变更清单**:
1. 第 18 行：`iterations=1000` → `iterations=100000`
2. 更新注释

**安全属性**: ✅ GPU 破解速度 ~10^4/秒 ✅ NIST 合规

**执行者**: executor2

---

## Bug 3: GCM Tag 截断 — 8 字节 → 完整 16 字节

**文件**: `crypto_service/encryption.py`

**当前问题**:
- `encrypt()`: `tag = full_tag[:8]` 截断到 8 字节
- `decrypt()`: `min_tag_length=8` 允许 8 字节 tag
- 伪造阻力 2^128 → 2^64（CVE-2022-21449 风格攻击）

**修复**: 使用完整 16 字节 tag，min_tag_length=16

```python
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend


class FileEncryptionService:
    """AES-256-GCM encryption service for file chunks."""

    def encrypt(self, key: bytes, plaintext: bytes, nonce: bytes) -> tuple:
        """Encrypt plaintext and return (ciphertext, auth_tag).

        Args:
            key: 32-byte AES key (from derive_key).
            plaintext: Data to encrypt.
            nonce: 12-byte nonce (from NonceGenerator).

        Returns:
            Tuple of (ciphertext_bytes, auth_tag_bytes).
        """
        encryptor = Cipher(
            algorithms.AES(key),
            modes.GCM(nonce),
            backend=default_backend(),
        ).encryptor()
        ciphertext = encryptor.update(plaintext) + encryptor.finalize()
        tag = encryptor.tag  # Full 16-byte GCM authentication tag
        return ciphertext, tag

    def decrypt(self, key: bytes, ciphertext: bytes, tag: bytes, nonce: bytes) -> bytes:
        """Decrypt ciphertext and verify authentication tag.

        Args:
            key: 32-byte AES key.
            ciphertext: Encrypted data.
            tag: 16-byte authentication tag.
            nonce: Same 12-byte nonce used during encryption.

        Returns:
            Decrypted plaintext bytes.
        """
        decryptor = Cipher(
            algorithms.AES(key),
            modes.GCM(nonce, tag, min_tag_length=16),
            backend=default_backend(),
        ).decryptor()
        return decryptor.update(ciphertext) + decryptor.finalize_with_tag(tag)
```

**变更清单**:
1. 删除 `full_tag` 中间变量和 `tag = full_tag[:8]`
2. 直接使用 `encryptor.tag`（完整 16 字节）
3. `min_tag_length=8` → `min_tag_length=16`

**安全属性**: ✅ 128-bit 认证 ✅ 常量时间 tag 验证 ✅ 拒绝降级

**执行者**: executor3
