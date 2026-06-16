# 省医（Shengyi）独有表定义

> 省医与珠江-新桥共用的表（patient、pathology_specimen、surgery_record、genetic_test）定义见 [unified_table_schema.md](./unified_table_schema.md)。
> 本文档仅包含省医独有的表。

## 目录结构

```
data/shengyi/
├── patient.parquet              # → 统一表
├── pathology_specimen.parquet   # → 统一表
├── surgery_record.parquet       # → 统一表
├── genetic_test.parquet         # → 统一表
├── visit_record.parquet         # 省医独有
├── drug_order.parquet           # 省医独有
├── non_drug_order.parquet       # 省医独有
├── lab_result.parquet           # 省医独有
├── imaging_report.parquet       # 省医独有
├── ultrasound_report.parquet    # 省医独有
└── ecg_report.parquet           # 省医独有
```

---

## 1. visit_record — 就诊记录

粒度：每患者每次就诊一行。综合了就诊基本信息、住院病案首页、病史、诊断等就诊级别数据。

### 核心字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| patient_id | string | 患者编号 |
| visit_id | string | 就诊编号 |
| visit_category | string | 就诊类别（住院/门诊/急诊） |
| admission_time | timestamp | 入院（就诊）时间 |
| discharge_date | date | 出院日期 |
| admission_dept | string | 入院（就诊）科室 |
| discharge_dept | string | 出院科室 |
| length_of_stay | int32 | 住院天数 |
| payment_method | string | 医疗付款方式 |
| visit_age | float | 就诊年龄（岁） |
| inpatient_no | string | 住院号 |
| outpatient_no | string | 门诊号 |

### JSON 扩展字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| inpatient_front_page | json | 住院病案首页扩展信息（不含手术，手术已拆入 surgery_record） |
| medical_history | json | 病史信息 |
| diagnoses | json | 本次就诊诊断列表 |
| clinical_documents | json | 病程记录文档 |

#### inpatient_front_page 结构

```jsonc
{
  "admission_route": "急诊",           // 入院途径
  "admission_status": "危",            // 入院状态名称
  "discharge_method": "医嘱离院",       // 离院方式
  "readmit_plan_31d": "否",            // 是否有31天内再入院计划
  "readmit_purpose": "",               // 31天再住院目的
  "admission_count": 3,                // 住院次数
  "rh_blood_type": "阳性",             // RH血型
  "abo_blood_type": "A",               // ABO血型
  "transfusion": {                     // 输血成分
    "whole_blood": "",
    "plasma": "",
    "platelet": "",
    "rbc": "",
    "other": ""
  },
  "neonatal_birth_weight": null,       // 新生儿出生体重（克）
  "neonatal_admission_weight": null,   // 新生儿入院体重（克）
  "birth_place": "",                   // 出生地
  "post_surgical_complication": "否",  // 是否为手术后并发症
  "coma_duration": {                   // 颅脑损伤患者昏迷时间
    "pre_admission": {"days": 0, "hours": 0, "minutes": 0},
    "post_admission": {"days": 0, "hours": 0, "minutes": 0}
  },
  "rescue_count": 0,                   // 抢救次数
  "rescue_success_count": 0,           // 抢救成功次数
  "nursing_days": {                    // 护理天数
    "level_1": 5,
    "level_2": 3
  }
}
```

#### medical_history 结构

```jsonc
{
  "chief_complaint": "右上肺癌术后2月余",      // 主诉
  "present_illness": "患者2月前因体检发现...",   // 现病史
  "past_history": "否认高血压、糖尿病...",      // 既往史
  "personal_history": "吸烟30年...",            // 个人史
  "marital_history": "已婚已育",                // 婚育史
  "family_history": "否认家族遗传病史",         // 家族史
  "record_date": "2008-08-13",                  // 记录日期
  "data_source": "住院病历"                     // 数据来源
}
```

#### diagnoses 结构

```jsonc
[
  {
    "code": "C34.101",              // 诊断编码（ICD-10）
    "name": "肺上叶恶性肿瘤",        // 诊断名称
    "type": "主要诊断",             // 诊断类型
    "outcome": "好转",              // 诊断归转情况
    "diagnosis_date": "2008-08-13", // 诊断日期
    "admission_condition": "有",    // 入院病情
    "is_primary": true,             // 是否主要诊断
    "category": "出院主要诊断"       // 诊断类别
  }
]
```

#### clinical_documents 结构

```jsonc
[
  {
    "content": "患者因'右上肺癌术后2月余'入院...",  // 文档内容
    "record_date": "2008-08-13",                    // 记录日期
    "doc_type": "入院记录.辅助检查"                  // 文档类型
  }
]
```

---

## 2. drug_order — 药物医嘱

粒度：每条药物医嘱一行，包含住院药物医嘱和门诊药物处方。

### 核心字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| patient_id | string | 患者编号 |
| visit_id | string | 就诊编号 |
| order_source | string | 来源：inpatient（住院）/ outpatient（门诊） |
| order_time | timestamp | 医嘱开始时间 / 处方开立日期 |
| drug_generic_name | string | 药物通用名 |

### JSON 扩展字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| order_detail | json | 医嘱详细信息 |

#### order_detail — 住院药物医嘱

