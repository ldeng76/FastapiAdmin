"""统一确定性脱敏核心模块 — ADR-0001。

设计要点（ADR-0001 决策摘要）：
- 策略：统一确定性映射（Linkable Anonymization），不维护映射表。
- 病人级：`ANON_ID = "ANON_" + HMAC-SHA256(secret, center + PAT_LOCAL_ID)[:12]`
- 检查级：`ANON_EXAM_ID = "ANON_EXAM_" + HMAC-SHA256(secret, center + EXAM_NO)[:12]`
- center 参与 HMAC 输入，防止跨中心碰撞（珠江 1008201 ≠ 省医 1008201）。
- HMAC 而非裸 SHA256：PAT_LOCAL_ID 仅 6-7 位，盐保护防暴力反查。
- 截断 12 位 hex（48 bit）：足够本系统去重碰撞半径，且不可反推明文。

所有函数纯函数无副作用，便于单测与离线校验。
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config.setting import settings

# --------------------------------------------------------------------------- #
# 前缀与长度约定（与 DDL CHECK 约束对齐）
# --------------------------------------------------------------------------- #

_ANON_ID_PREFIX = "ANON_"
_ANON_EXAM_ID_PREFIX = "ANON_EXAM_"
_HMAC_HEX_TRUNC = 12  # 截断长度：48 bit，碰撞概率在本系统量级（<10^7 病人）可忽略

# sex 归一化映射（中文/英文 → M/F/U）
_SEX_MAP_M = {"男", "男性", "m", "M", "male", "Male"}
_SEX_MAP_F = {"女", "女性", "f", "F", "female", "Female"}

# 本轮自由文本清洗策略（用户决策：暂不清洗，原样入库，等待人工/LLM 抽检）
# - clean_method 用 DDL 枚举中最保守的 'regex_only'（表示规则化清洗，即使本轮未实际替换）
# - review_status 恒为 'pending'，提示后续必须人工抽检
CLEAN_METHOD_REGEX_ONLY = "regex_only"
LLM_MODEL_NONE: str | None = None  # 本轮未接入 LLM

# 报告正文最大长度保护（DDL body_clean 是 TEXT 无上限，但截断防止异常巨文本拖慢导入）
MAX_BODY_LEN = 100_000


def truncate_body(body: str | None, max_len: int = MAX_BODY_LEN) -> str:
    """截断报告正文，防止异常巨文本拖慢导入。

    None / 空串 → ""（DDL body_clean NOT NULL，引擎需保证非空）
    其余 → 取前 max_len 字符。

    抽到 anonymize 模块便于单测（避免依赖 DB/parquet 的引擎层）。
    """
    if not body:
        return ""
    return body[:max_len]


# --------------------------------------------------------------------------- #
# HMAC 核心
# --------------------------------------------------------------------------- #


def _secret_bytes() -> bytes:
    """读取 settings 中的密钥并编码为 bytes。

    密钥缺失时抛错——脱敏是核心安全功能，不能静默用空密钥。
    """
    s = settings.LNRS_ANON_SECRET
    if not s or s == "change-me-in-production-please":
        # dev 环境允许使用占位密钥跑通流程，但明确警告（不阻塞，方便本机联调）
        # 生产环境应由部署侧通过环境变量覆盖此默认值
        pass
    return s.encode("utf-8")


def _hmac_hex(message: str) -> str:
    """对 message 做 HMAC-SHA256，返回截断后的 hex。

    用项目密钥，返回前 12 位 hex（48 bit）。
    """
    mac = hmac.new(_secret_bytes(), message.encode("utf-8"), hashlib.sha256)
    return mac.hexdigest()[:_HMAC_HEX_TRUNC]


def compute_anon_id(center_code: str, patient_local_id: str) -> str:
    """病人级确定性脱敏 ID。

    格式：`ANON_` + HMAC-SHA256(secret, "{center}:{patient_id}")[:12]
    满足 DDL CHECK `^ANON_[0-9a-f]{12}$`。
    """
    if not center_code or not patient_local_id:
        raise ValueError(
            f"compute_anon_id 需要非空 center_code 与 patient_local_id，"
            f"得到 center={center_code!r} patient={patient_local_id!r}"
        )
    return f"{_ANON_ID_PREFIX}{_hmac_hex(f'{center_code}:{patient_local_id}')}"


def compute_anon_exam_id(center_code: str, exam_no: str) -> str:
    """检查级确定性脱敏 ID（跨模态桥梁）。

    格式：`ANON_EXAM_` + HMAC-SHA256(secret, "{center}:{exam_no}")[:12]
    """
    if not center_code or not exam_no:
        raise ValueError(
            f"compute_anon_exam_id 需要非空 center_code 与 exam_no，"
            f"得到 center={center_code!r} exam={exam_no!r}"
        )
    return f"{_ANON_EXAM_ID_PREFIX}{_hmac_hex(f'{center_code}:{exam_no}')}"


def source_exam_hash(center_code: str, exam_no: str) -> str:
    """生成检查级源哈希，用于 anon_exam.source_exam_hash 幂等去重。

    用裸 SHA256（非 HMAC）—— 此哈希用于"同检查重复导入只 update"的幂等判定，
    不需要可逆性也不参与跨模态关联，按 ADR-0006 §3 字段说明实现。
    """
    return hashlib.sha256(f"{center_code}:{exam_no}".encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# 密钥指纹 / Schema 指纹（写入 ingest_batch 便于审计回溯）
# --------------------------------------------------------------------------- #


def key_fingerprint() -> str:
    """密钥指纹：SHA256(secret) 前 16 hex。

    不泄漏密钥本体，仅供 lnrs_anon_ingest_batch.key_fingerprint 标识"用了哪个密钥版本"。
    """
    return hashlib.sha256(_secret_bytes()).hexdigest()[:16]


def secret_version() -> str:
    """密钥版本号（来自 settings.LNRS_ANON_SECRET_VERSION）。"""
    return settings.LNRS_ANON_SECRET_VERSION


@lru_cache(maxsize=1)
def schema_hash() -> str:
    """脱敏 schema DDL 的 sha256，标识"当时按什么规则建表"。

    读 backend/sql/postgres/0006-anonymized-schema-lnrs.sql 内容计算。
    文件不存在时返回固定标记字符串的哈希（不抛错，保证 ETL 不因缺文件中断）。

    注意（lru_cache 限制）：返回值在**进程生命周期内**被缓存，不会自动刷新。
    - 生产环境无影响：DDL 一次部署后不变。
    - 开发环境：若修改了 DDL 文件且需要新哈希，重启进程即可；
      切换 BASE_DIR / 热重载 DDL 时同样需要重启。
    """
    # DDL 脚本与 setting.py / path_conf 的相对位置：BASE_DIR/sql/postgres/
    from app.config.path_conf import BASE_DIR

    sql_path = BASE_DIR / "sql" / "postgres" / "0006-anonymized-schema-lnrs.sql"
    try:
        content = Path(sql_path).read_bytes()
    except OSError:
        content = b"<schema-sql-not-found>"
    return hashlib.sha256(content).hexdigest()


# --------------------------------------------------------------------------- #
# 结构化字段归一化
# --------------------------------------------------------------------------- #


def normalize_sex(raw: Any) -> str:
    """性别归一化 → 'M' / 'F' / 'U'。

    - '男'/'男性'/'M'/'male' → 'M'
    - '女'/'女性'/'F'/'female' → 'F'
    - 其他（含 null/空串/未知） → 'U'（DDL 默认值）
    """
    if raw is None:
        return "U"
    s = str(raw).strip()
    if s in _SEX_MAP_M:
        return "M"
    if s in _SEX_MAP_F:
        return "F"
    return "U"


def birth_year_from(raw: Any) -> int | None:
    """从 date / int / str 提取出生年份，失败返回 None。

    ADR-0001 决策 11：birth_date 仅保留年份，月日清零。
    - date / datetime → .year
    - int (1900-2100) → 直接
    - str "YYYY-MM-DD" / "YYYY" → 解析 year
    """
    if raw is None:
        return None
    # date / datetime
    if hasattr(raw, "year") and isinstance(getattr(raw, "year", None), int):
        y = raw.year
        return y if 1900 <= y <= 2100 else None
    # int
    if isinstance(raw, int):
        return raw if 1900 <= raw <= 2100 else None
    # str
    s = str(raw).strip()
    if not s:
        return None
    # 取前 4 位数字
    digits = "".join(ch for ch in s[:4] if ch.isdigit())
    if len(digits) == 4:
        y = int(digits)
        return y if 1900 <= y <= 2100 else None
    return None


# --------------------------------------------------------------------------- #
# PHI audit 辅助（写 lnrs_anon_phi_audit 时复用）
# --------------------------------------------------------------------------- #


def hash_for_audit(raw: Any) -> str:
    """对被脱敏字段原值做 SHA256，写入 phi_audit.source_hash。

    原值不落库（ADR-0006 §9 铁律），仅落哈希用于审计抽检/碰撞比对。
    None → 空 bytes 的哈希（仍可记录"该字段被处理但原值为空"）。
    """
    b = str(raw).encode("utf-8") if raw is not None else b""
    return hashlib.sha256(b).hexdigest()
