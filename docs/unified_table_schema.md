# 多中心临床数据统一表定义

## 设计原则

1. **核心字段取并集** — 两家医院的核心字段合并为统一表结构，缺的一方填 null。
2. **同概念不同精度，只保留最精确的字段** — 如省医 `birth_date`（精确到日）与珠江-新桥 `birth_year`（年份），统一表只保留 `birth_date`，珠江-新桥的出生年转为 `YYYY-01-01` 格式。
3. **JSON 扩展列各自独立** — 不强制统一，各医院按自身数据特点定义结构和内容。
4. **有对应关系的表做并集，各自独有的表保持独立** — 如 patient、pathology_specimen 两家都有的表统一核心字段；省医独有的 visit_record、珠江-新桥独有的 nodule_imaging 保持独立。

## 表清单

| 表名 | 类型 | 说明 |
|------|------|------|
| **patient** | 统一表 | 患者基本信息（省医 + 珠江-新桥） |
| **pathology_specimen** | 统一表 | 病理标本（省医 + 珠江-新桥） |
| **surgery_record** | 统一表 | 手术记录（省医 + 珠江-新桥） |
| **genetic_test** | 统一表 | 基因检测（省医 + 珠江-新桥） |
| visit_record | 省医独有 | 就诊记录 |
| drug_order | 省医独有 | 药物医嘱 |
| non_drug_order | 省医独有 | 非药物医嘱 |
| lab_result | 省医独有 | 检验报告 |
| imaging_report | 省医独有 | 影像学报告 |
| ultrasound_report | 省医独有 | 超声诊断报告 |
| ecg_report | 省医独有 | 心电图报告 |
| nodule_imaging | 珠江-新桥独有 | 结节影像 |
| ihc_result | 珠江-新桥独有 | 免疫组化结果 |
| follow_up | 珠江-新桥独有 | 随访结局 |

## 目录结构

```
data/
├── shengyi/
│   ├── patient.parquet              # 统一表
│   ├── pathology_specimen.parquet   # 统一表
│   ├── surgery_record.parquet       # 统一表
│   ├── genetic_test.parquet         # 统一表
│   ├── visit_record.parquet         # 省医独有
│   ├── drug_order.parquet
│   ├── non_drug_order.parquet
│   ├── lab_result.parquet
│   ├── imaging_report.parquet
│   ├── ultrasound_report.parquet
│   └── ecg_report.parquet
│
└── zhujiang_xinqiao/
    ├── patient.parquet              # 统一表
    ├── pathology_specimen.parquet   # 统一表
    ├── surgery_record.parquet       # 统一表
    ├── genetic_test.parquet         # 统一表
    ├── nodule_imaging.parquet       # 珠江-新桥独有
    ├── ihc_result.parquet
    └── follow_up.parquet
```

---

## 统一表定义

### 1. patient — 患者基本信息

粒度：每患者一行。

#### 核心字段（两家并集）

| 字段名 | 类型 | 说明 | 省医 | 珠江-新桥 |
|--------|------|------|:----:|:---------:|
| patient_id | string | 患者编号（院内脱敏ID） | ✓ | ✓ |
| source_center | string | 来源中心（省医/珠江/新桥/...） | null | ✓ |
| gender | string | 性别（男/女） | ✓ | ✓ |
| birth_date | date | 出生日期 | ✓ | ✓* |
| ethnicity | string | 民族 | ✓ | null |
| native_place | string | 籍贯 | ✓ | null |
| abo_blood_type | string | ABO血型 | ✓ | null |
| rh_blood_type | string | RH血型 | ✓ | null |
| smoking_status | string | 吸烟状态（从不/既往/现在） | null | ✓ |
| first_nodule_date | date | 首次发现结节日期 | null | ✓ |

> \* 珠江-新桥原始数据为 `birth_year`（年份），转换时填充为 `YYYY-01-01`。
> 省医原始数据为 `birth_date`（精确到日），直接使用。
> 按精度优先原则，只保留 `birth_date`。

#### JSON 扩展字段

| 字段名 | 类型 | 说明 | 省医 | 珠江-新桥 |
|--------|------|------|:----:|:---------:|
| visit_counts | json | 就诊次数统计 | ✓ | — |
| demographics | json | 人口学扩展 | — | ✓ |
| medical_history | json | 既往病史 | — | ✓ |

