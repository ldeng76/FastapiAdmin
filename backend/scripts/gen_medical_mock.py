"""生成多模态医学数据 mock（parquet），用于「医学数据」模块展示。

依据 docs/unified_table_schema.md、shengyi_tables.md、zhujiang_xinqiao_tables.md
的字段定义造虚拟患者数据，严格对齐字段名/类型，输出到 backend/data/medical/。

用法:
    uv run python scripts/gen_medical_mock.py

数据为虚构病例，仅供展示，非真实临床数据。
"""

from __future__ import annotations

import random
from datetime import date, datetime
from pathlib import Path

import duckdb
import pandas as pd

# 固定随机种子，保证多次运行结果一致（展示稳定）
random.seed(20260701)

# backend/ 根目录
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "medical"

# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #

GENDER = ["男", "女"]
ETHNICITY = ["汉族", "壮族", "回族", "满族", "苗族", "土家族"]
NATIVE_PLACE = ["广东广州", "广东深圳", "湖南长沙", "广西南宁", "四川成都", "江西南昌", "河南郑州"]
ABO = ["A", "B", "AB", "O"]
RH = ["阳性", "阴性"]
SMOKING = ["从不", "既往", "现在"]
DEPT = ["肺一科", "胸外科", "呼吸内科", "肿瘤科", "放疗科"]
VISIT_CATEGORY = ["住院", "门诊", "急诊"]
PAYMENT = ["医保", "东莞医保", "广州医保", "自费", "非医保"]
DRUG_NAMES = ["吉非替尼片", "奥希替尼片", "克唑替尼胶囊", "培美曲塞二钠", "顺铂注射液", "地塞米松注射液"]
TEST_NAMES = ["血常规", "肝功能", "肾功能", "肿瘤标志物", "凝血功能"]
LAB_ITEMS = [
    ("白细胞计数", 4.0, 10.0, "10^9/L"),
    ("血红蛋白", 115, 150, "g/L"),
    ("癌胚抗原(CEA)", 0, 5.0, "ng/mL"),
    ("细胞角蛋白19片段", 0.5, 3.3, "ng/mL"),
    ("谷丙转氨酶", 7, 40, "U/L"),
]
EXAM_TYPES = ["CT", "MRI", "DR", "PET-CT"]
BODY_PARTS = ["胸部", "颅脑", "腹部", "上腹部"]
DENSITY = ["纯磨玻璃", "部分实性", "实性", "钙化"]
NODULE_LOC = ["右肺上叶尖段", "右肺中叶内侧段", "右肺下叶后基底段", "左肺上叶尖后段", "左肺下叶背段"]
GENES = ["EGFR", "KRAS", "ALK", "ROS1", "BRAF", "HER2", "MET", "TP53"]
HISTOLOGY = ["腺癌", "鳞癌", "腺鳞癌", "大细胞癌"]
SPECIMEN_TYPE = ["肺活检", "手术切除", "穿刺"]


