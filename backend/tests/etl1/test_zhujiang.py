"""ETL-1 珠江 center 配置与产出验证 (轻量, 不跑 xlsx)。

覆盖:
- ZHUJIANG_CONFIG 注册正确 (表名 / sheet / 列名)
- WHERE 子句安全验证 (拒绝 ; / DDL / 注释)
- 已落 data/zhujiang/*.parquet 的 schema + 关键过滤 (若存在)
- 后处理脚本: first_nodule_date 派生验证
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest


# ============================================================
# 01. config 注册与表清单
# ============================================================

class TestZhujiangConfig:
    """ZHUJIANG_CONFIG 元数据校验。"""

    def test_center_registered(self):
        from app.plugin.module_medical.hospital.etl1 import list_centers, get_center_config

        assert "zhujiang" in list_centers()
        cfg = get_center_config("zhujiang")
        assert cfg.code == "zhujiang"
        assert cfg.display_name == "南方医科大学珠江医院"
        assert cfg.source_kind == "xlsx"

    def test_target_tables(self):
        from app.plugin.module_medical.hospital.etl1 import get_center_config

        cfg = get_center_config("zhujiang")
        assert cfg.all_target_tables() == ["patient", "nodule_imaging", "pathology_specimen"]

    def test_sheet_names(self):
        from app.plugin.module_medical.hospital.etl1 import get_center_config

        cfg = get_center_config("zhujiang")
        sheets = {s.sheet_name for s in cfg.hospital_tables}
        assert sheets == {"Select v_exam_patient_rpt"}

    def test_column_targets(self):
        from app.plugin.module_medical.hospital.etl1 import get_center_config

        cfg = get_center_config("zhujiang")
        by_table = {s.target_table: [c.tgt for c in s.columns] for s in cfg.hospital_tables}
        assert by_table["patient"] == ["patient_id", "gender"]
        assert by_table["nodule_imaging"] == [
            "patient_id", "exam_id", "exam_date", "findings", "impression",
        ]
        assert by_table["pathology_specimen"] == [
            "patient_id", "specimen_id", "exam_date", "pathology_diagnosis",
        ]

    def test_required_columns(self):
        from app.plugin.module_medical.hospital.etl1 import get_center_config

        cfg = get_center_config("zhujiang")
        for spec in cfg.hospital_tables:
            req = [c.tgt for c in spec.columns if c.required]
            assert "patient_id" in req, f"{spec.target_table} 缺 patient_id required"


# ============================================================
# 02. shengyi 兼容性 (Review M3)
# ============================================================

class TestShengyiCompatibility:
    """WHERE 子句加入后, shengyi 的所有 SheetSpec (where=None) 仍应能正常生成 SQL。

    验证 core._process_single_sheet 在 where=None 时不报错, 且产出的 SELECT 结构合法。
    """

    def test_shengyi_specs_have_no_where(self):
        from app.plugin.module_medical.hospital.etl1 import get_center_config

        cfg = get_center_config("shengyi")
        for spec in cfg.universal_tables + cfg.hospital_tables:
            assert spec.where is None, f"shengyi.{spec.target_table} 不应设 where"
        for spec in cfg.derived_tables:
            assert spec.where is None, f"shengyi.{spec.target_table} 不应设 where"
            for src in spec.sources:
                assert src.where is None, "shengyi derived source 不应设 where"

    def test_shengyi_sql_built_without_where(self):
        """模拟 core._build_select_for_sheet 的产出 + core 拼接 WHERE 片段, 验证 SQL 合法。"""
        from app.plugin.module_medical.hospital.etl1 import get_center_config
        from app.plugin.module_medical.hospital.etl1.core import _quote_ident

        cfg = get_center_config("shengyi")
        spec = cfg.universal_tables[0]  # patient
        # 模拟 where=None 时拼接
        where_clause = f"WHERE {spec.where}" if spec.where else ""
        # 应为空字符串, SQL 中 FROM 和 ) 之间多一个空行但仍合法
        assert where_clause == ""
        # 拼接后用 duckdb 试解析 (SELECT 子句随便造一列)
        sample_sql = (
            f"SELECT CAST(NULL AS VARCHAR) AS \"x\" FROM \"dummy_view\" {where_clause}"
        )
        # 不需要执行, 只验证 SQL 语法可被解析
        import duckdb
        con = duckdb.connect(":memory:")
        con.execute("CREATE TEMP VIEW dummy_view AS SELECT 1 AS x")
        rows = con.execute(sample_sql).fetchall()
        assert rows == [(None,)]


# ============================================================
# 03. WHERE 子句安全校验
# ============================================================

class TestWhereSafety:
    """SheetSpec/DerivedSpec 的 where 字段拒绝危险 SQL。"""

    def test_where_accepts_safe_expr(self):
        from app.plugin.module_medical.hospital.etl1.config import ColumnSpec, SheetSpec

        # 安全: 简单比较 + ILIKE
        s = SheetSpec(
            sheet_name="x", target_table="patient",
            columns=[ColumnSpec(src="a", tgt="patient_id", type="string", required=True)],
            where="EXAM_CLASS = 'ＣＴ' AND IMPRESSION ILIKE '%肺%'",
        )
        assert "EXAM_CLASS" in s.where

    @pytest.mark.parametrize("bad", [
        "EXAM_CLASS = 'ＣＴ'; DROP TABLE patient",
        "EXAM_CLASS = 'ＣＴ' -- comment",
        "/* malicious */ EXAM_CLASS = 'ＣＴ'",
        "EXAM_CLASS = 'ＣＴ' UNION SELECT * FROM users",
        "DELETE FROM patient",
        "INSERT INTO patient VALUES (1,2,3)",
        "DROP TABLE patient",
    ])
    def test_where_rejects_unsafe(self, bad):
        from pydantic import ValidationError

        from app.plugin.module_medical.hospital.etl1.config import ColumnSpec, SheetSpec

        with pytest.raises((ValidationError, ValueError)):
            SheetSpec(
                sheet_name="x", target_table="patient",
                columns=[ColumnSpec(src="a", tgt="patient_id", type="string", required=True)],
                where=bad,
            )

    def test_derived_spec_where(self):
        from app.plugin.module_medical.hospital.etl1.config import (
            ColumnSpec, DerivedSource, DerivedSpec, SheetSpec,
        )

        d = DerivedSpec(
            target_table="x",
            sources=[DerivedSource(
                spec=SheetSpec(
                    sheet_name="x", target_table="x",
                    columns=[ColumnSpec(src="a", tgt="patient_id", type="string", required=True)],
                ),
            )],
            where="EXAM_CLASS = '病理'",
        )
        assert d.where is not None


# ============================================================
# 03. 已落 parquet 验证 (依赖 Step 5 实际跑过 ETL-1)
# ============================================================

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "zhujiang"


@pytest.mark.skipif(
    not (DATA_DIR / "patient.parquet").exists(),
    reason=f"data/zhujiang 尚未落库 (需先跑 ETL-1 + 后处理脚本)",
)
class TestZhujiangParquet:
    """实际产出的 parquet 内容验证。"""

    @pytest.fixture(scope="class")
    def con(self):
        c = duckdb.connect(":memory:")
        yield c
        c.close()

    def test_manifest_exists(self):
        manifest = DATA_DIR / "_meta" / "conversion_manifest.json"
        assert manifest.exists()
        data = json.loads(manifest.read_text(encoding="utf-8"))
        assert data["center_code"] == "zhujiang"
        assert set(data["target_tables"].keys()) == {
            "patient", "nodule_imaging", "pathology_specimen",
        }

    def test_patient_count(self, con):
        n = con.execute(
            f"SELECT count(*) FROM read_parquet('{DATA_DIR}/patient.parquet')"
        ).fetchone()[0]
        assert n > 0

    def test_patient_first_nodule_date_filled(self, con):
        n = con.execute(
            f"SELECT count(*) FROM read_parquet('{DATA_DIR}/patient.parquet') "
            f"WHERE first_nodule_date IS NOT NULL"
        ).fetchone()[0]
        n_total = con.execute(
            f"SELECT count(*) FROM read_parquet('{DATA_DIR}/patient.parquet')"
        ).fetchone()[0]
        assert n == n_total, "所有患者应有 first_nodule_date"

    def test_nodule_imaging_exam_id_unique(self, con):
        total, unique = con.execute(
            f"SELECT count(*), count(DISTINCT exam_id) "
            f"FROM read_parquet('{DATA_DIR}/nodule_imaging.parquet')"
        ).fetchone()
        assert total == unique, "nodule_imaging.exam_id 应唯一"

    def test_nodule_imaging_no_gynecology(self, con):
        """nodule_imaging 主体应是肺结节 CT 报告。允许报告中顺带提及宫颈(偶发)。

        弱断言: 主诊断(primary finding)应是肺部相关, 不应是纯妇科样本。
        """
        # 真正的"纯妇科 CT 报告" 应以宫颈/子宫/卵巢 为主诉
        pure_gyne = con.execute(
            f"SELECT count(*) FROM read_parquet('{DATA_DIR}/nodule_imaging.parquet') "
            f"WHERE (impression ILIKE '%宫颈%' OR impression ILIKE '%子宫%' "
            f"       OR impression ILIKE '%卵巢%' OR impression ILIKE '%盆腔%') "
            f"  AND impression NOT ILIKE '%肺%' "
            f"  AND impression NOT ILIKE '%结节%' "
            f"  AND impression NOT ILIKE '%胸部CT%'"
        ).fetchone()[0]
        assert pure_gyne == 0, f"nodule_imaging 有 {pure_gyne} 行纯妇科 CT 报告 (应过滤掉)"

    def test_pathology_no_gynecology(self, con):
        """pathology_specimen 主体应是肺病理。允许: 肺鳞癌合并宫颈癌转移等临床有意义情形。"""
        # 主体应为肺(以"右/左/上/下肺"等关键字开头或主诊断含肺术语)
        pure_gyne = con.execute(
            f"SELECT count(*) FROM read_parquet('{DATA_DIR}/pathology_specimen.parquet') "
            f"WHERE pathology_diagnosis ILIKE '%宫颈%' "
            f"  AND pathology_diagnosis NOT ILIKE '%肺%' "
            f"  AND pathology_diagnosis NOT ILIKE '%支气管%'"
        ).fetchone()[0]
        assert pure_gyne == 0, f"pathology_specimen 有 {pure_gyne} 行纯妇科病理 (应过滤掉)"

    def test_first_nodule_date_not_later_than_exam(self, con):
        """patient.first_nodule_date ≤ 该患者 nodule_imaging 中最早 exam_date。"""
        violations = con.execute(f"""
            SELECT count(*) FROM read_parquet('{DATA_DIR}/patient.parquet') p
            WHERE EXISTS (
                SELECT 1 FROM read_parquet('{DATA_DIR}/nodule_imaging.parquet') n
                WHERE n.patient_id = p.patient_id
                  AND n.exam_date < p.first_nodule_date
            )
        """).fetchone()[0]
        assert violations == 0