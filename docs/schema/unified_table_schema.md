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
| **diagnosis** | 省医独有 | 诊断事件（统一来自病案首页与诊疗过程的诊断流） |
| **medical_history** | 省医独有 | 病史记录（主诉/现病史/既往史/个人史/婚育史/家族史） |
| **progress_note** | 省医独有 | 病程记录文档（自由文本段落） |
| **nursing_observation** | 省医独有 | 护理测量子项（体温/脉搏/呼吸/血压/出入量等） |
| **icu_observation** | 省医独有 | ICU 护理记录观察项 |
| **anesthesia_event** | 省医独有 | 麻醉事件（术中用药 + 子项观察） |

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
│   ├── ecg_report.parquet
│   ├── diagnosis.parquet            # 省医独有 — 新增
│   ├── medical_history.parquet      # 省医独有 — 新增
│   ├── progress_note.parquet        # 省医独有 — 新增
│   ├── nursing_observation.parquet  # 省医独有 — 新增
│   ├── icu_observation.parquet      # 省医独有 — 新增
│   └── anesthesia_event.parquet     # 省医独有 — 新增
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
| diagnosis | 每条诊断事件 | patient_id, visit_id, diagnosis_source, diagnosis_type, diagnosis_code, diagnosis_name, diagnosis_date, is_primary_diagnosis |
| medical_history | 每就诊一份病史记录 | patient_id, visit_id, visit_ordinal, record_date, chief_complaint, present_illness, past_history, personal_history, marriage_history, family_history, source_document |
| progress_note | 每段病程文档 | patient_id, visit_id, visit_ordinal, note_id, note_date, note_type, content |
| nursing_observation | 每条护理测量子项 | patient_id, visit_id, record_id, item_id, item_code, item_name, item_value, item_unit, measurement_time, measurement_method |
| icu_observation | 每条 ICU 观察项 | patient_id, visit_id, visit_ordinal, department, admission_date, icu_in_time, icu_out_time, weight_kg, record_date, item_name, item_result, item_result_value |
| anesthesia_event | 每条麻醉事件 | patient_id, visit_id, visit_ordinal, session_id, event_type, event_time, drug_name, drug_dose, observation_name, observation_value, observation_unit |

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

参见下文 “扩展后的关系图” 一节（已包含本节新增 6 张表）。

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

---

## 省医追加表定义（基于 Excel 数据扩展）

> 适用范围：广东人民医院本次导出的 `搜索导出.xlsx`。下述 6 张表覆盖了原 schema 未纳入的诊断、病史、病程、护理测量、ICU 记录、麻醉事件等数据。所有表只服务单院分析，不参与跨院 UNION。

### 通用约定

- 数据源字符串中所有时间字段以 `YYYY-MM-DD[ HH:MM:SS]` 编码，需转换为 `date`/`timestamp`。
- 第二列 `当前命中就诊次数/命中就诊总次数` 形如 `m/n`，原始表中有多张工作表不携带 `就诊编号` 列。新增表统一保留 `visit_ordinal` 字段（文本，格式 `m/n`），并通过 ETL 在加载阶段用 `(patient_id, m)` 反查 `visit_record.visit_id` 填充 `visit_id`；若患者在 `visit_record` 中无对应记录，`visit_id` 置 null，但 `visit_ordinal` 与 `patient_id` 仍保留以便溯源。
- 自由文本类字段统一使用 `TEXT`（CLOB 等价），包含 `\r\n` / `\n` 的字段在加载时统一为 `\n`，长度上限不做截断。

#### Excel 表头格式（2026-07-19 ETL-1 实施时核实）

每张 sheet 都是**单行表头**（行 1），数据从行 2 开始：

- A 列固定为 `患者编号`（短名）
- B 列固定为 `当前命中就诊次数/命中就诊总次数`（短名，即 `m/n`）
- C 列起为带全路径的字段名，如 `非隐私信息.就诊.住院病案首页.诊断.诊断编码`

> ⚠️ 早先分析脚本 `analyze_xlsx_raw.py` 报告的 `header_rows=10` 是误报——因为所有 cell 都是 inline string，"全字符串行"判定永远通过，脚本跑满了 10 行 look-ahead。它输出的 `data_rows` 因此也比真实值少 9 行。**实际数据行 = `row_count - 1`**。
>
> ETL-1 (`backend/.../etl1/`) 用 duckdb `read_xlsx(..., header=true, all_varchar=true)` 已正确处理：1 行表头 + 数据从第 2 行起，2026-07-19 全量跑通 16 张表共 3,207,305 行，与 `row_count-1` 完全对齐。
>
> 另：部分表头有尾随空格（如 `非隐私信息.就诊.就诊基本信息.医疗付款方式 `），ETL 匹配时需 `.strip()`。

