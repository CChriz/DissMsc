# KVP 协议测试矩阵

> 由 executor2 编制，供 executor1 编写测试用例时参考。
> 覆盖 protocol_spec.txt 中全部 15 条命令，按 MUST/SHOULD/MAY 标注需求级别。

---

## 0. 通用限制常量

| 常量 | 值 | 用途 |
|------|-----|------|
| MAX_KEY_LENGTH | 64 | 键最大长度 |
| MAX_VALUE_SIZE | 1024 | 值最大长度 |
| MAX_KEYS | 100 | 最大键数量 |

---

## 1. SET 命令

### 需求级别：MUST (M1)

| 场景 ID | 等价类 | 输入 | 预期输出 | 备注 |
|---------|--------|------|----------|------|
| SET-01 | 正常设置 | `SET mykey myvalue` | `OK` | 基础功能 |
| SET-02 | 覆盖已有键 | 先 SET k v1，再 SET k v2 | `OK`，后续 GET 返回 v2 | 更新不触发 store_full |
| SET-03 | 键长度=64（边界） | SET 64字符键 val | `OK` | 边界内有效 |
| SET-04 | 键长度=65（超限） | SET 65字符键 val | `ERR key_too_long` | M10 |
| SET-05 | 键长度=0（空键） | `SET "" val` | 取决于实现（空字符串或参数缺失） | 边界 |
| SET-06 | 值长度=1024（边界） | SET k 1024字符值 | `OK` | 边界内有效 |
| SET-07 | 值长度=1025（超限） | SET k 1025字符值 | `ERR value_too_large` | M11 |
| SET-08 | 值长度=0（空值） | `SET k ""` 或 `SET k`（无值参数） | `OK`（空字符串为有效值） | 边界 |
| SET-09 | store 满时新增 | 填充100个键后 `SET newkey val` | `ERR store_full` | M12 |
| SET-10 | store 满时更新 | 填充100个键后 `SET key0 newval` | `OK` | M12 — 更新已存在键不触发限制 |
| SET-11 | 值含空格 | `SET k hello world` | `OK`，GET 返回 `hello world` | 解析器需正确处理多词值 |

### 现有测试覆盖：`test_set_returns_ok` (SET-01)

---

## 2. GET 命令

### 需求级别：MUST (M2)

| 场景 ID | 等价类 | 输入 | 预期输出 | 备注 |
|---------|--------|------|----------|------|
| GET-01 | 获取已存在键 | 先 SET，后 GET | 返回存储的值 | 基础功能 |
| GET-02 | 获取不存在键 | `GET noexist` | `ERR key_not_found` | 基础错误 |
| GET-03 | 获取已删除键 | SET → DEL → GET | `ERR key_not_found` | 生命周期 |
| GET-04 | 获取过期键 | SETEX k 1 val → sleep(1.5) → GET k | `ERR key_not_found` | S1: 过期处理 |
| GET-05 | 获取空值键 | SET k "" → GET k | 返回空行或 `""` | 边界 |

### 现有测试覆盖：`test_get_existing_key` (GET-01), `test_get_missing_key` (GET-02)

---

## 3. DEL 命令

### 需求级别：MUST (M3)

| 场景 ID | 等价类 | 输入 | 预期输出 | 备注 |
|---------|--------|------|----------|------|
| DEL-01 | 删除已存在键 | SET → DEL | `OK`，后续 GET 返回 key_not_found | 基础功能 |
| DEL-02 | 删除不存在键 | `DEL noexist` | `ERR key_not_found` | 错误处理 |
| DEL-03 | 重复删除 | SET → DEL → DEL（同一键） | 第二次 `ERR key_not_found` | 幂等性 |
| DEL-04 | 删除后 COUNT 减一 | SET k1,k2 → DEL k1 → COUNT | `COUNT 1` | 计数一致性 |

### 现有测试覆盖：`test_del_existing_key` (DEL-01)

---

## 4. KEYS 命令

### 需求级别：MUST (M4)