def _d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _dt(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def _rand_date(start: date, end: date) -> date:
    span = (end - start).days
    return start.fromordinal(start.toordinal() + random.randint(0, max(span, 1)))


# --------------------------------------------------------------------------- #
# 省医数据
# --------------------------------------------------------------------------- #

def gen_shengyi(n: int = 12) -> None:
    """省医（Shengyi）：含 visit_record / lab_result / imaging_report 等独有表 + 4 张统一表。"""
    out_dir = DATA_DIR / "shengyi"
    out_dir.mkdir(parents=True, exist_ok=True)

    patient_rows, visit_rows, drug_rows, lab_rows, img_rows = [], [], [], [], []
    path_rows, surg_rows, gene_rows = [], [], []

    for i in range(1, n + 1):
        pid = f"SY{10000 + i}"
        birth = _rand_date(date(1945, 1, 1), date(1985, 12, 31))
        gender = random.choice(GENDER)
        visit_count = random.randint(1, 6)

        patient_rows.append({
            "patient_id": pid,
            "source_center": "省医",
            "gender": gender,
            "birth_date": birth,
            "ethnicity": random.choice(ETHNICITY),
            "native_place": random.choice(NATIVE_PLACE),
            "abo_blood_type": random.choice(ABO),
            "rh_blood_type": random.choice(RH),
            "smoking_status": None,
            "first_nodule_date": None,
            "visit_counts": {
                "outpatient_count": random.randint(0, 5),
                "inpatient_count": visit_count,
                "visit_count": visit_count,
            },
            "demographics": None,
            "medical_history": None,
        })

        # 就诊记录（每次就诊一行）
        for v in range(1, visit_count + 1):
            vid = f"{pid}V{v}"
            admit = _rand_date(date(2008, 1, 1), date(2024, 12, 31))
            los = random.randint(1, 20)
            discharge = date.fromordinal(admit.toordinal() + los)
            visit_age = (admit - birth).days // 365
            visit_rows.append({
                "patient_id": pid,
                "visit_id": vid,
                "visit_category": random.choice(VISIT_CATEGORY),
                "admission_time": _dt(admit.isoformat() + " 10:30:00"),
                "discharge_date": discharge,
                "admission_dept": random.choice(DEPT),
                "discharge_dept": random.choice(DEPT),
                "length_of_stay": los,
                "payment_method": random.choice(PAYMENT),
                "visit_age": float(visit_age),
                "inpatient_no": f"P{100000 + i * 100 + v}",
                "outpatient_no": f"O{200000 + i * 100 + v}",
                "diagnoses": [{
                    "code": "C34.101",
                    "name": "肺上叶恶性肿瘤",
                    "type": "主要诊断" if v == 1 else "其他诊断",
                    "outcome": random.choice(["好转", "治愈", "未愈"]),
                    "is_primary": v == 1,
                }],
            })

            # 药物医嘱
            for _ in range(random.randint(1, 3)):
                drug_rows.append({
                    "patient_id": pid,
                    "visit_id": vid,
                    "order_source": random.choice(["inpatient", "outpatient"]),
                    "order_time": _dt(admit.isoformat() + f" {9+v}:00:00"),
                    "drug_generic_name": random.choice(DRUG_NAMES),
                    "order_detail": {
                        "duration_type": random.choice(["长期", "临时"]),
                        "dose": str(random.randint(1, 500)),
                        "dose_unit": "mg",
                        "frequency": "QD",
                        "route": "口服",
                    },
                })

            # 检验子项
            for tname in random.sample(TEST_NAMES, k=random.randint(1, 3)):
                for item_name, lo, hi, unit in LAB_ITEMS:
                    val = round(random.uniform(lo * 0.5, hi * 1.5), 2)
                    lab_rows.append({
                        "patient_id": pid,
                        "visit_id": vid,
                        "report_id": f"{vid}R{random.randint(1,99)}",
                        "test_name": tname,
                        "item_name": item_name,
                        "item_result": str(val),
                        "item_result_value": val,
                        "item_unit": unit,
                        "ref_lower": lo,
                        "ref_upper": hi,
                        "collection_time": _dt(admit.isoformat() + " 08:00:00"),
                        "test_detail": {"overall_result": str(val)},
                    })

        # 影像学报告
        for _ in range(random.randint(1, 3)):
            img_rows.append({
                "patient_id": pid,
                "visit_id": f"{pid}V1",
                "report_id": f"{pid}IMG{random.randint(1,99)}",
                "exam_type": random.choice(EXAM_TYPES),
                "exam_body_part": random.choice(BODY_PARTS),
                "exam_date": _rand_date(date(2015, 1, 1), date(2024, 12, 31)),
                "exam_item": random.choice(["胸部平扫", "胸部高分辨CT", "胸部增强"]),
                "exam_detail": {
                    "type_code": "CT",
                    "exam_method": random.choice(["平扫", "平扫+增强"]),
                    "findings": "右肺上叶可见一枚结节，边缘可见浅分叶。",
                    "impression": "右肺上叶结节，建议复查。",
                },
            })

        # 病理标本（统一表）
        path_rows.append({
            "patient_id": pid,
            "visit_id": f"{pid}V1",
            "specimen_id": f"{pid}P1",
            "submission_date": None,
            "report_date": _rand_date(date(2015, 1, 1), date(2024, 12, 31)),
            "specimen_type": None,
            "sampling_site": None,
            "specimen_name": random.choice(SPECIMEN_TYPE),
            "exam_name": "病理检查",
            "exam_type": "常规HE",
            "exam_date": _rand_date(date(2015, 1, 1), date(2024, 12, 31)),
            "histology_class": None,
            "pathology_diagnosis": f"{random.choice(HISTOLOGY)}，分化中等",
            "tumor_total_size_mm": round(random.uniform(5, 35), 1),
            "exam_detail": {
                "gross_findings": "灰白组织一块，大小1.5×1.0×0.8cm。",
                "microscopic_findings": "肿瘤细胞呈腺管样排列。",
                "immunohistochemistry": "TTF-1(+) NapsinA(+)",
            },
            "specimen_meta": None,
            "adenocarcinoma_subtypes": None,
            "tumor_measurement": None,
            "high_risk_factors": None,
            "staging": None,
        })

        # 手术记录（统一表）
        surg_rows.append({
            "patient_id": pid,
            "visit_id": f"{pid}V1",
            "surgery_date": _rand_date(date(2015, 1, 1), date(2024, 12, 31)),
            "procedure_name": random.choice(["胸腔镜下肺叶切除术", "肺段切除术", "肺楔形切除术"]),
            "resection_scope": None,
            "surgical_approach": None,
            "procedure_detail": {
                "procedure_level": random.choice(["二级", "三级"]),
                "incision_healing": random.choice(["甲/甲", "乙/甲"]),
                "anesthesia_method": random.choice(["全麻", "局麻"]),
                "surgeon": "李主任",
            },
        })

        # 基因检测（统一表，省医以 variant_type 区分）
        for vtype in random.sample(["snv", "cnv", "drug_ref"], k=random.randint(1, 3)):
            gene_rows.append({
                "patient_id": pid,
                "visit_id": f"{pid}V1",
                "test_id": f"{pid}G{vtype}",
                "test_date": None,
                "variant_type": vtype,
                "test_method": None,
                "test_meta": {
                    "gene_name": random.choice(GENES),
                    "sample_source": "手术组织",
                    "method": "NGS panel",
                },
                "variant_result": {
                    "variant_desc": random.choice(["L858R", "19del", "T790M", "扩增", "野生型"]),
                    "vaf_pct": round(random.uniform(0, 60), 1),
                    "clinical_significance": random.choice(["致病性", "可能致病", "意义未明"]),
                    "drug_reference": "一代TKI敏感" if vtype == "drug_ref" else "",
                },
                "driver_mutations": None,
                "immune_markers": None,
            })

    _write(out_dir / "patient.parquet", patient_rows)
    _write(out_dir / "visit_record.parquet", visit_rows)
    _write(out_dir / "drug_order.parquet", drug_rows)
    _write(out_dir / "lab_result.parquet", lab_rows)
    _write(out_dir / "imaging_report.parquet", img_rows)
    _write(out_dir / "pathology_specimen.parquet", path_rows)
    _write(out_dir / "surgery_record.parquet", surg_rows)
    _write(out_dir / "genetic_test.parquet", gene_rows)
    print(f"[shengyi] patients={n} visit_records={len(visit_rows)} drug_orders={len(drug_rows)} "
          f"lab_results={len(lab_rows)} imaging_reports={len(img_rows)} "
          f"pathology={len(path_rows)} surgery={len(surg_rows)} genetic={len(gene_rows)}")


# --------------------------------------------------------------------------- #
# 珠江-新桥数据
# --------------------------------------------------------------------------- #

def gen_zhujiang_xinqiao(n: int = 8) -> None:
    """珠江-新桥：含 nodule_imaging / ihc_result / follow_up 独有表 + 4 张统一表。"""
    out_dir = DATA_DIR / "zhujiang_xinqiao"
    out_dir.mkdir(parents=True, exist_ok=True)

    patient_rows, nodule_rows, ihc_rows, follow_rows = [], [], [], []
    path_rows, surg_rows, gene_rows = [], [], []

    for i in range(1, n + 1):
        pid = f"ZJ{20000 + i}"
        birth = _rand_date(date(1948, 1, 1), date(1980, 12, 31))
        gender = random.choice(GENDER)
        first_nodule = _rand_date(date(2018, 1, 1), date(2024, 12, 31))

        patient_rows.append({
            "patient_id": pid,
            "source_center": random.choice(["珠江", "新桥"]),
            "gender": gender,
            "birth_date": birth,
            "ethnicity": None,
            "native_place": None,
            "abo_blood_type": None,
            "rh_blood_type": None,
            "smoking_status": random.choice(SMOKING),
            "first_nodule_date": first_nodule,
            "visit_counts": None,
            "demographics": {"bmi": round(random.uniform(18, 28), 1)},
            "medical_history": {
                "smoking_pack_years": random.randint(0, 40),
                "family_lung_cancer": random.choice([True, False]),
                "prior_malignancy": "无",
                "comorbid_copd": random.choice([True, False]),
                "discovery_route": random.choice(["体检", "症状就诊", "其他病随诊偶发"]),
            },
        })

        # 结节影像（独有）
        n_ct = random.randint(1, 3)
        for c in range(n_ct):
            exam_id = f"{pid}CT{c + 1}"
            exam_date = _rand_date(first_nodule, date(2025, 6, 30))
            n_nodule = random.randint(1, 2)
            for nn in range(1, n_nodule + 1):
                nodule_rows.append({
                    "patient_id": pid,
                    "exam_id": exam_id,
                    "exam_date": exam_date,
                    "exam_type": "CT",
                    "nodule_no": f"N{nn}",
                    "nodule_location": random.choice(NODULE_LOC),
                    "long_diameter": round(random.uniform(3, 25), 1),
                    "density_type": random.choice(DENSITY),
                    "exam_meta": {
                        "exam_name": "肺螺旋CT高分辨",
                        "contrast": random.choice(["平扫", "增强"]),
                        "slice_thickness_mm": 1.0,
                    },
                    "nodule_morphology": {
                        "subpleural": random.choice([True, False]),
                        "margin": random.choice(["光滑", "分叶", "毛刺"]),
                        "signs": random.sample(["毛刺", "胸膜牵拉", "空泡征"], k=random.randint(0, 2)),
                    },
                    "nodule_quantitative": {
                        "short_diameter_mm": round(random.uniform(2, 15), 1),
                        "mean_ct_value_hu": random.randint(-600, 50),
                        "lung_rads": random.choice(["2", "3", "4A", "4B"]),
                    },
                    "follow_up_comparison": {"vs_prior": random.choice(["无变化", "增大", "缩小", "新发"])},
                })

        # 免疫组化（独有）
        ihc_rows.append({
            "patient_id": pid,
            "specimen_id": f"{pid}P1",
            "ki67_pct": round(random.uniform(3, 50), 1),
            "markers": {
                "pdl1_tps_pct": random.choice([0, 1, 10, 40, 80]),
                "pdl1_clone": "22C3",
                "ttf1": "阳性",
                "napsina": "阳性",
                "p40": "阴性",
            },
        })

        # 随访（独有）
        follow_rows.append({
            "patient_id": pid,
            "last_followup_date": _rand_date(date(2023, 1, 1), date(2026, 6, 30)),
            "recurrence": random.choice(["是", "否"]),
            "survival_status": random.choice(["存活", "存活", "死亡", "失访"]),
            "treatment_detail": {
                "adjuvant_therapy": random.choice(["无", "化疗", "靶向", "免疫"]),
                "first_line_regimen": random.choice(["奥希替尼", "培美曲塞+顺铂", "无"]),
            },
            "recurrence_detail": {
                "recurrence_date": _rand_date(date(2024, 1, 1), date(2025, 12, 31)).isoformat() if random.random() > 0.5 else None,
                "recurrence_site": random.choice(["局部", "区域(纵隔)", "远处"]),
            },
        })

        # 病理标本（统一表）
        path_rows.append({
            "patient_id": pid,
            "visit_id": None,
            "specimen_id": f"{pid}P1",
            "submission_date": _rand_date(date(2020, 1, 1), date(2024, 12, 31)),
            "report_date": _rand_date(date(2020, 1, 1), date(2024, 12, 31)),
            "specimen_type": random.choice(SPECIMEN_TYPE),
            "sampling_site": random.choice(NODULE_LOC),
            "specimen_name": None,
            "exam_name": None,
            "exam_type": None,
            "exam_date": None,
            "histology_class": random.choice(HISTOLOGY),
            "pathology_diagnosis": None,
            "tumor_total_size_mm": round(random.uniform(5, 30), 1),
            "exam_detail": None,
            "specimen_meta": {"frozen": "石蜡", "multi_nodule_same_report": False},
            "adenocarcinoma_subtypes": {
                "lepidic_pct": random.randint(0, 40),
                "acinar_pct": random.randint(20, 60),
                "micropapillary_pct": random.randint(0, 10),
                "solid_pct": random.randint(0, 10),
                "major_subtype": "腺泡",
            },
            "tumor_measurement": {"differentiation": random.choice(["高", "中", "低"]), "invasive_size_mm": round(random.uniform(2, 15), 1)},
            "high_risk_factors": {
                "stas": random.choice([True, False]),
                "lymphovascular_invasion": random.choice([True, False]),
                "pleural_invasion": random.choice(["PL0", "PL1", "PL2"]),
            },
            "staging": {
                "margin": "R0",
                "lymph_nodes_positive_total": f"{random.randint(0,3)}/{random.randint(10,20)}",
                "pt": random.choice(["pT1a(mi)", "pT1b", "pT2a"]),
                "pn": "pN0",
                "staging_edition": "AJCC 第8版",
            },
        })

        # 手术记录（统一表）
        surg_rows.append({
            "patient_id": pid,
            "visit_id": None,
            "surgery_date": _rand_date(date(2020, 1, 1), date(2024, 12, 31)),
            "procedure_name": random.choice(["胸腔镜下肺叶切除术", "肺段切除术"]),
            "resection_scope": random.choice(["楔形切除", "段切除", "叶切除"]),
            "surgical_approach": random.choice(["VATS", "机器人辅助", "开胸"]),
            "procedure_detail": {
                "icd9cm3_code": "32.4101",
                "ln_dissection_strategy": random.choice(["系统性", "采样"]),
                "duration_minutes": random.randint(90, 300),
                "blood_loss_ml": random.randint(20, 200),
                "los_days": random.randint(4, 14),
            },
        })

        # 基因检测（统一表，珠江以驱动基因维度组织）
        gene_rows.append({
            "patient_id": pid,
            "visit_id": None,
            "test_id": f"{pid}G1",
            "test_date": _rand_date(date(2020, 1, 1), date(2024, 12, 31)),
            "variant_type": None,
            "test_method": random.choice(["NGS panel", "ARMS-PCR"]),
            "test_meta": {
                "sample_source": random.choice(["手术组织", "穿刺组织", "血浆ctDNA"]),
                "panel_size": random.choice(["小panel(<50)", "中(50-200)", "大(>200)"]),
            },
            "variant_result": None,
            "driver_mutations": {
                "egfr": random.choice(["L858R", "19del", "阴性"]),
                "egfr_vaf_pct": round(random.uniform(0, 50), 1),
                "kras": random.choice(["阴性", "G12C", "G12D"]),
                "alk_fusion": "阴性",
                "ros1_fusion": "阴性",
                "braf": "阴性",
                "tp53": random.choice(["阴性", "突变(R175H)"]),
            },
            "immune_markers": {
                "tmb_per_mb": round(random.uniform(1, 15), 1),
                "tmb_level": random.choice(["低", "中", "高"]),
                "msi": "MSS",
            },
        })

    _write(out_dir / "patient.parquet", patient_rows)
    _write(out_dir / "nodule_imaging.parquet", nodule_rows)
    _write(out_dir / "ihc_result.parquet", ihc_rows)
    _write(out_dir / "follow_up.parquet", follow_rows)
    _write(out_dir / "pathology_specimen.parquet", path_rows)
    _write(out_dir / "surgery_record.parquet", surg_rows)
    _write(out_dir / "genetic_test.parquet", gene_rows)
    print(f"[zhujiang_xinqiao] patients={n} nodules={len(nodule_rows)} ihc={len(ihc_rows)} "
          f"follow_up={len(follow_rows)} pathology={len(path_rows)} surgery={len(surg_rows)} genetic={len(gene_rows)}")


# --------------------------------------------------------------------------- #
# 输出
# --------------------------------------------------------------------------- #

def _write(path: Path, rows: list[dict]) -> None:
    """用 DuckDB 写 parquet（pandas 仅作中间载体，含 dict 列会自动转为 parquet struct）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    try:
        if rows:
            df = pd.DataFrame(rows)
            con.register("_medical_t", df)
        else:
            # 空表：建一个最小 schema 的空表占位，保证可被 read_parquet 读到
            con.execute("CREATE TABLE _medical_t (_placeholder VARCHAR)")
        # 覆盖写入（FORMAT PARQUET, OVERWRITE）
        con.execute(f"COPY _medical_t TO '{path.as_posix()}' (FORMAT PARQUET, OVERWRITE_OR_IGNORE TRUE)")
    finally:
        con.close()


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    gen_shengyi(12)
    gen_zhujiang_xinqiao(8)
    print(f"\n✅ mock 数据已生成到 {DATA_DIR}")


if __name__ == "__main__":
    main()
