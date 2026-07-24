"""脱敏核心模块单测 — ADR-0001 规则验证（无需数据库）。

覆盖：
- HMAC 确定性：同输入同输出
- center 参与哈希：跨中心同 patient_id 不碰撞
- 截断长度与格式（与 DDL CHECK 约束对齐）
- sex / birth_date 归一化各分支
- 密钥指纹 / schema_hash 稳定性
"""

from __future__ import annotations

from datetime import date

import pytest

from app.plugin.module_medical.hospital.anonymize import (
    CLEAN_METHOD_REGEX_ONLY,
    MAX_BODY_LEN,
    birth_date_from,
    compute_anon_exam_id,
    compute_anon_id,
    hash_for_audit,
    key_fingerprint,
    normalize_sex,
    schema_hash,
    secret_version,
    source_exam_hash,
    truncate_body,
)


class TestAnonId:
    """病人级 anon_id 生成规则。"""

    def test_deterministic(self):
        """同输入必须产生同输出（确定性脱敏的核心）。"""
        a = compute_anon_id("zhujiang", "120408")
        b = compute_anon_id("zhujiang", "120408")
        assert a == b

    def test_format(self):
        """格式必须匹配 DDL CHECK `^ANON_[0-9a-f]{12}$`。"""
        aid = compute_anon_id("zhujiang", "120408")
        assert aid.startswith("ANON_")
        hex_part = aid[len("ANON_"):]
        assert len(hex_part) == 12
        assert all(c in "0123456789abcdef" for c in hex_part)

    def test_center_in_hmac_input(self):
        """center_code 参与哈希：同一 patient_id 在不同中心得到不同 anon_id。"""
        zj = compute_anon_id("zhujiang", "1008201")
        sy = compute_anon_id("shengyi", "1008201")
        assert zj != sy, "跨中心同 patient_id 不应碰撞（ADR-0001 决策 2）"

    def test_patient_id_changes(self):
        """不同 patient_id 得到不同 anon_id。"""
        a = compute_anon_id("zhujiang", "120408")
        b = compute_anon_id("zhujiang", "120409")
        assert a != b

    def test_empty_input_raises(self):
        """center / patient_local_id 任一为空必须报错。"""
        with pytest.raises(ValueError):
            compute_anon_id("", "120408")
        with pytest.raises(ValueError):
            compute_anon_id("zhujiang", "")
        with pytest.raises(ValueError):
            compute_anon_id("zhujiang", None)  # type: ignore[arg-type]


class TestAnonExamId:
    """检查级 anon_exam_id 生成规则。"""

    def test_format(self):
        """格式必须匹配 `^ANON_EXAM_[0-9a-f]{12}$`。"""
        eid = compute_anon_exam_id("zhujiang", "EXAM001")
        assert eid.startswith("ANON_EXAM_")
        hex_part = eid[len("ANON_EXAM_"):]
        assert len(hex_part) == 12
        assert all(c in "0123456789abcdef" for c in hex_part)

    def test_deterministic(self):
        a = compute_anon_exam_id("xinqiao", "E999")
        b = compute_anon_exam_id("xinqiao", "E999")
        assert a == b

    def test_distinct_from_anon_id(self):
        """病人级与检查级前缀不同，绝不混用。"""
        aid = compute_anon_id("zhujiang", "120408")
        eid = compute_anon_exam_id("zhujiang", "120408")
        assert aid != eid
        assert aid.startswith("ANON_")
        assert eid.startswith("ANON_EXAM_")


class TestSourceExamHash:
    def test_format_64_hex(self):
        h = source_exam_hash("zhujiang", "EXAM001")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_deterministic(self):
        assert source_exam_hash("zhujiang", "X1") == source_exam_hash("zhujiang", "X1")

    def test_center_affects_hash(self):
        assert source_exam_hash("zhujiang", "X1") != source_exam_hash("xinqiao", "X1")


class TestNormalizeSex:
    """性别归一化 → HQMS RC001 0/1/2/9。

    ADR-0008 决策5：归一化逻辑下沉到 enum_normalization，anonymize.normalize_sex
    仅作转发。缓存归属 enum_normalization._SEX_MAP_CACHE，故 monkeypatch 目标改为
    该模块。同时覆盖向后兼容入口（从 anonymize 导入 normalize_sex）。
    """

    @pytest.fixture(autouse=True)
    def mapping_cache(self, monkeypatch):
        # 缓存归属 enum_normalization（ADR-0008 决策5），patch 真正的持有者
        monkeypatch.setattr(
            "app.plugin.module_medical.hospital.enum_normalization._SEX_MAP_CACHE",
            {"男": "1", "男性": "1", "m": "1", "male": "1", "女": "2", "女性": "2", "f": "2", "female": "2", "未知": "0", "9": "9"},
        )

    @pytest.mark.parametrize("raw,expected", [("男", "1"), ("m", "1"), ("male", "1"), ("女", "2"), ("f", "2"), ("female", "2"), ("未知", "0"), ("9", "9")])
    def test_known_values(self, raw, expected):
        assert normalize_sex(raw) == expected

    def test_unknown_to_zero(self):
        assert normalize_sex("") == "0"
        assert normalize_sex(None) == "0"
        assert normalize_sex("other") == "0"

    def test_empty_cache_returns_zero(self, monkeypatch):
        """缓存未预热（load_sex_mapping 未调用）时，所有输入返回 '0'（未知）。

        覆盖 ADR-0008 决策5 的硬编码兜底退役后行为：
        不再回退 _SEX_MAP_M/F，缓存空即返回默认值。
        """
        monkeypatch.setattr(
            "app.plugin.module_medical.hospital.enum_normalization._SEX_MAP_CACHE", {}
        )
        assert normalize_sex("男") == "0"
        assert normalize_sex("female") == "0"

    def test_strip_whitespace(self):
        assert normalize_sex("  男  ") == "1"


