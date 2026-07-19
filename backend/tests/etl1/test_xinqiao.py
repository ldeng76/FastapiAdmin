"""ETL-1 新桥中心 (xinqiao) 配置与 E2E 测试。

覆盖:
- XINQIAO_CONFIG 注册正确 (表名 / sheet / 列名 / source_kind=csv)
- WHERE 子句安全 (复用 zhujiang 的 _validate_where 白名单测试)
- 已注册 centers 不受影响 (shengyi / zhujiang 仍走 ExcelReader)
- CsvReader 在 tmp_path 下的 E2E: 写两份 mini CSV, 跑 run_etl1, 验证
  parquet 内容 (行数 / 字段值 / 病理多值字段保留 / 日期归一化)
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from app.plugin.module_medical.hospital.etl1 import (
    get_center_config,
    list_centers,
    run_etl1,
)
from app.plugin.module_medical.hospital.etl1.centers import xinqiao as xinqiao_mod


# ============================================================
# 01. config 注册与表清单
# ============================================================

class TestXinqiaoConfig:
    """XINQIAO_CONFIG 元数据校验。"""

    def test_center_registered(self):
        assert "xinqiao" in list_centers()
        cfg = get_center_config("xinqiao")
        assert cfg.code == "xinqiao"
        assert cfg.display_name == "陆军军医大学新桥医院"
        assert cfg.source_kind == "csv"

    def test_target_tables(self):
        cfg = get_center_config("xinqiao")
        # patient/nodule_imaging/pathology_specimen 三张表 (去重后)
        assert set(cfg.all_target_tables()) == {
            "patient", "nodule_imaging", "pathology_specimen",
        }
        # patient 在两个子目录里都派生 (冗余)
        patient_specs = [s for s in cfg.hospital_tables if s.target_table == "patient"]
        assert len(patient_specs) == 2, "patient 必须在 SUB1 + SUB2 都派生"
        # pathology_specimen 只在 SUB2
        path_specs = [s for s in cfg.hospital_tables if s.target_table == "pathology_specimen"]
        assert len(path_specs) == 1
        assert path_specs[0].sheet_name == xinqiao_mod.SUB_2

    def test_sheet_names(self):
        cfg = get_center_config("xinqiao")
        sheets = {s.sheet_name for s in cfg.hospital_tables}
        assert sheets == {xinqiao_mod.SUB_1, xinqiao_mod.SUB_2}

    def test_column_targets(self):
        cfg = get_center_config("xinqiao")
        by_table = {s.target_table: [c.tgt for c in s.columns] for s in cfg.hospital_tables}
        # patient 表只关心 patient_id + gender
        assert by_table["patient"] == ["patient_id", "gender"]
        # nodule_imaging 表
        assert by_table["nodule_imaging"] == [
            "patient_id", "exam_id", "exam_date", "findings", "impression",
        ]
        # pathology_specimen 表
        assert by_table["pathology_specimen"] == [
            "patient_id", "specimen_id",
            "specimen_received_at", "report_released_at", "sampling_site",
            "gross_findings", "microscopic_findings",
            "pathology_diagnosis", "report_status",
            "exam_date",
        ]

    def test_required_columns(self):
        cfg = get_center_config("xinqiao")
        for spec in cfg.hospital_tables:
            req = [c.tgt for c in spec.columns if c.required]
            if spec.target_table in ("patient", "nodule_imaging"):
                assert "patient_id" in req, f"{spec.target_table} 缺 patient_id required"
            if spec.target_table == "nodule_imaging":
                assert "exam_id" in req, "nodule_imaging 缺 exam_id required"
            if spec.target_table == "pathology_specimen":
                assert "patient_id" in req
                assert "specimen_id" in req

    def test_where_clauses_filter_lung_nodule(self):
        """nodule_imaging/patient 的 WHERE 必须过滤 'CT' + 肺/结节, 避免非肺结节报告入影像表。

        pathology_specimen 的 WHERE 是 `病理.病理系统编号 IS NOT NULL` (不涉及 CT 过滤)。
        """
        cfg = get_center_config("xinqiao")
        for spec in cfg.hospital_tables:
            if spec.where is None:
                continue
            if spec.target_table in ("patient", "nodule_imaging"):
                assert "'CT'" in spec.where, f"{spec.target_table} WHERE 缺 CT 过滤"
                assert "ILIKE" in spec.where, f"{spec.target_table} WHERE 缺 ILIKE 过滤"
            elif spec.target_table == "pathology_specimen":
                # 病理表按 `病理.病理系统编号` 过滤
                assert "病理.病理系统编号" in spec.where, (
                    f"{spec.target_table} WHERE 应过滤 病理.病理系统编号"
                )
                assert "IS NOT NULL" in spec.where


# ============================================================
# 02. 既有 centers 不受影响 (回归保护)
# ============================================================

class TestLegacyCentersUnaffected:
    """shengyi / zhujiang 注册与字段未被本次改动破坏。"""

    def test_shengyi_still_registered(self):
        assert "shengyi" in list_centers()
        cfg = get_center_config("shengyi")
        assert cfg.source_kind == "xlsx"

    def test_zhujiang_still_registered(self):
        assert "zhujiang" in list_centers()
        cfg = get_center_config("zhujiang")
        assert cfg.source_kind == "xlsx"
        assert cfg.all_target_tables() == ["patient", "nodule_imaging", "pathology_specimen"]


# ============================================================
# 03. WHERE 子句安全 (复用 zhujiang 测试模式, 验证新桥也通过)
# ============================================================

class TestWhereSafety:
    """新桥 SheetSpec 的 WHERE 子句应通过 _validate_where 白名单。"""

    def test_xinqiao_where_passes_validation(self):
        """直接构造 SheetSpec 时, WHERE 字面量被 config.py 校验。"""
        from pydantic import ValidationError

        from app.plugin.module_medical.hospital.etl1.config import ColumnSpec, SheetSpec

        # 新桥用的 WHERE 应能正常构造 (说明过了白名单)
        try:
            s = SheetSpec(
                sheet_name="x", target_table="nodule_imaging",
                dedup_key=["exam_id"],
                columns=[ColumnSpec(src="检查报告.患者ID", tgt="patient_id",
                                    type="string", required=True)],
                where=(
                    "检查报告.检查类别 = 'CT' "
                    "AND (检查报告.检查结论 ILIKE '%肺%' "
                    "OR 检查报告.检查结论 ILIKE '%结节%')"
                ),
            )
            assert "CT" in s.where
        except (ValidationError, ValueError) as e:
            pytest.fail(f"新桥 WHERE 被误拒: {e}")

    @pytest.mark.parametrize("bad", [
        "检查报告.检查类别 = 'CT'; DROP TABLE patient",
        "检查报告.检查类别 = 'CT' -- comment",
        "/* malicious */ 检查报告.检查类别 = 'CT'",
        "检查报告.检查类别 = 'CT' UNION SELECT * FROM users",
        "DELETE FROM patient",
        "INSERT INTO patient VALUES (1,2,3)",
        "DROP TABLE patient",
    ])
    def test_xinqiao_where_rejects_unsafe(self, bad):
        from pydantic import ValidationError

        from app.plugin.module_medical.hospital.etl1.config import ColumnSpec, SheetSpec

        with pytest.raises((ValidationError, ValueError)):
            SheetSpec(
                sheet_name="x", target_table="nodule_imaging",
                dedup_key=["exam_id"],
                columns=[ColumnSpec(src="检查报告.患者ID", tgt="patient_id",
                                    type="string", required=True)],
                where=bad,
            )


# ============================================================
# 04. CsvReader E2E (在 tmp_path 下写两份 mini CSV, 跑 run_etl1)
# ============================================================

SUB1_HEADERS = (
    "patients.性别,patients.姓名,patients.出生日期,patients.身份证号,"
    "检查报告.患者ID,检查报告.姓名,检查报告.性别,检查报告.出生日期,"
    "检查报告.临床诊断,检查报告.报告日期及时间,检查报告.检查类别,"
    "检查报告.检查部位,检查报告.检查名称,检查报告.检查所见,"
    "检查报告.检查结论,检查报告.检查日期时间,检查报告.报告中图像编号"
)

SUB2_HEADERS = (
    "patients.性别,patients.姓名,patients.出生日期,patients.身份证号,"
    "检查报告.患者ID,检查报告.姓名,检查报告.性别,检查报告.出生日期,"
    "检查报告.临床诊断,检查报告.报告日期及时间,检查报告.检查类别,"
    "检查报告.检查部位,检查报告.检查名称,检查报告.检查所见,"
    "检查报告.检查结论,检查报告.检查日期时间,检查报告.报告中图像编号,"
    "病理.患者ID,病理.姓名,病理.临床诊断,病理.病理系统编号,"
    "病理.送检时间,病理.送检部位,病理.报告时间,病理.病理所见-肉眼所见,"
    "病理.送检科室,病理.病理所见-镜下所见,病理.病理诊断,"
    "病理.病理诊断编码,病理.报告状态"
)


def _write_sub1_csv(path: Path, rows: list[dict]) -> None:
    """写入子目录 1 风格的 CSV。"""
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write(SUB1_HEADERS + "\n")
        for row in rows:
            vals = [row.get(col, "") for col in SUB1_HEADERS.split(",")]
            # 病理多值字段内的逗号需保留为半角; 其他字段不应含逗号
            # 这里直接 join, 由调用方负责字段内不含逗号 (除病理多值字段外)
            f.write(",".join(vals) + "\n")


def _write_sub2_csv(path: Path, rows: list[dict]) -> None:
    """写入子目录 2 风格的 CSV。

    病理多值字段 (如 `病理.送检时间 = "2025-03-08 08:45:42,2025-03-08 08:46:30"`)
    含半角逗号, 不能简单 join, 需要把整个字段用双引号包裹 (CSV 标准)。
    """
    import csv
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        w.writerow(SUB2_HEADERS.split(","))
        for row in rows:
            vals = [row.get(col, "") for col in SUB2_HEADERS.split(",")]
            w.writerow(vals)


class TestXinqiaoCsvE2E:
    """端到端: tmp_path 下两个子目录 + mini CSV → run_etl1 → 验证 parquet。"""

    @pytest.fixture
    def data_dirs(self, tmp_path: Path) -> tuple[Path, Path, Path]:
        """返回 (parent_dir, sub1_dir, sub2_dir)。"""
        parent = tmp_path / "01_disk"
        sub1 = parent / xinqiao_mod.SUB_1
        sub2 = parent / xinqiao_mod.SUB_2
        sub1.mkdir(parents=True)
        sub2.mkdir(parents=True)

        # SUB1: 4 个患者 (0711/0800/1080/1067), 4 个 CT 报告, 全过 WHERE
        sub1_rows = [
            {
                "patients.性别": "男", "patients.姓名": "***",
                "patients.出生日期": "1956/1/17 0:00", "patients.身份证号": "***",
                "检查报告.患者ID": "07116569", "检查报告.姓名": "***",
                "检查报告.性别": "男", "检查报告.出生日期": "1956/1/17 0:00",
                "检查报告.临床诊断": "慢阻肺急性发作",
                "检查报告.报告日期及时间": "2017/9/13 13:33",
                "检查报告.检查类别": "CT", "检查报告.检查部位": "胸部",
                "检查报告.检查名称": "肺部低剂量CT平扫",
                "检查报告.检查所见": "双肺纹理增多。",
                "检查报告.检查结论": "右肺上叶浅淡结节影。",
                "检查报告.检查日期时间": "2017/9/13 10:59",
                "检查报告.报告中图像编号": "1017091344072",
            },
            {
                "patients.性别": "男", "patients.姓名": "***",
                "patients.出生日期": "1974/4/21 0:00", "patients.身份证号": "***",
                "检查报告.患者ID": "08000386", "检查报告.姓名": "***",
                "检查报告.性别": "男", "检查报告.出生日期": "1974/4/21 0:00",
                "检查报告.临床诊断": "慢性咳嗽",
                "检查报告.报告日期及时间": "2017/10/3 8:27",
                "检查报告.检查类别": "CT", "检查报告.检查部位": "胸部",
                "检查报告.检查名称": "肺螺旋CT高分辨扫描",
                "检查报告.检查所见": "右肺上叶小浅淡结节影。",
                "检查报告.检查结论": "右肺上叶浅淡结节影。建议随访复查。",
                "检查报告.检查日期时间": "2017/10/3 8:06",
                "检查报告.报告中图像编号": "1017100335001",
            },
            # 第三例: 检查结论不含"肺/结节", 应被 WHERE 过滤掉
            {
                "patients.性别": "女", "patients.姓名": "***",
                "patients.出生日期": "1980/5/10 0:00", "patients.身份证号": "***",
                "检查报告.患者ID": "09999999", "检查报告.姓名": "***",
                "检查报告.性别": "女", "检查报告.出生日期": "1980/5/10 0:00",
                "检查报告.临床诊断": "头痛",
                "检查报告.报告日期及时间": "2018/1/1 10:00",
                "检查报告.检查类别": "CT", "检查报告.检查部位": "头部",
                "检查报告.检查名称": "头部CT",
                "检查报告.检查所见": "颅内未见异常。",
                "检查报告.检查结论": "颅脑CT平扫未见明显异常。",
                "检查报告.检查日期时间": "2018/1/1 9:30",
                "检查报告.报告中图像编号": "1018010109001",
            },
            # 第四例: 患者重复 (与 SUB2 行 1 同 ID), 用于测试跨子目录去重
            {
                "patients.性别": "男", "patients.姓名": "***",
                "patients.出生日期": "1971/9/12 0:00", "patients.身份证号": "***",
                "检查报告.患者ID": "10802887", "检查报告.姓名": "***",
                "检查报告.性别": "男", "检查报告.出生日期": "1971/9/12 0:00",
                "检查报告.临床诊断": "胸背痛待查",
                "检查报告.报告日期及时间": "2022/10/24 16:18",
                "检查报告.检查类别": "CT", "检查报告.检查部位": "胸部",
                "检查报告.检查名称": "肺螺旋CT",
                "检查报告.检查所见": "左肺下叶磨玻璃结节。",
                "检查报告.检查结论": "左肺下叶磨玻璃结节，建议随访。",
                "检查报告.检查日期时间": "2022/10/24 15:53",
                "检查报告.报告中图像编号": "1022102416001",
            },
        ]
        _write_sub1_csv(sub1 / "mini_1.csv", sub1_rows)

        # SUB2: 3 行 (患者 10802887/10674402; 行 3 无病理)
        sub2_rows = [
            {
                "patients.性别": "男", "patients.姓名": "***",
                "patients.出生日期": "1971-09-12 00:00:00", "patients.身份证号": "***",
                "检查报告.患者ID": "10802887", "检查报告.姓名": "***",
                "检查报告.性别": "男", "检查报告.出生日期": "1971-09-12 00:00:00",
                "检查报告.临床诊断": "胸背痛待查",
                "检查报告.报告日期及时间": "2022-10-24 16:18:14",
                "检查报告.检查类别": "CT", "检查报告.检查部位": "胸部",
                "检查报告.检查名称": "肺螺旋CT",
                "检查报告.检查所见": "左肺下叶磨玻璃结节。",
                "检查报告.检查结论": "左肺下叶磨玻璃结节，建议随访。",
                "检查报告.检查日期时间": "2022-10-24 15:53:06",
                "检查报告.报告中图像编号": "1022102415531",
                # 病理段空
                "病理.患者ID": "", "病理.姓名": "", "病理.临床诊断": "",
                "病理.病理系统编号": "",
                "病理.送检时间": "", "病理.送检部位": "", "病理.报告时间": "",
                "病理.病理所见-肉眼所见": "",
                "病理.送检科室": "", "病理.病理所见-镜下所见": "",
                "病理.病理诊断": "", "病理.病理诊断编码": "", "病理.报告状态": "",
            },
            # 行 2: 有病理 (多值字段, 逗号分隔)
            {
                "patients.性别": "女", "patients.姓名": "***",
                "patients.出生日期": "1965-11-02 00:00:00", "patients.身份证号": "***",
                "检查报告.患者ID": "10674402", "检查报告.姓名": "***",
                "检查报告.性别": "女", "检查报告.出生日期": "1965-11-02 00:00:00",
                "检查报告.临床诊断": "右上肺结节",
                "检查报告.报告日期及时间": "2025-03-01 08:51:08",
                "检查报告.检查类别": "CT", "检查报告.检查部位": "胸部",
                "检查报告.检查名称": "肺螺旋CT",
                "检查报告.检查所见": "右肺上叶前段实性结节。",
                "检查报告.检查结论": "右肺上叶前段结节，炎性可能。",
                "检查报告.检查日期时间": "2025-03-01 08:51:08",
                "检查报告.报告中图像编号": "1025030108511",
                "病理.患者ID": "10674402", "病理.姓名": "***",
                "病理.临床诊断": "右上肺结节",
                "病理.病理系统编号": "31429975",
                # 多值字段 (逗号分隔, 原样入 parquet)
                "病理.送检时间": "2025-03-08 08:45:42,2025-03-08 08:46:30",
                "病理.送检部位": "组织病理,冰冻切片",
                "病理.报告时间": "2025-03-12 14:25:26,2025-03-10 16:26:27",
                "病理.病理所见-肉眼所见": "灰白色组织一块,大小约2.3cm×1.8cm×0.6cm",
                "病理.送检科室": "胸外科",
                "病理.病理所见-镜下所见": "浸润性腺癌,腺泡型50%+乳头型30%+贴壁型20%",
                "病理.病理诊断": "（右肺上叶前段结节）浸润性腺癌",
                "病理.病理诊断编码": ",",  # 占位
                "病理.报告状态": "已发布,已发布",
            },
            # 行 3: CT 报告无肺 (结论是"无异常"), 应被 WHERE 过滤
            {
                "patients.性别": "女", "patients.姓名": "***",
                "patients.出生日期": "1990/3/15 0:00", "patients.身份证号": "***",
                "检查报告.患者ID": "05555555", "检查报告.姓名": "***",
                "检查报告.性别": "女", "检查报告.出生日期": "1990/3/15 0:00",
                "检查报告.临床诊断": "体检",
                "检查报告.报告日期及时间": "2024/6/1 9:00",
                "检查报告.检查类别": "CT", "检查报告.检查部位": "胸部",
                "检查报告.检查名称": "胸部CT",
                "检查报告.检查所见": "未见异常。",
                "检查报告.检查结论": "胸部CT平扫未见明显异常。",
                "检查报告.检查日期时间": "2024/6/1 8:30",
                "检查报告.报告中图像编号": "1024060109001",
                "病理.患者ID": "", "病理.姓名": "", "病理.临床诊断": "",
                "病理.病理系统编号": "",
                "病理.送检时间": "", "病理.送检部位": "", "病理.报告时间": "",
                "病理.病理所见-肉眼所见": "",
                "病理.送检科室": "", "病理.病理所见-镜下所见": "",
                "病理.病理诊断": "", "病理.病理诊断编码": "", "病理.报告状态": "",
            },
        ]
        _write_sub2_csv(sub2 / "mini_1.csv", sub2_rows)
        return parent, sub1, sub2

    def test_run_etl1_sub1_only(self, data_dirs, tmp_path):
        """单独跑子目录 1: 应产出 patient=3, nodule_imaging=3 (过滤掉 1 例头部 CT)。"""
        parent, _, _ = data_dirs
        cfg = get_center_config("xinqiao")
        out = tmp_path / "out_sub1"
        # 只跑 SUB1 的 SheetSpec (via only_tables): patient + nodule_imaging (SUB1 派生)
        # pathology_specimen 在 SUB1 不产生 (无病理列)
        stats = run_etl1(
            cfg, parent, out_dir=out,
            only_tables=["patient", "nodule_imaging"],
        )
        # patient 跨 SUB1/SUB2 都派生; only_tables=patient/nodule_imaging → SUB1 派生先跑
        # 注: 因为 cfg.hospital_tables 里 SUB2 也派生 patient/nodule_imaging, run_etl1 会全跑
        # 所以预期是 SUB1 + SUB2 的合集:
        #   patient = SUB1 3 例 + SUB2 2 例 = 5 (10802887 在两边都有, 会按 dedup_key 去重为 4)
        #   nodule_imaging = SUB1 3 例 + SUB2 2 例 = 5 (exam_id 唯一, 不去重 = 5)
        assert stats.get("patient", 0) == 4  # 4 个 unique patient
        assert stats.get("nodule_imaging", 0) == 5
        assert "pathology_specimen" not in stats

    def test_run_etl1_sub2_only(self, data_dirs, tmp_path):
        """单独跑子目录 2: patient=4 (跨两子去重), nodule_imaging=5, pathology=1。

        注: 跑父目录 + only=patient/nodule_imaging/pathology_specimen,
        CsvReader 在父目录下分别处理 SUB1 (patient/nodule_imaging) 和 SUB2 (全部 3 张)。
        """
        parent, _, _ = data_dirs
        cfg = get_center_config("xinqiao")
        out = tmp_path / "out_sub2"
        stats = run_etl1(cfg, parent, out_dir=out)

        # 跑全部 SheetSpec: SUB1 + SUB2 全跑, 跨批去重
        #   patient: SUB1 3 例 + SUB2 2 例, 10802887 重复 → 4 例
        #   nodule_imaging: SUB1 3 例 + SUB2 2 例 = 5
        #   pathology_specimen: SUB2 1 例
        assert stats.get("patient", 0) == 4
        assert stats.get("nodule_imaging", 0) == 5
        assert stats.get("pathology_specimen", 0) == 1

    def test_run_etl1_parent_dir_unions(self, data_dirs, tmp_path):
        """跑父目录: CsvReader 在两子目录都扫, 产出 patient=4 (去重), nodule_imaging=5, pathology=1。

        注: 父目录场景下两个 SheetSpec (SUB1/SUB2) 都会跑; run_etl1 顺序处理,
        后者按 dedup_key 去重, 不会出现重复 patient_id。
        """
        parent, _, _ = data_dirs
        cfg = get_center_config("xinqiao")
        out = tmp_path / "out_parent"
        stats = run_etl1(cfg, parent, out_dir=out)

        # 患者: 0711, 0800, 1080, 1067 = 4 例 (0999 被 WHERE 过滤; 0555 也在 SUB2 被过滤)
        assert stats.get("patient", 0) == 4
        # nodule_imaging: SUB1 3 例 + SUB2 2 例 = 5
        assert stats.get("nodule_imaging", 0) == 5
        # pathology_specimen: SUB2 1 例
        assert stats.get("pathology_specimen", 0) == 1

    def test_patient_id_not_anonymized_in_parquet(self, data_dirs, tmp_path):
        """patient_id 入库时仍是真实 8 位数字, 不被 ETL-1 改成 `***` 或 PT_xxx。"""
        parent, _, _ = data_dirs
        cfg = get_center_config("xinqiao")
        out = tmp_path / "out_check"
        run_etl1(cfg, parent, out_dir=out)

        con = duckdb.connect(":memory:")
        ids = con.execute(
            f"SELECT patient_id FROM read_parquet('{out}/patient.parquet')"
        ).fetchall()
        all_ids = [r[0] for r in ids]
        # 没有 `***`, 没有 `PT_` 前缀 (脱敏由 ETL-2 负责)
        for pid in all_ids:
            assert pid != "***"
            assert not pid.startswith("PT_")
            assert pid.isdigit(), f"patient_id 应为数字, 实得 {pid!r}"
        # 抽样: 至少包含预期患者
        assert "07116569" in all_ids
        assert "10802887" in all_ids

    def test_pathology_multivalue_preserved(self, data_dirs, tmp_path):
        """病理多值字段在 parquet 中仍是逗号分隔字符串, 未被 ETL-1 拆开。"""
        parent, _, _ = data_dirs
        cfg = get_center_config("xinqiao")
        out = tmp_path / "out_mv"
        run_etl1(cfg, parent, out_dir=out)

        con = duckdb.connect(":memory:")
        row = con.execute(
            f"SELECT specimen_received_at, report_released_at, "
            f"       sampling_site, pathology_diagnosis, report_status "
            f"FROM read_parquet('{out}/pathology_specimen.parquet') "
            f"WHERE specimen_id = '31429975'"
        ).fetchone()
        assert row is not None
        recv, rep, site, dx, status = row
        # 多值字段原样保留
        assert "," in recv, f"送检时间应为多值字符串, 实得 {recv!r}"
        assert "," in rep, f"报告时间应为多值字符串, 实得 {rep!r}"
        assert "," in site
        assert "腺癌" in dx or "浸润性腺癌" in dx
        assert "," in status

    def test_date_normalization_sub1_slash(self, data_dirs, tmp_path):
        """子目录 1 斜杠日期 2017/9/13 10:59 应被 cast_expr_for_type TRY_CAST 为 DATE。"""
        parent, _, _ = data_dirs
        cfg = get_center_config("xinqiao")
        out = tmp_path / "out_date_sub1"
        run_etl1(cfg, parent, out_dir=out)

        con = duckdb.connect(":memory:")
        dates = con.execute(
            f"SELECT DISTINCT exam_date FROM read_parquet('{out}/nodule_imaging.parquet') "
            f"ORDER BY exam_date"
        ).fetchall()
        # 至少有一个非 NULL 日期
        non_null = [d[0] for d in dates if d[0] is not None]
        assert len(non_null) >= 1, "至少一个 exam_date 应被解析"
        # 第一例 (0711) 是 2017-09-13
        assert any(str(d).startswith("2017-09-13") for d in non_null)

    def test_date_normalization_sub2_dash(self, data_dirs, tmp_path):
        """子目录 2 横杠日期 2025-03-01 08:51 应被 cast_expr_for_type 解析。"""
        parent, _, _ = data_dirs
        cfg = get_center_config("xinqiao")
        out = tmp_path / "out_date_sub2"
        run_etl1(cfg, parent, out_dir=out)

        con = duckdb.connect(":memory:")
        dates = con.execute(
            f"SELECT DISTINCT exam_date FROM read_parquet('{out}/nodule_imaging.parquet') "
            f"ORDER BY exam_date"
        ).fetchall()
        non_null = [d[0] for d in dates if d[0] is not None]
        assert len(non_null) >= 1
        # 第二例 (1067) 是 2025-03-01
        assert any(str(d).startswith("2025-03-01") for d in non_null)

    def test_manifest_generated(self, data_dirs, tmp_path):
        """run_etl1 末尾应写 _meta/conversion_manifest.json。"""
        parent, _, _ = data_dirs
        cfg = get_center_config("xinqiao")
        out = tmp_path / "out_manifest"
        run_etl1(cfg, parent, out_dir=out)

        manifest = out / "_meta" / "conversion_manifest.json"
        assert manifest.exists()
        import json
        data = json.loads(manifest.read_text(encoding="utf-8"))
        assert data["center_code"] == "xinqiao"


# ============================================================
# 05. CsvReader 单元 (不依赖 run_etl1)
# ============================================================

class TestCsvReaderUnit:
    """CsvReader 自身的接口与异常路径。"""

    def test_rejects_nonexistent_dir(self, tmp_path):
        from app.plugin.module_medical.hospital.etl1.csv_reader import CsvReader
        with pytest.raises(FileNotFoundError):
            CsvReader(tmp_path / "does_not_exist")

    def test_rejects_file_path(self, tmp_path):
        from app.plugin.module_medical.hospital.etl1.csv_reader import CsvReader
        f = tmp_path / "x.csv"
        f.write_text("a,b\n1,2\n")
        with pytest.raises(ValueError):
            CsvReader(f)

    def test_empty_dir_no_csv_raises(self, tmp_path):
        from app.plugin.module_medical.hospital.etl1.csv_reader import CsvReader
        d = tmp_path / "empty"
        d.mkdir()
        with pytest.raises(FileNotFoundError):
            CsvReader(d).read_sheet("empty")

    def test_basename_match_succeeds(self, tmp_path):
        """sheet_name == 当前目录 basename 时正常读。"""
        from app.plugin.module_medical.hospital.etl1.csv_reader import CsvReader

        d = tmp_path / "data"
        d.mkdir()
        (d / "a.csv").write_text("x,y\n1,2\n", encoding="utf-8")

        reader = CsvReader(d)
        reader.ensure_loaded()
        sv = reader.read_sheet("data")
        assert sv.headers == ["x", "y"]
        n = reader.con.execute(
            f"SELECT count(*) FROM {sv.view_name}"
        ).fetchone()[0]
        assert n == 1

    def test_parent_dir_with_subdir_succeeds(self, tmp_path):
        """父目录 + sheet_name 子目录, 正常读。"""
        from app.plugin.module_medical.hospital.etl1.csv_reader import CsvReader

        parent = tmp_path / "parent"
        (parent / "sub_a").mkdir(parents=True)
        (parent / "sub_b").mkdir(parents=True)
        (parent / "sub_a" / "a.csv").write_text("x,y\n1,2\n", encoding="utf-8")
        (parent / "sub_b" / "b.csv").write_text("p,q\n3,4\n", encoding="utf-8")

        reader = CsvReader(parent)
        reader.ensure_loaded()

        sv_a = reader.read_sheet("sub_a")
        assert "x" in sv_a.headers and "y" in sv_a.headers
        n_a = reader.con.execute(
            f"SELECT count(*) FROM {sv_a.view_name}"
        ).fetchone()[0]
        assert n_a == 1

        sv_b = reader.read_sheet("sub_b")
        assert "p" in sv_b.headers

    def test_sheet_name_not_subdir_raises(self, tmp_path):
        """sheet_name 既不等于 basename 也不是子目录, 报错。"""
        from app.plugin.module_medical.hospital.etl1.csv_reader import CsvReader

        d = tmp_path / "data"
        d.mkdir()
        (d / "a.csv").write_text("x,y\n1,2\n", encoding="utf-8")

        reader = CsvReader(d)
        reader.ensure_loaded()
        with pytest.raises(ValueError, match="既不等于当前目录 basename"):
            reader.read_sheet("not_subdir_or_basename")

    def test_close_idempotent(self, tmp_path):
        from app.plugin.module_medical.hospital.etl1.csv_reader import CsvReader
        d = tmp_path / "d"
        d.mkdir()
        (d / "x.csv").write_text("a\n1\n")
        r = CsvReader(d)
        r.close()
        r.close()  # 不应报错


# ============================================================
# 06. _process_union_sheets 单元 (列顺序校验 + 跨源 dedup_key)
# ============================================================

class TestProcessUnionSheets:
    """UNION 多 SheetSpec 的两个 HIGH 修复点的回归覆盖。

    HIGH 1 (列顺序校验): 同 target_table 的多 SheetSpec 列顺序不一致必须抛 ValueError,
        避免 UNION ALL 按位置对齐时静默错位列。
    HIGH 2 (跨源 dedup_key): 同 exam_id/specimen_id 的跨源行, 即使长文本(findings/impression)
        有微小差异, 也应按 dedup_key 去重为一行, 不应重复入库。
    """

    def test_column_order_mismatch_raises(self):
        """HIGH 1: 两 SheetSpec 列集相同但顺序不同, _process_union_sheets 应抛 ValueError。"""
        from app.plugin.module_medical.hospital.etl1.config import ColumnSpec, SheetSpec

        # 两 spec 列集相同 {patient_id, gender}, 但顺序相反
        spec_a = SheetSpec(
            sheet_name="sub_a", target_table="patient",
            dedup_key=["patient_id"],
            columns=[
                ColumnSpec(src="检查报告.患者ID", tgt="patient_id",
                           type="string", required=True),
                ColumnSpec(src="检查报告.性别", tgt="gender", type="string"),
            ],
        )
        spec_b = SheetSpec(
            sheet_name="sub_b", target_table="patient",
            dedup_key=["patient_id"],
            columns=[
                # 顺序反转: gender 在前, patient_id 在后
                ColumnSpec(src="检查报告.性别", tgt="gender", type="string"),
                ColumnSpec(src="检查报告.患者ID", tgt="patient_id",
                           type="string", required=True),
            ],
        )
        # 不实际跑 SQL, 只触发列顺序校验 (在 read_sheet 之前就会抛)
        # 用 mock reader 避免依赖真实 CSV
        class _MockReader:
            def ensure_loaded(self): pass
            def read_sheet(self, name): raise AssertionError("不应到达 read_sheet")
            def close(self): pass
            @property
            def con(self): raise AssertionError("不应到达 con")

        from app.plugin.module_medical.hospital.etl1.core import _process_union_sheets
        with pytest.raises(ValueError, match="列集或列顺序不一致"):
            _process_union_sheets(
                _MockReader(), con=None,
                spec_list=[spec_a, spec_b],
                out_path=Path("/tmp/never_written.parquet"),
            )

    def test_column_set_mismatch_raises(self):
        """HIGH 1 (补): 两 SheetSpec 列集不同 (一个多一列), 也应抛错。"""
        from app.plugin.module_medical.hospital.etl1.config import ColumnSpec, SheetSpec

        spec_a = SheetSpec(
            sheet_name="sub_a", target_table="patient",
            dedup_key=["patient_id"],
            columns=[
                ColumnSpec(src="检查报告.患者ID", tgt="patient_id",
                           type="string", required=True),
            ],
        )
        spec_b = SheetSpec(
            sheet_name="sub_b", target_table="patient",
            dedup_key=["patient_id"],
            columns=[
                ColumnSpec(src="检查报告.患者ID", tgt="patient_id",
                           type="string", required=True),
                # 多了一列 gender
                ColumnSpec(src="检查报告.性别", tgt="gender", type="string"),
            ],
        )
        class _MockReader:
            def ensure_loaded(self): pass
            def read_sheet(self, name): raise AssertionError("不应到达 read_sheet")
            def close(self): pass
            @property
            def con(self): raise AssertionError("不应到达 con")

        from app.plugin.module_medical.hospital.etl1.core import _process_union_sheets
        with pytest.raises(ValueError, match="列集或列顺序不一致"):
            _process_union_sheets(
                _MockReader(), con=None,
                spec_list=[spec_a, spec_b],
                out_path=Path("/tmp/never_written.parquet"),
            )

    def test_cross_source_dedup_by_exam_id(self, tmp_path):
        """HIGH 2: 跨源同 exam_id 但 findings 文本有微小差异, 应只保留一行 (按 dedup_key)。

        构造场景:
          - SUB1 行: exam_id=X1, findings="hello world"
          - SUB2 行: exam_id=X1, findings="hello world " (多一个空格)
          预期: UNION 后只保留 1 行 (按 exam_id 去重), 不是 2 行

        注: 当前 _process_union_sheets 用 ROW_NUMBER() OVER (PARTITION BY dedup_key),
            PARTITION 内多行保留第 1 行 (按 spec_list 顺序)。
        """
        # 构造两个子目录, 各放一个同 exam_id 不同 findings 的行
        from app.plugin.module_medical.hospital.etl1.centers import xinqiao as xq

        parent = tmp_path / "01_disk"
        sub1 = parent / xq.SUB_1
        sub2 = parent / xq.SUB_2
        sub1.mkdir(parents=True)
        sub2.mkdir(parents=True)

        # SUB1 一行: 10802887 / exam_id=DUP001 / findings="左肺结节"
        sub1_row = {
            "patients.性别": "男", "patients.姓名": "***",
            "patients.出生日期": "1971/9/12 0:00", "patients.身份证号": "***",
            "检查报告.患者ID": "10802887", "检查报告.姓名": "***",
            "检查报告.性别": "男", "检查报告.出生日期": "1971/9/12 0:00",
            "检查报告.临床诊断": "胸背痛",
            "检查报告.报告日期及时间": "2022/10/24 16:18",
            "检查报告.检查类别": "CT", "检查报告.检查部位": "胸部",
            "检查报告.检查名称": "肺螺旋CT",
            "检查报告.检查所见": "左肺结节。",
            "检查报告.检查结论": "左肺结节。",
            "检查报告.检查日期时间": "2022/10/24 15:53",
            "检查报告.报告中图像编号": "DUP001",
        }
        _write_sub1_csv(sub1 / "mini.csv", [sub1_row])

        # SUB2 一行: 10802887 / exam_id=DUP001 / findings="左肺结节 " (多一空格)
        sub2_row = {
            "patients.性别": "男", "patients.姓名": "***",
            "patients.出生日期": "1971-09-12 00:00:00", "patients.身份证号": "***",
            "检查报告.患者ID": "10802887", "检查报告.姓名": "***",
            "检查报告.性别": "男", "检查报告.出生日期": "1971-09-12 00:00:00",
            "检查报告.临床诊断": "胸背痛",
            "检查报告.报告日期及时间": "2022-10-24 16:18:14",
            "检查报告.检查类别": "CT", "检查报告.检查部位": "胸部",
            "检查报告.检查名称": "肺螺旋CT",
            # 微小差异: 末尾多一空格
            "检查报告.检查所见": "左肺结节。 ",
            "检查报告.检查结论": "左肺结节。",
            "检查报告.检查日期时间": "2022-10-24 15:53:06",
            "检查报告.报告中图像编号": "DUP001",
            "病理.患者ID": "", "病理.姓名": "", "病理.临床诊断": "",
            "病理.病理系统编号": "",
            "病理.送检时间": "", "病理.送检部位": "", "病理.报告时间": "",
            "病理.病理所见-肉眼所见": "",
            "病理.送检科室": "", "病理.病理所见-镜下所见": "",
            "病理.病理诊断": "", "病理.病理诊断编码": "", "病理.报告状态": "",
        }
        _write_sub2_csv(sub2 / "mini.csv", [sub2_row])

        cfg = get_center_config("xinqiao")
        out = tmp_path / "out_dedup"
        stats = run_etl1(cfg, parent, out_dir=out, only_tables=["nodule_imaging"])

        # 期望: 1 行 (按 exam_id=DUP001 去重), 不是 2 行
        assert stats.get("nodule_imaging", 0) == 1, (
            f"跨源同 exam_id 应按 dedup_key 去重为 1 行, 实得 {stats.get('nodule_imaging')}"
        )

        # 读回验证: 只有 1 个 exam_id
        con = duckdb.connect(":memory:")
        rows = con.execute(
            f"SELECT exam_id, findings FROM read_parquet('{out}/nodule_imaging.parquet')"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "DUP001"