#### 省医 visit_counts 结构

```jsonc
{
  "outpatient_count": 0,    // 门诊总次数
  "inpatient_count": 6,     // 住院总次数
  "visit_count": 6          // 就诊总次数
}
```

#### 珠江-新桥 demographics 结构

```jsonc
{
  "bmi": 22.5   // BMI（若有）
}
```

#### 珠江-新桥 medical_history 结构

```jsonc
{
  "smoking_pack_years": 20,                    // 吸烟包年（若吸烟）
  "family_lung_cancer": false,                 // 一级亲属肺癌史
  "family_other_cancer": false,                // 一级亲属其他癌史
  "family_other_cancer_type": "",              // 是则填瘤种
  "prior_malignancy": "无",                    // 既往恶性肿瘤史（无/有(瘤种)）
  "comorbid_copd": false,                      // 合并COPD/慢支
  "comorbid_old_tb": false,                    // 合并陈旧性肺结核
  "discovery_route": "体检"                     // 发现途径（体检/症状就诊/其他病随诊偶发）
}
```

#### 转换说明

| 原始字段 | 来源 | 转换规则 |
|---------|------|---------|
| birth_year | 珠江-新桥 | 转为 date 类型：`{year}-01-01` |
| birth_date | 省医 | 直接使用，无需转换 |
| source_center | 省医 | 填入固定值 `"省医"` |
| smoking_status | 省医 | 填 null |
| first_nodule_date | 省医 | 填 null |
| ethnicity / native_place / abo_blood_type / rh_blood_type | 珠江-新桥 | 填 null |

---

### 2. pathology_specimen — 病理标本

粒度：每份病理标本/报告一行。

> 省医原始表名为 pathology_report，统一后更名为 pathology_specimen，与珠江-新桥对齐。

#### 核心字段（两家并集）

| 字段名 | 类型 | 说明 | 省医 | 珠江-新桥 |
|--------|------|------|:----:|:---------:|
| patient_id | string | 患者编号 | ✓ | ✓ |
| visit_id | string | 就诊编号 | ✓ | null |
| specimen_id | string | 标本号 / 报告编号 | ✓ | ✓ |
| submission_date | date | 送检日期 | null | ✓ |
| report_date | date | 报告日期 | null | ✓ |
| specimen_type | string | 标本类型 | null | ✓ |
| sampling_site | string | 取材部位 | null | ✓ |
| specimen_name | string | 标本名称 | ✓ | null |
| exam_name | string | 检查名称 | ✓ | null |
| exam_type | string | 检查类型 | ✓ | null |
| exam_date | date | 检查日期 | ✓ | null |
| histology_class | string | 组织学大类 | null | ✓ |
| pathology_diagnosis | string | 病理诊断 | ✓ | null |
| tumor_total_size_mm | float | 肿瘤总大小(mm) | null | ✓ |

> 省医的 `report_id` 对应统一表的 `specimen_id`。
> 省医缺少结构化的组织学分类（histology_class），其 `pathology_diagnosis` 为自由文本，包含类似信息。

#### JSON 扩展字段

| 字段名 | 类型 | 说明 | 省医 | 珠江-新桥 |
|--------|------|------|:----:|:---------:|
| exam_detail | json | 检查详情（肉眼/镜下所见等） | ✓ | — |
| specimen_meta | json | 标本元数据 | — | ✓ |
| adenocarcinoma_subtypes | json | 腺癌亚型百分比 | — | ✓ |
| tumor_measurement | json | 肿瘤测量 | — | ✓ |
| high_risk_factors | json | 高危因素 | — | ✓ |
| staging | json | 病理分期 | — | ✓ |

#### 省医 exam_detail 结构

```jsonc
{
  "request_id": "SQ001",                  // 申请单号
  "gross_findings": "灰白组织一块...",     // 肉眼所见
  "microscopic_findings": "肿瘤细胞...",   // 镜下所见
  "immunohistochemistry": "TTF-1(+)",      // 免疫组化
  "exam_method": "常规HE",                 // 检查方法名称
  "special_markers": "",                   // 特殊检查标志
  "remarks": ""                            // 备注
}
```

#### 珠江-新桥 specimen_meta 结构