### 5. diagnosis — 诊断事件

**粒度**：每条诊断一行。  
**数据源**：

```text
非隐私信息.就诊.住院病案首页.诊断   (35 列，21,308 行)
非隐私信息.就诊.诊断                 (7  列，280,929 行)
```

两份数据建模为同一张表，通过 `diagnosis_source` 区分来源，并通过冗余字段 `diagnosis_front_page_meta` JSON 收纳仅首页诊断拥有的扩展结构。

#### 核心字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| patient_id | string | 患者编号 |
| visit_id | string | 就诊编号（首页诊断可直接从患者住院结算病案首页继承；visit 诊断来自诊疗事件） |
| visit_ordinal | string | 原始 `m/n` 序号 |
| diagnosis_source | string | 数据来源：`front_page`（病案首页） / `visit`（诊疗过程） |
| diagnosis_no | int | 诊断次序（首页：1..N；visit：null 或次序号） |
| diagnosis_code | string | 诊断编码（ICD-10 / 院内码，例如 `C34.001`、`M80410/3`、`R91.x02`） |
| diagnosis_name | string | 诊断名称 |
| diagnosis_type | string | 诊断类型：`主要诊断` / `次要诊断` / `其他` |
| diagnosis_outcome | string | 诊断归转情况（首页）：`治愈` / `好转` / `未愈` / `死亡` / `其他` / null |
| admission_condition | string | 入院病情（首页）：`有` / `无` / `临床未确定` / `情况不明` / null |
| diagnosis_date | timestamp | 诊断日期（visit 诊断明确填写；首页诊断可能为空） |
| is_primary_diagnosis | bool | 是否主要诊断（visit 诊断的 `是否主要诊断` 字段：`是`/`否`） |
| diagnosis_category | string | 诊断类别（visit）：`出院诊断` / `出院主要诊断` / `入院主要诊断` / `入院诊断` / `初步诊断` / 其他 |

#### JSON 扩展

| 字段名 | 来源 | 说明 |
|--------|------|------|
| diagnosis_front_page_meta | `front_page` | 仅首页诊断有值，承载 35 列中的扩展结构，详见下表 |

##### diagnosis_front_page_meta 结构

```jsonc
{
  "admission_route": "门诊",
  "admission_status": "一般",
  "discharge_method": "医嘱离院",
  "readmission_31d_planned": false,
  "readmission_31d_purpose": "...",
  "inpatient_count": 1,
  "rh_blood_type_frontpage": "阳",
  "abo_blood_type_frontpage": "O",
  "transfusion_units": {
    "whole_blood": 0,
    "plasma": 0,
    "platelet": 0,
    "rbc": 0,
    "other": 0
  },
  "newborn_birth_weight_g": null,
  "newborn_admit_weight_g": null,
  "birthplace": "广东省揭阳市",
  "is_postop_complication": false,
  "cranial_injury_observation": {
    "post_admit_minutes": 0,
    "post_admit_hours": 0,
    "post_admit_days": 0,
    "pre_admit_minutes": 0,
    "pre_admit_hours": 0,
    "pre_admit_days": 0
  },
  "rescue_count": 0,
  "rescue_success_count": 0,
  "primary_nursing_days": 0,
  "secondary_nursing_days": 0
}
```

> 设计取舍：首页诊断的扩展字段对 `visit` 诊断恒为 null。保持单表能够避免 JOIN，符合“通过 `diagnosis_source` 字段区分”这一选择。

#### 转换说明

| 原始字段 | 来源 | 转换规则 |
|---------|------|---------|
| `非隐私信息.就诊.住院病案首页.诊断.诊断编码` | 病案首页 | → `diagnosis_code` |
| `非隐私信息.就诊.住院病案首页.诊断.诊断名称` | 病案首页 | → `diagnosis_name` |
| `非隐私信息.就诊.住院病案首页.诊断.诊断类型` | 病案首页 | → `diagnosis_type`（"主要诊断"/"次要诊断"/"其他"） |
| `非隐私信息.就诊.住院病案首页.诊断.诊断归转情况` | 病案首页 | → `diagnosis_outcome` |
| `非隐私信息.就诊.住院病案首页.诊断.诊断日期` | 病案首页 | → `diagnosis_date` |
| `非隐私信息.就诊.住院病案首页.诊断.入院病情` | 病案首页 | → `admission_condition` |
| `非隐私信息.就诊.诊断.诊断编码/名称/日期` | visit | → 上述同名字段 |
| `非隐私信息.就诊.诊断.是否主要诊断` | visit | → `is_primary_diagnosis`（`是`→true） |
| `非隐私信息.就诊.诊断.诊断类别` | visit | → `diagnosis_category` |
| 当前命中就诊次数/命中就诊总次数 | 两表 | → `visit_ordinal` |