class TestBirthDate:
    """birth_date 提取（ADR-0006：保留到日，精度不足时补齐）。"""

    def test_from_full_date(self):
        """date 对象：完整保留。"""
        assert birth_date_from(date(1963, 10, 13)) == date(1963, 10, 13)

    def test_from_int_year(self):
        """纯 int 年份：补齐为 YYYY-01-01。"""
        assert birth_date_from(1980) == date(1980, 1, 1)

    def test_from_iso_full_string(self):
        """YYYY-MM-DD 字符串：完整解析。"""
        assert birth_date_from("1980-05-06") == date(1980, 5, 6)

    def test_from_year_month_string(self):
        """YYYY-MM 字符串：日置 01。"""
        assert birth_date_from("1980-05") == date(1980, 5, 1)

    def test_from_year_only_string(self):
        """YYYY 字符串：月日置 01-01。"""
        assert birth_date_from("1980") == date(1980, 1, 1)

    def test_none(self):
        assert birth_date_from(None) is None

    def test_empty_string(self):
        assert birth_date_from("") is None

    def test_out_of_range(self):
        assert birth_date_from(1800) is None
        assert birth_date_from(2200) is None
        assert birth_date_from(date(1700, 1, 1)) is None

    def test_garbage_string(self):
        assert birth_date_from("abc") is None


class TestKeyFingerprintAndSchema:
    def test_key_fingerprint_format(self):
        fp = key_fingerprint()
        assert len(fp) == 16
        assert all(c in "0123456789abcdef" for c in fp)

    def test_key_fingerprint_stable(self):
        assert key_fingerprint() == key_fingerprint()

    def test_secret_version(self):
        v = secret_version()
        assert isinstance(v, str) and v

    def test_schema_hash_stable(self):
        """schema_hash 是 lru_cache，重复调用必须稳定。"""
        assert schema_hash() == schema_hash()

    def test_schema_hash_64_hex(self):
        h = schema_hash()
        assert len(h) == 64


class TestHashForAudit:
    def test_deterministic(self):
        assert hash_for_audit("张三") == hash_for_audit("张三")

    def test_none_to_empty_hash(self):
        """None 输入应映射到空 bytes 的 sha256（不是报错）。"""
        import hashlib

        assert hash_for_audit(None) == hashlib.sha256(b"").hexdigest()

    def test_returns_64_hex(self):
        h = hash_for_audit("sensitive-value")
        assert len(h) == 64


class TestConstants:
    """常量与枚举取值约束（与 DDL 对齐）。"""

    def test_clean_method_constant(self):
        assert CLEAN_METHOD_REGEX_ONLY == "regex_only"

    def test_max_body_len_constant(self):
        # 防止被误改小导致正常报告被截断；也防止被改大导致内存/导入性能问题
        assert MAX_BODY_LEN == 100_000


class TestTruncateBody:
    """报告正文截断（防止异常巨文本拖慢导入）。"""

    def test_none_to_empty(self):
        """None 输入必须返回 ""（DDL body_clean NOT NULL，引擎需保证非空）。"""
        assert truncate_body(None) == ""

    def test_empty_string_to_empty(self):
        assert truncate_body("") == ""

    def test_short_body_unchanged(self):
        assert truncate_body("腺癌。") == "腺癌。"

    def test_exact_max_length_unchanged(self):
        body = "x" * MAX_BODY_LEN
        assert truncate_body(body) == body
        assert len(truncate_body(body)) == MAX_BODY_LEN

    def test_over_max_length_truncated(self):
        """超过 MAX_BODY_LEN 必须截断到 MAX_BODY_LEN。"""
        body = "y" * (MAX_BODY_LEN + 1000)
        result = truncate_body(body)
        assert len(result) == MAX_BODY_LEN
        assert result == "y" * MAX_BODY_LEN

    def test_multibyte_truncation_uses_chars_not_bytes(self):
        """Python 字符串切片按字符数计——中文超长也应按字符截断。

        MAX_BODY_LEN=100_000 字符（非字节）足以容纳任何真实报告；
        若误按字节截断可能在多字节边界处产生乱码，此处验证字符语义。
        """
        body = "中" * (MAX_BODY_LEN + 5)
        result = truncate_body(body)
        assert len(result) == MAX_BODY_LEN
        assert result == "中" * MAX_BODY_LEN

    def test_custom_max_len(self):
        """支持调用方自定义上限。"""
        assert truncate_body("abcdef", max_len=3) == "abc"