```jsonc
{
  "frozen": "石蜡",                   // 是否冰冻（冰冻/石蜡）
  "paired_specimen_id": "",           // 配对标本号（冰冻↔石蜡同次手术配对）
  "multi_nodule_same_report": false   // 是否多结节同份报告
}
```

#### 珠江-新桥 adenocarcinoma_subtypes 结构

```jsonc
{
  "lepidic_pct": 20,         // 贴壁型(%)
  "acinar_pct": 50,          // 腺泡型(%)
  "papillary_pct": 20,       // 乳头型(%)
  "micropapillary_pct": 5,   // 微乳头型(%)(高危)
  "solid_pct": 5,            // 实性型(%)(高危)
  "major_subtype": "腺泡",   // 主要亚型
  "rare_subtype": ""         // 罕见亚型（黏液腺癌/胶样/肠型/胎儿型/混合型）
}
```

#### 珠江-新桥 tumor_measurement 结构

```jsonc
{
  "differentiation": "中",     // 分化程度（高/中/低/未分化）
  "invasive_size_mm": 8        // 浸润成分大小(mm)（MIA/IA区分关键）
}
```

#### 珠江-新桥 high_risk_factors 结构

```jsonc
{
  "stas": false,                       // 气腔播散(STAS)
  "lymphovascular_invasion": false,    // 脉管/淋巴管侵犯(LVI)
  "perineural_invasion": false,        // 神经侵犯(PNI)
  "pleural_invasion": "PL0"            // 胸膜侵犯（PL0/PL1/PL2/PL3，高危: ≥PL1）
}
```

#### 珠江-新桥 staging 结构

```jsonc
{
  "margin": "R0",                      // 切缘（R0/R1/R2）
  "lymph_nodes_positive_total": "0/15", // 淋巴结(阳性/总数)
  "sampled_ln_groups": "2,4,7,10,11,12", // 送检淋巴结组别（IASLC编号）
  "positive_ln_groups": "",              // 阳性淋巴结组别
  "pt": "pT1a(mi)",                     // 病理 pT
  "pn": "pN0",                          // 病理 pN
  "pm": "pM0",                          // 病理 pM
  "staging_edition": "AJCC 第8版"       // 分期版本
}
```

#### 转换说明

| 原始字段 | 来源 | 转换规则 |
|---------|------|---------|
| report_id | 省医 | 映射为 `specimen_id` |
| visit_id | 省医 | 直接使用 |
| visit_id | 珠江-新桥 | 填 null |
| exam_date | 省医 | 直接使用 |
| submission_date / report_date | 珠江-新桥 | 直接使用 |

---

### 3. surgery_record — 手术记录

粒度：每次手术一行。

> 省医原始数据中，手术信息嵌套在住院病案首页的 `surgeries` JSON 数组内，每条手术拆出为独立行。
> 珠江-新桥已有独立的 surgery_record 表。

#### 核心字段（两家并集）

| 字段名 | 类型 | 说明 | 省医 | 珠江-新桥 |
|--------|------|------|:----:|:---------:|
| patient_id | string | 患者编号 | ✓ | ✓ |
| visit_id | string | 就诊编号 | ✓ | null |
| surgery_date | date | 手术日期 | ✓ | ✓ |
| procedure_name | string | 手术及操作名称 / 术式名 | ✓ | ✓ |
| resection_scope | string | 切除范围 | null | ✓ |
| surgical_approach | string | 手术入路 | null | ✓ |

#### JSON 扩展字段

| 字段名 | 类型 | 说明 | 省医 | 珠江-新桥 |
|--------|------|------|:----:|:---------:|
| procedure_detail | json | 手术详情 | ✓ | ✓ |

#### 省医 procedure_detail 结构

```jsonc
{
  "original_patient_id": "2967004",     // 原始患者编号
  "case_no": "",                        // 病案序号
  "procedure_level": "二级",            // 手术等级
  "incision_healing": "甲/甲",          // 切口愈合等级
  "anesthesia_method": "局麻",          // 麻醉方式
  "surgeon": "张三",                    // 术者
  "anesthesiologist": "",               // 麻醉医生
  "assistant_1": "",                    // Ⅰ助
  "assistant_2": ""                     // Ⅱ助
}
```

#### 珠江-新桥 procedure_detail 结构