| 场景 ID | 等价类 | 输入 | 预期输出 | 备注 |
|---------|--------|------|----------|------|
| KEYS-01 | 多个键 | SET k1,k2,k3 → KEYS | 三行键名 + `END` | 基础功能 |
| KEYS-02 | 空 store | KEYS（未 SET 任何键） | `END`（仅终止符） | 边界 |
| KEYS-03 | FLUSH 后 | SET → FLUSH → KEYS | `END`（仅终止符） | 清空后 |
| KEYS-04 | 100 个键 | 填充100键 → KEYS | 100行 + `END` | 最大容量边界 |

### 现有测试覆盖：`test_keys_lists_all` (KEYS-01)

---

## 5. COUNT 命令

### 需求级别：MUST (M5)

| 场景 ID | 等价类 | 输入 | 预期输出 | 备注 |
|---------|--------|------|----------|------|
| COUNT-01 | 有键时 | SET k1,k2 → COUNT | `COUNT 2` | 基础功能 |
| COUNT-02 | 空 store | COUNT（初始状态） | `COUNT 0` | 边界 |
| COUNT-03 | FLUSH 后 | SET k1,k2 → FLUSH → COUNT | `COUNT 0` | 清空后 |
| COUNT-04 | 满 store | 填充100键 → COUNT | `COUNT 100` | 最大边界 |
| COUNT-05 | DEL 后递减 | SET k1,k2 → DEL k1 → COUNT | `COUNT 1` | 计数递减 |

### 现有测试覆盖：`test_count_after_sets` (COUNT-01)

---

## 6. EXISTS 命令

### 需求级别：MUST (M6)

| 场景 ID | 等价类 | 输入 | 预期输出 | 备注 |
|---------|--------|------|----------|------|
| EXISTS-01 | 键存在 | SET k v → EXISTS k | `TRUE` | 基础功能 |
| EXISTS-02 | 键不存在 | EXISTS noexist | `FALSE` | 基础功能 |
| EXISTS-03 | 键已删除 | SET → DEL → EXISTS | `FALSE` | 生命周期 |
| EXISTS-04 | 过期键 | SETEX k 1 val → sleep(1.5) → EXISTS k | `FALSE` | S1: 过期处理 |
| EXISTS-05 | 超长键 | EXISTS + 65字符键 | `FALSE`（键不存在即 FALSE，不报 key_too_long） | 边界 |

### 现有测试覆盖：`test_exists_true` (EXISTS-01), `test_exists_false` (EXISTS-02)

---

## 7. FLUSH 命令

### 需求级别：MUST (M7)

| 场景 ID | 等价类 | 输入 | 预期输出 | 备注 |
|---------|--------|------|----------|------|
| FLUSH-01 | 清空有数据 store | SET k1,k2 → FLUSH | `OK`，后续 COUNT=0 | 基础功能 |
| FLUSH-02 | 清空空 store | FLUSH（初始状态） | `OK` | 空操作也返回 OK |
| FLUSH-03 | 重复 FLUSH | FLUSH → FLUSH | 两次都 `OK` | 幂等性 |
| FLUSH-04 | FLUSH 后 KEYS | SET k1,k2 → FLUSH → KEYS | `END` | 一致性 |

### 现有测试覆盖：`test_flush_clears_store` (FLUSH-01)

---

## 8. MSET 命令

### 需求级别：SHOULD (S2) — 高优先级覆盖

| 场景 ID | 等价类 | 输入 | 预期输出 | 备注 |
|---------|--------|------|----------|------|
| MSET-01 | 正常多对设置 | `MSET k1 v1 k2 v2 k3 v3` | `OK 3` | 基础功能 |
| MSET-02 | 单对设置 | `MSET k1 v1` | `OK 1` | 退化为单 SET |
| MSET-03 | 部分键已存在 | SET k1 old → `MSET k1 new k2 v2` | `OK 2` | 更新 + 新增 |
| MSET-04 | 奇数参数 | `MSET k1 v1 k2` | `ERR unknown_command` 或特定错误 | 边界：参数不完整 |
| MSET-05 | 某键超长 | `MSET k1 v1 kkk...(65chars) v2` | `ERR key_too_long` | **原子性关键测试**：整体回滚 |
| MSET-06 | 某值超大 | `MSET k1 v1 k2 vvv...(1025chars)` | `ERR value_too_large` | **原子性关键测试** |
| MSET-07 | 触发 store_full | 已有99键 → `MSET k1 v1 k2 v2` | `ERR store_full` | 原子性：整体不写入 |
| MSET-08 | store_full 但全部更新 | 已有100键 → `MSET key0 v0 key1 v1`（均存在） | `OK 2` | 全部已存在键的更新 |
| MSET-09 | 空参数 | `MSET` | `ERR unknown_command` | 边界 |