---

### 6. medical_history — 病史记录

**粒度**：每就诊一份病史（同一 (patient_id, m/n) 仅一行）。  
**数据源**：`非隐私信息.就诊.病史`（10 列，73,180 行）。

#### 核心字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| patient_id | string | 患者编号 |
| visit_id | string | 就诊编号（ETL 时由 `visit_ordinal` 反查） |
| visit_ordinal | string | 原始 `m/n` 序号 |
| record_date | timestamp | 记录日期（可能为空） |
| chief_complaint | text | 主诉 |
| present_illness | text | 现病史（含 `\r\n`，加载时规范化为 `\n`） |
| past_history | text | 既往史 |
| personal_history | text | 个人史（吸烟、饮酒等） |
| marriage_history | text | 婚育史 |
| family_history | text | 家族史 |
| source_document | string | 数据来源（如 `门诊病历`、`住院病历`、`首次病程` 等） |

#### 转换说明

| 原始字段 | 转换规则 |
|---------|---------|
| `非隐私信息.就诊.病史.{主诉/现病史/既往史/个人史/婚育史/家族史}` | → 同名字段 |
| `非隐私信息.就诊.病史.记录日期` | → `record_date`（datetime） |
| `非隐私信息.就诊.病史.数据来源` | → `source_document` |

> 注意：73,180 行远超患者数（≈ 1,007）与就诊总数目，原因是每次门诊都可能产生一份；同一 `(patient_id, m)` 出现多次时按 `(record_date, source_document)` 顺序聚合到一行或将多次记录额外扁平化到一张 `medical_history_event` 表，由实现侧选择。当前 schema 按"一就诊一份"建模。

---

### 7. progress_note — 病程记录文档

**粒度**：每段病程文档一行（每条 `(patient_id, visit_id, note_id)` 一行）。  
**数据源**：`非隐私信息.就诊.病程记录文档`（5 列，240,170 行）。

#### 核心字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| patient_id | string | 患者编号 |
| visit_id | string | 就诊编号（由 `visit_ordinal` 反查） |
| visit_ordinal | string | 原始 `m/n` 序号 |
| note_id | string | 文档编号（若原始未提供，采用哈希 `(patient_id, visit_ordinal, note_type, note_date)` 合成） |
| note_date | timestamp | 记录日期（可能为空） |
| note_type | string | 文档类型，例如 `门诊病历.辅助检查`、`门诊病历.处理`、`首次病程记录`、`日常病程记录`、`查房记录` 等 |
| content | text | 文档正文（CLOB，含 `\r\n`，长度可达上千字符） |

#### 转换说明

| 原始字段 | 转换规则 |
|---------|---------|
| `非隐私信息.就诊.病程记录文档.文档内容` | → `content` |
| `非隐私信息.就诊.病程记录文档.记录日期` | → `note_date` |
| `非隐私信息.就诊.病程记录文档.文档类型` | → `note_type` |

> 抽样显示约 19% 的行 `note_date` 为空，应保留为 null；约 9 行是精确重复，可在 ETL 时按 `(patient_id, visit_id, note_type, note_date, content)` 去重。

---

### 8. nursing_observation — 护理测量子项

**粒度**：每条护理测量子项一行（每条 `<uuid>_指标_seq` 一行）。  
**数据源**：`非隐私信息.就诊.护理记录.测量子项`（21 列，341,430 行）。  
表头同时存在父级（行 1–9）与子级（行 10–21）的字段，存在列冗余。