```jsonc
{
  "icd9cm3_code": "32.4101",              // ICD9-CM3编码
  "ln_dissection_strategy": "系统性",     // 淋巴结清扫策略（系统性/采样/未做）
  "dissected_ln_groups": "2,4,7,10,11",   // 清扫淋巴结组别
  "duration_minutes": 180,                // 手术时长(分钟)
  "asa_score": "P2",                      // ASA评分（P1/P2/P3/P4）
  "blood_loss_ml": 50,                    // 出血量(ml)
  "complications": "无",                  // 术后并发症（无/漏气/肺炎/心律失常/...）
  "los_days": 9                           // 住院天数
}
```

#### 转换说明

| 原始数据 | 来源 | 转换规则 |
|---------|------|---------|
| inpatient_front_page.surgeries[] | 省医 | 数组中每个元素拆为独立行 |
| surgery_date | 省医 | 从 surgeries[].procedure_date 提取 |
| visit_id | 省医 | 从所在就诊记录继承 |

---

### 4. genetic_test — 基因检测

粒度：每份基因检测报告/变异记录一行。

> 省医包含 6 个子类别（拷贝数变异、用药参考、融合基因、插入缺失突变、其他变异、单核苷酸变异），以 `variant_type` 区分。
> 珠江-新桥以驱动基因维度组织，每行汇总一份检测报告的全部基因结果。

#### 核心字段（两家并集）

| 字段名 | 类型 | 说明 | 省医 | 珠江-新桥 |
|--------|------|------|:----:|:---------:|
| patient_id | string | 患者编号 | ✓ | ✓ |
| visit_id | string | 就诊编号 | ✓ | null |
| test_id | string | 检测唯一号 / 报告编号 | ✓ | ✓ |
| test_date | date | 检测日期 | null | ✓ |
| variant_type | string | 变异类型 | ✓ | null |
| test_method | string | 检测方法 | null | ✓ |

> 省医的 `report_id` 对应统一表的 `test_id`。
> variant_type 取值：cnv / drug_ref / fusion / indel / other / snv（仅省医使用）。

#### JSON 扩展字段

| 字段名 | 类型 | 说明 | 省医 | 珠江-新桥 |
|--------|------|------|:----:|:---------:|
| test_meta | json | 检测元数据 | ✓ | ✓ |
| variant_result | json | 变异结果 | ✓ | — |
| driver_mutations | json | 驱动基因突变 | — | ✓ |
| immune_markers | json | 免疫相关标志物 | — | ✓ |

#### test_meta 结构（两家共用键名，内容各自填充）

```jsonc
{
  // 省医填充
  "gene_name": "EGFR",               // 基因名称
  "sample_source": "手术组织",        // 检测样本来源
  "method": "NGS panel",             // 检测方法

  // 珠江-新桥填充
  "sample_source": "手术组织",        // 检测样本来源（手术组织/穿刺组织/血浆ctDNA/胸水）
  "panel_size": "小panel(<50)"        // panel基因数（单基因/小panel(<50)/中(50-200)/大(>200)/全外显子）
}
```

#### 省医 variant_result 结构

```jsonc
{
  "variant_desc": "L858R",               // 变异描述
  "vaf_pct": 35.0,                       // 变异丰度(%)
  "clinical_significance": "致病性",      // 临床意义
  "drug_reference": ""                    // 用药参考信息（仅 drug_ref 类型）
}
```

#### 珠江-新桥 driver_mutations 结构

```jsonc
{
  "egfr": "L858R",                       // EGFR（阴性/L858R/19del/T790M/20ins/G719X/其他）
  "egfr_vaf_pct": 35,                    // EGFR 丰度(VAF%)
  "kras": "阴性",                        // KRAS（阴性/G12C/G12D/G12V/G12A/G13D/其他）
  "kras_vaf_pct": null,                  // KRAS 丰度(VAF%)
  "alk_fusion": "阴性",                  // ALK融合（阴性/阳性(伴侣)）
  "ros1_fusion": "阴性",                 // ROS1融合
  "ret_fusion": "阴性",                  // RET融合
  "ntrk_fusion": "阴性",                 // NTRK融合
  "braf": "阴性",                        // BRAF（阴性/V600E/其他）
  "her2": "阴性",                        // HER2(ERBB2)（阴性/突变(20ins)/扩增）
  "met": "阴性",                         // MET（阴性/14外显子跳跃/扩增）
  "tp53": "阴性",                        // TP53（阴性/突变(具体位点)）
  "other_variants": ""                   // 其他临床意义变异（PIK3CA/STK11/KEAP1/SMARCA4等）
}
```