---

## 9. MGET 命令

### 需求级别：SHOULD (S3) — 高优先级覆盖

| 场景 ID | 等价类 | 输入 | 预期输出 | 备注 |
|---------|--------|------|----------|------|
| MGET-01 | 全部存在 | SET k1,k2,k3 → `MGET k1 k2 k3` | v1 / v2 / v3 / `END` | 基础功能 |
| MGET-02 | 部分存在 | SET k1 → `MGET k1 k2` | v1 / NIL / `END` | 不存在返回 NIL |
| MGET-03 | 全部不存在 | `MGET no1 no2` | NIL / NIL / `END` | 边界 |
| MGET-04 | 单键 | SET k1 v1 → `MGET k1` | v1 / `END` | 退化为单 GET |
| MGET-05 | 空参数 | `MGET` | `END` 或错误 | 边界 |
| MGET-06 | 含过期键 | SETEX k1 1 val → sleep(1.5) → `MGET k1` | NIL / `END` | S1: 过期处理 |

---

## 10. SETEX 命令

### 需求级别：SHOULD (S1) — 最高优先级覆盖

| 场景 ID | 等价类 | 输入 | 预期输出 | 备注 |
|---------|--------|------|----------|------|
| SETEX-01 | 正常设置 | `SETEX k 10 val` | `OK` | 基础功能 |
| SETEX-02 | TTL 查询 | SETEX k 10 val → TTL k | 返回 ≤10 的正整数 | 验证 TTL 设值 |
| SETEX-03 | 未过期 GET | SETEX k 5 val → 立即 GET | 返回 val | 过期前可访问 |
| SETEX-04 | 已过期 GET | SETEX k 1 val → sleep(1.5) → GET k | `ERR key_not_found` | **过期闭环关键测试** |
| SETEX-05 | 已过期 EXISTS | SETEX k 1 val → sleep(1.5) → EXISTS k | `FALSE` | 过期后不存在 |
| SETEX-06 | 覆盖已有键 | SET k old → SETEX k 10 newval → GET k | `newval`，TTL 被设置 | 覆盖行为 |
| SETEX-07 | seconds=0 | `SETEX k 0 val` | `ERR unknown_command` | ⚠️ 实现确认：≤0 拒绝 |
| SETEX-07b | seconds 负数 | `SETEX k -1 val` | `ERR unknown_command` | ⚠️ 实现确认：≤0 拒绝 |
| SETEX-08 | seconds 非数字 | `SETEX k abc val` | `ERR unknown_command` | int() 转换失败 |
| SETEX-09 | 键超长 | `SETEX kkk...(65chars) 10 val` | `ERR key_too_long` | M10 |
| SETEX-10 | 值超大 | `SETEX k 10 vvv...(1025chars)` | `ERR value_too_large` | M11 |
| SETEX-11 | store_full | 填充100键 → SETEX newkey 10 val | `ERR store_full` | M12 |
| SETEX-12 | SETEX 覆盖普通 SET | SET k v → SETEX k 10 newval → TTL k | 正数 (~10)（覆盖后获得过期时间） | ⚠️ 实现确认 |
| SETEX-13 | 普通 SET 覆盖 SETEX | SETEX k 10 v → SET k newval → TTL k | `-1`（覆盖后清除过期） | ⚠️ 实现确认 |

---

## 11. TTL 命令

### 需求级别：SHOULD (S4) — 中优先级覆盖