```jsonc
{
  "duration_type": "长期",           // 长期或临时
  "drug_code": "DXM001",            // 药物编码
  "drug_trade_name": "地塞米松注射液", // 药物商品名
  "stop_time": "2008-08-20 00:00:00", // 医嘱停止时间
  "specification": "5mg/ml",          // 药物规格
  "dose": "5",                        // 药物剂量
  "dose_unit": "mg",                  // 剂量单位
  "frequency": "QD",                  // 用药频率
  "route": "静脉注射",                // 用药途径
  "dosage_form": "注射液",            // 药物剂型
  "order_dept": "肺一科"              // 开嘱科室
}
```

#### order_detail — 门诊药物处方

```jsonc
{
  "original_patient_id": "3175462",     // 原始患者编号
  "visit_id": "1000900001",             // 就诊编号
  "prescription_id": "RX001",           // 处方编号
  "drug_type": "西药",                  // 药品类型
  "drug_name": "氯雷他定片",            // 药物名称
  "specification": "10mg",              // 药物规格
  "dosage_form": "片剂",                // 药物剂型
  "dose_per_use": "10mg",               // 使用次剂量
  "frequency": "QD",                    // 使用频次
  "route": "口服",                      // 用药途径
  "duration_days": 7,                   // 用药天数
  "prescription_date": "2010-03-15",    // 处方开立日期
  "prescribing_dept": "肺一科",         // 开立科室
  "doctor_signature": "李四"            // 开立医生签名
}
```

---

## 3. non_drug_order — 非药物医嘱

粒度：每条非药物医嘱一行。

### 核心字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| patient_id | string | 患者编号 |
| visit_id | string | 就诊编号 |
| order_name | string | 医嘱名称 |
| order_start_time | timestamp | 医嘱开始时间 |
| order_stop_time | timestamp | 医嘱停止时间 |

### JSON 扩展字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| order_detail | json | 医嘱扩展信息 |

#### order_detail 结构

```jsonc
{
  "duration_type": "长期",    // 长期或临时
  "order_dept": "肺一科"      // 开嘱科室
}
```

---

## 4. lab_result — 检验报告

粒度：每条检验子项一行。

### 核心字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| patient_id | string | 患者编号 |
| visit_id | string | 就诊编号 |
| report_id | string | 检验单号 |
| test_name | string | 检验项目名称 |
| item_name | string | 检验子项中文名 |
| item_result | string | 检验子项结果 |
| item_result_value | float | 检验子项结果数值 |
| item_unit | string | 检验子项单位 |
| ref_lower | float | 参考下限值 |
| ref_upper | float | 参考上限值 |
| collection_time | timestamp | 采集时间 |

### JSON 扩展字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| test_detail | json | 检验扩展信息 |

#### test_detail 结构

```jsonc
{
  "overall_result": "15.23"   // 检验结果（整体/文本描述）
}
```

---

## 5. imaging_report — 影像学报告

粒度：每次影像检查一行。

### 核心字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| patient_id | string | 患者编号 |
| visit_id | string | 就诊编号 |
| report_id | string | 报告编号 |
| exam_type | string | 检查类型名称（CT/MRI/DR/X线等） |
| exam_body_part | string | 检查部位 |
| exam_date | date | 检查日期 |
| exam_item | string | 检查项目 |

### JSON 扩展字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| exam_detail | json | 检查详细发现 |

#### exam_detail 结构

```jsonc
{
  "type_code": "CT",                                  // 检查类型代码
  "exam_method": "平扫+增强",                          // 检查方法
  "findings": "右肺上叶术后改变，右侧胸膜增厚...",      // 检查所见（镜下所见）
  "impression": "右肺上叶肺癌术后，右侧胸膜转移可能"    // 印象
}
```

---

## 6. ultrasound_report — 超声诊断报告

粒度：每次超声检查一行。

### 核心字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| patient_id | string | 患者编号 |
| visit_id | string | 就诊编号 |
| report_id | string | 报告编号 |
| exam_name | string | 检查名称 |
| body_part | string | 检查部位 |
| exam_date | date | 检查日期 |
| ultrasound_finding | string | 超声提示 |

### JSON 扩展字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| exam_detail | json | 检查详情及测量子项 |

#### exam_detail 结构

```jsonc
{
  "findings": "左室内径正常，室间隔及左室壁厚...",  // 检查所见
  "items": [                                        // 测量子项列表
    {
      "name": "二尖瓣A",
      "result": "0.83",
      "value": 0.83,
      "unit": "m/s",
      "data_source": "超声"
    }
  ]
}
```

---

## 7. ecg_report — 心电图报告

粒度：每次心电图检查一行。

> 省医该模块暂无数据，预留表结构。

### 核心字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| patient_id | string | 患者编号 |
| visit_id | string | 就诊编号 |
| report_id | string | 报告编号 |
| exam_date | date | 检查日期 |

### JSON 扩展字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| exam_detail | json | 心电图检查详情（含子项测量） |

---

## 表间关系

```
patient (1) ──── (N) visit_record
  │                    │
  │                    ├── (N) drug_order
  │                    ├── (N) non_drug_order
  │                    ├── (N) lab_result
  │                    ├── (N) imaging_report
  │                    ├── (N) ultrasound_report
  │                    ├── (N) ecg_report
  │                    └── (N) surgery_record     ← 统一表
  │
  ├── (N) pathology_specimen    ← 统一表
  └── (N) genetic_test          ← 统一表
```

所有表通过 `patient_id` 关联患者，就诊级别的表额外通过 `patient_id + visit_id` 关联具体就诊。