#### 核心字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| patient_id | string | 患者编号 |
| visit_id | string | 就诊编号（直接取 `非隐私信息.就诊.护理记录.就诊编号`） |
| record_id | string | 护理记录编号（UUID） |
| item_id | string | 子项编号，格式 `<uuid>_<指标>_<seq>`，作为天然主键 |
| item_code | string | 项目编码（可能为空） |
| item_name | string | 项目名称（如 `呼吸`、`脉搏`、`体温`、`血压`、`大便次`） |
| item_category | string | 项目类型 / 护理类型（如 `基础护理`、`专科护理`） |
| item_value | decimal | 测量结果数值 |
| item_unit | string | 测量单位 |
| measurement_time | timestamp | 测量时间 |
| measurement_method | string | 测量方法（如 `呼吸辅助措施`、`血压辅助`） |
| nurse_signature | string | 护士签名（可选保留） |
| department | string | 住院科室 |
| record_date | timestamp | 护理记录日期（父级字段，冗余） |

#### JSON 扩展

| 字段名 | 说明 |
|--------|------|
| nursing_meta | 用于收纳父级冗余字段：`原始患者编号`、`诊断`等 |

#### 转换说明

| 原始字段 | 转换规则 |
|---------|---------|
| `非隐私信息.就诊.护理记录.就诊编号` | → `visit_id` |
| `非隐私信息.就诊.护理记录.护理记录编号` | → `record_id` |
| `非隐私信息.就诊.护理记录.测量子项.子项编号` | → `item_id` |
| `非隐私信息.就诊.护理记录.测量子项.项目编码/名称/类型` | → `item_code/name/category` |
| `非隐私信息.就诊.护理记录.测量子项.测量结果数值/单位/时间/方法` | → 对应核心字段 |

> 注意：抽样的 `item_value` 为 0 / 0.0 的占比极少，但参考上下限字段大量为空，目标表不保留参考范围（按需在 ETL 阶段推入 `nursing_meta`）。

---

### 9. icu_observation — ICU 护理记录观察项

**粒度**：每条 ICU 观察项一行（每条 `(patient_id, icu_in_time, item_name, record_date)` 一行）。  
**数据源**：`非隐私信息.就诊.ICU护理记录.记录详细信息`（13 列，8,869 行；不含 ICU 子表时，作为同一院 ICU 数据全量；可视为"ICU 病房的护理数据子集"）。

#### 核心字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| patient_id | string | 患者编号 |
| visit_id | string | 就诊编号（由 `visit_ordinal` 反查） |
| visit_ordinal | string | 原始 `m/n` 序号 |
| department | string | 住院科室（如 `肺二科`、`ICU-1`） |
| admission_date | timestamp | 入院日期 |
| icu_in_time | timestamp | 入 ICU 时间 |
| icu_out_time | timestamp | 出 ICU 时间 |
| weight_kg | decimal | 体重（kg） |
| diagnosis_summary | string | 诊断名称（来自父记录） |
| observation_id | string | 观测项 ID（哈希 `(patient_id, icu_in_time, record_date, item_name)`） |
| record_date | timestamp | 记录日期 |
| item_name | string | 项目（如 `SPO2`、`脉搏`、`呼吸`、`血压(收缩)`） |
| item_result | string | 结果（文本） |
| item_result_value | decimal | 结果数值（可空） |

#### 转换说明

| 原始字段 | 转换规则 |
|---------|---------|
| `非隐私信息.就诊.ICU护理记录.{住院科室,诊断名称,入院日期,入ICU时间,出ICU时间,体重}` | → 同名核心字段 |
| `非隐私信息.就诊.ICU护理记录.记录详细信息.{记录日期,项目,结果,结果_数值}` | → `record_date / item_name / item_result / item_result_value` |

---

### 10. anesthesia_event — 麻醉事件

**粒度**：每条麻醉事件一行（药物记录或观察项各占一行）。  
**数据源**：

```text
非隐私信息.就诊.麻醉信息.用药记录   (13 列，6,086 行，event_type=medication)
非隐私信息.就诊.麻醉信息.子项记录   (15 列，45,489 行，event_type=observation)
```

两张表通过共同的麻醉会话字段（`入室时间`、`出室时间`、`麻醉开始/结束`、`ASA分级`、`实施手术名称`、`手术开始/结束`）形成同会话，按 `(patient_id, visit_ordinal, 入室时间)` 关联。