| 场景 ID | 等价类 | 输入 | 预期输出 | 备注 |
|---------|--------|------|----------|------|
| TTL-01 | 有过期时间的键 | SETEX k 30 val → TTL k | 非负整数字符串（`int(r) >= 0`） | ⚠️ 用较大 seconds（如 10）避免秒边界竞态 |
| TTL-02 | 无过期时间的键 | SET k v → TTL k | `-1` | 永久键 |
| TTL-03 | 不存在的键 | `TTL noexist` | `ERR key_not_found` | 错误处理 |
| TTL-04 | 已过期键 | SETEX k 1 val → sleep(1.5) → TTL k | `ERR key_not_found` | 过期后不存在 |
| TTL-05 | FLUSH 后 | SETEX k 10 val → FLUSH → TTL k | `ERR key_not_found` | 清空后 |
| TTL-06 | DEL 后 | SETEX k 10 val → DEL k → TTL k | `ERR key_not_found` | 删除后 |

---

## 12. APPEND 命令

### 需求级别：SHOULD (S5) — 中优先级覆盖

| 场景 ID | 等价类 | 输入 | 预期输出 | 备注 |
|---------|--------|------|----------|------|
| APPEND-01 | 追加到已存在键 | SET k hello → APPEND k _world | `OK 11` | 基础功能 |
| APPEND-02 | 创建新键 | APPEND newkey hello | `OK 5` | 不存在键视为空字符串追加 |
| APPEND-03 | 追加空值 | SET k hello → APPEND k "" | `OK 5` | 空字符串追加，长度不变 |
| APPEND-04 | 追加后超限 | SET k v(1020字符) → APPEND k xxxxxxxxxx(10字符) | `ERR value_too_large` | M11：结果不能超 1024 |
| APPEND-05 | 键超长 | APPEND kkk...(65chars) val | `ERR key_too_long` | M10 |
| APPEND-06 | store_full 新增 | 已有100键 → APPEND newkey val | `ERR store_full` | M12（新建键才检查） |
| APPEND-07 | store_full 更新 | 已有100键 → APPEND key0 val | `OK <new_len>` | 更新不触发 store_full |

### 现有测试覆盖：`test_append_to_existing` (APPEND-01)

---

## 13. RENAME 命令

### 需求级别：MAY (A3) — 低优先级（可选覆盖）

| 场景 ID | 等价类 | 输入 | 预期输出 | 备注 |
|---------|--------|------|----------|------|
| RENAME-01 | 正常重命名 | SET k v → RENAME k newk | `OK`，GET k→key_not_found，GET newk→v | 基础功能 |
| RENAME-02 | 旧键不存在 | `RENAME noexist newk` | `ERR key_not_found` | 错误处理 |
| RENAME-03 | 新键已存在（覆盖） | SET k1 v1 → SET k2 v2 → RENAME k1 k2 | `OK`，GET k2→v1 | 覆盖行为 |
| RENAME-04 | 新键超长 | SET k v → RENAME k kkk...(65chars) | `ERR key_too_long` | M10 |
| RENAME-05 | 新旧键相同 | SET k v → RENAME k k | `OK`（无变化） | 边界 |
| RENAME-06 | store_full 不触发 | 已有100键 → RENAME key0 newkey（覆盖自身） | `OK` | 不增加计数 |

---

## 14. TYPE 命令

### 需求级别：MAY (A1) — 低优先级（可选覆盖）

| 场景 ID | 等价类 | 输入 | 预期输出 | 备注 |
|---------|--------|------|----------|------|
| TYPE-01 | 字符串类型 | SET k hello → TYPE k | `STRING` | 基础功能 |
| TYPE-02 | 整数类型 | SET k 123 → TYPE k | `INTEGER` | `int("123")` 成功 |
| TYPE-03 | 负数值 | SET k -456 → TYPE k | `INTEGER` | ⚠️ `int("-456")` 成功（实现确认） |
| TYPE-04 | 浮点数 | SET k 3.14 → TYPE k | `STRING` | ⚠️ `int("3.14")` 抛异常（实现确认） |
| TYPE-05 | 前导零 | SET k 007 → TYPE k | `INTEGER` | ⚠️ `int("007")` → 7，成功（实现确认） |
| TYPE-05b | 带空格数字 | SET k " 123 " → TYPE k | `INTEGER` | ⚠️ `int(" 123 ")` 自动 strip（实现确认） |
| TYPE-06 | 键不存在 | `TYPE noexist` | `ERR key_not_found` | 错误处理 |
| TYPE-07 | 空字符串 | SET k "" → TYPE k | `STRING` | 空串非 INTEGER |
| TYPE-08 | 过期键 | SETEX k 1 val → sleep(1.5) → TYPE k | `ERR key_not_found` | S1: 过期处理 |