#### 珠江-新桥 immune_markers 结构

```jsonc
{
  "tmb_per_mb": 6.5,                     // TMB(突变/Mb)
  "tmb_level": "中",                     // TMB分级（低<6/中6-10/高≥10）
  "msi": "MSS",                          // MSI（MSS/MSI-H/MSI-L）
  "mmr": "pMMR"                          // MMR（pMMR/dMMR）
}
```

#### 转换说明

| 原始字段 | 来源 | 转换规则 |
|---------|------|---------|
| report_id | 省医 | 映射为 `test_id` |
| visit_id | 省医 | 直接使用 |
| test_id | 珠江-新桥 | 直接使用 |
| test_date | 省医 | 填 null（原始数据中暂无此字段） |
| variant_type | 珠江-新桥 | 填 null |

---

## 医院独有表定义

以下表仅存在于对应医院的数据目录中，无需跨院对齐。详细定义见各医院独立文档。

### 省医独有表

> 完整定义见 [shengyi_tables.md](./shengyi_tables.md)

| 表名 | 粒度 | 核心字段概要 |
|------|------|-------------|
| visit_record | 每患者每次就诊 | patient_id, visit_id, visit_category, admission_time, discharge_date, admission_dept, discharge_dept, length_of_stay, payment_method, visit_age, inpatient_no, outpatient_no |
| drug_order | 每条药物医嘱 | patient_id, visit_id, order_source, order_time, drug_generic_name |
| non_drug_order | 每条非药物医嘱 | patient_id, visit_id, order_name, order_start_time, order_stop_time |
| lab_result | 每条检验子项 | patient_id, visit_id, report_id, test_name, item_name, item_result, item_result_value, item_unit, ref_lower, ref_upper, collection_time |
| imaging_report | 每次影像检查 | patient_id, visit_id, report_id, exam_type, exam_body_part, exam_date, exam_item |
| ultrasound_report | 每次超声检查 | patient_id, visit_id, report_id, exam_name, body_part, exam_date, ultrasound_finding |
| ecg_report | 每次心电图 | patient_id, visit_id, report_id, exam_date |

### 珠江-新桥独有表

> 完整定义见 [zhujiang_xinqiao_tables.md](./zhujiang_xinqiao_tables.md)

| 表名 | 粒度 | 核心字段概要 |
|------|------|-------------|
| nodule_imaging | 一次CT中的一个结节 | patient_id, exam_id, exam_date, exam_type, nodule_no, nodule_location, long_diameter, density_type |
| ihc_result | 每份标本的免疫组化 | patient_id, specimen_id, ki67_pct |
| follow_up | 每患者随访 | patient_id, last_followup_date, recurrence, survival_status |

---

## 表间关系

### 省医

```
patient (1) ──── (N) visit_record
  │                    │
  │                    ├── (N) drug_order
  │                    ├── (N) non_drug_order
  │                    ├── (N) lab_result
  │                    ├── (N) imaging_report
  │                    ├── (N) ultrasound_report
  │                    ├── (N) ecg_report
  │                    └── (N) surgery_record
  │
  ├── (N) pathology_specimen
  └── (N) genetic_test
```

通过 `patient_id` 关联患者，就诊级别的表额外通过 `patient_id + visit_id` 关联具体就诊。

### 珠江-新桥

```
patient (1) ──── (N) nodule_imaging       [patient_id]
  │
  ├── (N) pathology_specimen              [patient_id]
  │         └── (1) ihc_result            [specimen_id]
  │
  ├── (N) genetic_test                    [patient_id]
  │
  ├── (N) surgery_record                  [patient_id]
  │
  └── (1..N) follow_up                   [patient_id]
```

通过 `patient_id` 关联患者。`ihc_result` 与 `pathology_specimen` 通过 `specimen_id` 关联到具体标本。

### 跨院查询

统一表（patient、pathology_specimen、surgery_record、genetic_test）可直接跨院 UNION 查询，核心字段名和类型完全一致。医院独有表不参与跨院 UNION，仅在单院分析时使用。