#### 核心字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| patient_id | string | 患者编号 |
| visit_id | string | 就诊编号（由 `visit_ordinal` 反查） |
| visit_ordinal | string | 原始 `m/n` 序号 |
| session_id | string | 麻醉会话 ID（哈希 `(patient_id, 入室时间)`），一张麻醉记录展开为多行 |
| event_type | string | `medication` / `observation` |
| event_time | timestamp | 事件时间（用药时取自父级入室/出室/麻醉开始/术中时机；观察时取自 `子项记录.记录日期`） |
| asa_level | string | ASA 分级：`Ⅰ级` / `Ⅱ级` / `Ⅲ级` / `Ⅳ级` |
| surgery_name | string | 实施手术名称 |
| surgery_start_time | timestamp | 手术开始时间 |
| surgery_end_time | timestamp | 手术结束时间 |
| anesthesia_start_time | timestamp | 麻醉开始时间 |
| anesthesia_end_time | timestamp | 麻醉结束时间 |
| room_in_time | timestamp | 入室时间 |
| room_out_time | timestamp | 出室时间 |
| weight_kg | decimal | 体重（kg），可能为空 |
| drug_name | string | 术中用药名称（仅 medication） |
| drug_dose | decimal | 术中用药剂量（仅 medication） |
| observation_name | string | 观察项目描述（仅 observation） |
| observation_value | string | 观察项目值（仅 observation） |
| observation_unit | string | 观察项目单位（仅 observation） |

#### JSON 扩展

| 字段名 | 说明 |
|--------|------|
| anesthesia_extra | 药房 / 批次等未在核心字段表达的元信息 |

#### 转换说明

| 原始字段 | 转换规则 |
|---------|---------|
| 父级字段（入室时间 … 手术结束时间，6 项） | → `room_in_time / room_out_time / anesthesia_start_time / anesthesia_end_time / surgery_start_time / surgery_end_time` |
| `非隐私信息.就诊.麻醉信息.ASA分级` | → `asa_level` |
| `非隐私信息.就诊.麻醉信息.实施手术名称` | → `surgery_name` |
| `非隐私信息.就诊.麻醉信息.体重（kg）` | → `weight_kg` |
| `非隐私信息.就诊.麻醉信息.用药记录.术中用药名称/剂量` | → 仅 medication 行：`drug_name / drug_dose` |
| `非隐私信息.就诊.麻醉信息.子项记录.{记录日期,项目描述,项目值,项目单位}` | → 仅 observation 行：`event_time / observation_name / observation_value / observation_unit` |
| 当前命中就诊次数/命中就诊总次数 | → `visit_ordinal` |

> 抽样显示 6,086 用药记录中有 15 条完全重复、45,489 子项记录中有 9 条完全重复；ETL 应通过 `(session_id, drug_name, drug_dose)` / `(session_id, observation_name, observation_value, observation_unit)` 去重后加载。

---

## 扩展后的关系图

### 省医（追加表后）

```
patient (1) ──── (N) visit_record
  │                    │
  │                    ├── (N) drug_order
  │                    ├── (N) non_drug_order
  │                    ├── (N) lab_result
  │                    ├── (N) imaging_report
  │                    ├── (N) ultrasound_report
  │                    ├── (N) ecg_report
  │                    ├── (N) surgery_record
  │                    ├── (N) diagnosis              [patient_id + visit_id]
  │                    ├── (N) medical_history        [patient_id + visit_id]
  │                    ├── (N) progress_note          [patient_id + visit_id]
  │                    ├── (N) anesthesia_event       [patient_id + visit_id]
  │                    │
  ├── (N) pathology_specimen
  ├── (N) genetic_test
  ├── (N) nursing_observation            [patient_id + visit_id + record_id + item_id]
  └── (N) icu_observation                [patient_id + visit_id + session_id]
```

> `nursing_observation` 不直接挂 `visit_record`（视情况而定，部分原始记录可能跨多个 visit），但业务上仍以 `patient_id` 为顶层关联键，`visit_id` 可空。

### 关键观察

1. **冗余列**：护理、ICU 麻醉原始表中均出现父子级重复（父字段在子行反复出现）。统一表不保存冗余，父级字段由 `visit_record` / `surgery_record` 承担，只保留子项粒度。
2. **visit_id 缺失恢复**：5 类表（病史、病程、麻醉、ICU、首页诊断等）原始不含 `就诊编号` 列，只能通过 `(patient_id, 当前命中就诊次数)` 反查 `visit_record.visit_id`。ETL 必须执行一次反查并缓存 `(patient_id, m) → visit_id` 的字典。
3. **长文本**：病史、诊断描述、病程文档均为 CLOB，加载时规范换行符 `\\r?\\n → \\n`，不做截断。
4. **多源诊断合并**：病案首页诊断与诊疗过程诊断合并为同一 `diagnosis` 表，靠 `diagnosis_source` 字段区分；首页诊断的扩展结构进 `diagnosis_front_page_meta` JSON；这两种诊断不参与跨院 UNION。