---

## 15. DUMP 命令

### 需求级别：MAY (A2) — 低优先级（可选覆盖）

| 场景 ID | 等价类 | 输入 | 预期输出 | 备注 |
|---------|--------|------|----------|------|
| DUMP-01 | 有数据 dump | SET k1 v1 → SET k2 v2 → DUMP | k1=v1 / k2=v2 / `END` | 基础功能 |
| DUMP-02 | 空 store dump | DUMP（初始状态） | `END` | 边界 |
| DUMP-03 | FLUSH 后 dump | SET k1 v1 → FLUSH → DUMP | `END` | 清空后 |
| DUMP-04 | 100 键 dump | 填充100键 → DUMP | 100行 + `END` | 最大容量 |
| DUMP-05 | 值含等号 | SET k val=ue → DUMP | `k=val=ue` | 边界：等号解析 |

---

## 16. 需求覆盖总览 & 开发优先级

### MUST（12 条）— 全部必须覆盖

| 需求 | 描述 | 现有测试 | 缺失 |
|------|------|----------|------|
| M1 | SET 存储值 | ✅ | 键/值长度边界 (63/64/65, 1023/1024/1025) |
| M2 | GET 返回值或 ERR | ✅✅ | 过期键 GET |
| M3 | DEL 删除键 | ✅ | DEL 不存在键、重复 DEL |
| M4 | KEYS 列出键 | ✅ | 空 store KEYS |
| M5 | COUNT 返回计数 | ✅ | COUNT 0 |
| M6 | EXISTS TRUE/FALSE | ✅✅ | 过期键 EXISTS |
| M7 | FLUSH 清空 | ✅ | 空 store FLUSH |
| M8 | 错误响应格式 | ❌ 无独立测试 | 需验证 5 种错误码格式 |
| M9 | 未知命令 | ✅ | — |
| M10 | 键超长 (64) | ✅ | 边界 64/65 字符 |
| M11 | 值超大 (1024) | ✅ | 边界 1024/1025 字符 |
| M12 | store_full | ✅✅ | MSET/APPEND store_full |

### SHOULD（5 条）— 至少覆盖 3 条

| 需求 | 描述 | 现有测试 | 目标 |
|------|------|----------|------|
| S1 | 过期键处理 (SETEX+TTL) | ❌ | ✅ 最高优先级 |
| S2 | MSET 多键设置 | ❌ | ✅ 高优先级 |
| S3 | MGET 多键获取 | ❌ | ✅ 高优先级 |
| S4 | TTL 返回剩余时间 | ❌ | 可选 |
| S5 | APPEND 追加 | ✅ | 追加边界 |

### 建议 3 条 SHOULD 覆盖：**S1 + S2 + S3**

---

## 17. 测试开发建议顺序

```
Phase 1 — 解锁 3 条 SHOULD 覆盖（约 18 条新测试）：
  1. SETEX 基础 + TTL 查询 (S1)
  2. SETEX 过期后 GET/EXISTS (S1 闭环) — 含 time.sleep
  3. MSET 正常多对 + 原子性错误回滚 (S2)
  4. MGET 正常多键 + NIL 返回 (S3)

Phase 2 — 补充 MUST 边界（约 10 条新测试）：
  5. SET 键值长度边界 (M10/M11 63/64/65, 1023/1024/1025)
  6. DEL 不存在键 (M3)
  7. KEYS 空 store (M4)
  8. COUNT 0 (M5)
  9. FLUSH 空 store (M7)

Phase 3 — 完善 SHOULD/MAY（约 15 条新测试）：
  10. APPEND 创建新键/追加超限 (S5)
  11. TTL 无过期/-1 返回值 (S4)
  12. RENAME 全套 (A3)
  13. TYPE 全套 (A1)
  14. DUMP 全套 (A2)
```

### 预计新增测试总数：约 43 条（Phase 1: ~18, Phase 2: ~10, Phase 3: ~15）
