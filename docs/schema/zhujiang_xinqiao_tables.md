# 珠江-新桥（Zhujiang-Xinqiao）多中心肺结节独有表定义

> 珠江-新桥与省医共用的表（patient、pathology_specimen、surgery_record、genetic_test）定义见 [unified_table_schema.md](./unified_table_schema.md)。
> 本文档仅包含珠江-新桥独有的表。

## 目录结构

```
data/zhujiang_xinqiao/
├── patient.parquet              # → 统一表
├── pathology_specimen.parquet   # → 统一表
├── surgery_record.parquet       # → 统一表
├── genetic_test.parquet         # → 统一表
├── nodule_imaging.parquet       # 珠江-新桥独有
├── ihc_result.parquet           # 珠江-新桥独有
└── follow_up.parquet            # 珠江-新桥独有
```

---

## 1. nodule_imaging — 结节影像

粒度：一行 = 一次 CT 中的一个结节。同一患者多次 CT、一次 CT 多个结节均产生多行。

### 核心字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| patient_id | string | 患者编号 |
| exam_id | string | 检查唯一号（机构内部检查号，可对接DICOM） |
| exam_date | timestamp | 检查日期时间 |
| exam_type | string | 检查类型（CT/PET-CT/MRI/胸片） |
| nodule_no | string | 结节编号（N1/N2/N3，区分一例多结节） |
| nodule_location | string | 结节位置（叶+段） |
| long_diameter | float | 长径(mm) |
| density_type | string | 密度类型（纯磨玻璃/部分实性/实性/钙化/囊性/空洞） |

### JSON 扩展字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| exam_meta | json | 检查元数据 |
| nodule_morphology | json | 结节形态与征象 |
| nodule_quantitative | json | 结节定量参数 |
| follow_up_comparison | json | 与既往片对比 |

#### exam_meta 结构

```jsonc
{
  "report_date": "2024-09-15",                 // 报告日期
  "exam_name": "肺螺旋CT高分辨",               // 检查名称
  "contrast": "平扫",                           // 是否增强（平扫/增强）
  "slice_thickness_mm": 1.0                     // 层厚(mm)
}
```

#### nodule_morphology 结构

```jsonc
{
  "subpleural": false,                          // 是否胸膜下
  "margin": "分叶",                             // 边缘（光滑/分叶/毛刺/不规则）
  "signs": [                                    // 影像征象（多选）
    "毛刺",
    "胸膜牵拉"
  ],
  "mediastinal_lymphadenopathy": false,         // 纵隔/肺门淋巴结肿大
  "pleural_effusion": false                     // 胸腔积液
}
```

#### nodule_quantitative 结构

```jsonc
{
  "short_diameter_mm": 8,                       // 短径(mm)
  "volume_mm3": null,                           // 体积(mm³)（若报告自动给出）
  "mean_ct_value_hu": -450,                     // 平均CT值(HU)
  "solid_ratio_pct": 30,                        // 实性占比(%)（部分实性结节填）
  "solid_component_mm": 5,                      // 实性成分大小(mm)（部分实性结节填）
  "lung_rads": "4A",                            // Lung-RADS（1/2/3/4A/4B/4X）
  "dicom_slice": "Se3 Im330"                    // DICOM切片号
}
```

#### follow_up_comparison 结构

```jsonc
{
  "vs_prior": "增大"   // 与既往片对比（无变化/增大/缩小/新发/消失）
}
```

---

## 2. ihc_result — 免疫组化结果

粒度：每份标本的免疫组化检测一行，与 pathology_specimen 通过 specimen_id 关联。

### 核心字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| patient_id | string | 患者编号 |
| specimen_id | string | 病理标本号 |
| ki67_pct | float | Ki-67(%) |

### JSON 扩展字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| markers | json | 免疫组化标志物详情 |

#### markers 结构

```jsonc
{
  "pdl1_tps_pct": 10,                   // PD-L1 TPS(%)
  "pdl1_clone": "22C3",                 // PD-L1 克隆号（22C3/SP142/SP263/E1L3N）
  "pdl1_cps": null,                     // PD-L1 CPS
  "alk_ihc": "阴性",                    // ALK (IHC, D5F3)
  "ttf1": "阳性",                       // TTF-1
  "napsina": "阳性",                    // NapsinA
  "p40": "阴性",                        // P40
  "p53": "野生型"                       // P53（野生型/突变型(过表达/缺失)）
}
```

---

## 3. follow_up — 随访结局

粒度：每患者一行（或每患者一个随访周期一行）。

### 核心字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| patient_id | string | 患者编号 |
| last_followup_date | date | 末次随访日期 |
| recurrence | string | 是否复发（是/否） |
| survival_status | string | 生存状态（存活/死亡/失访） |

### JSON 扩展字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| treatment_detail | json | 辅助治疗详情 |
| recurrence_detail | json | 复发详情 |

#### treatment_detail 结构

```jsonc
{
  "adjuvant_therapy": "靶向",                // 辅助治疗（无/化疗/靶向/免疫/放疗/化免）
  "first_line_regimen": "奥希替尼"            // 一线治疗方案
}
```

#### recurrence_detail 结构

```jsonc
{
  "recurrence_date": "2025-12-01",            // 复发日期
  "recurrence_site": "远处",                  // 复发部位（局部/区域(纵隔)/远处/多部位）
  "death_date": null                          // 死亡日期
}
```

---

## 表间关系

```
patient (1) ──── (N) nodule_imaging       [patient_id]
  │
  ├── (N) pathology_specimen              [patient_id]    ← 统一表
  │         └── (1) ihc_result            [specimen_id]
  │
  ├── (N) genetic_test                    [patient_id]    ← 统一表
  │
  ├── (N) surgery_record                  [patient_id]    ← 统一表
  │
  └── (1..N) follow_up                   [patient_id]
```

通过 `patient_id` 关联患者。`ihc_result` 与 `pathology_specimen` 通过 `specimen_id` 关联到具体标本。`nodule_imaging` 中的 `exam_id + nodule_no` 可唯一标识一个结节在某次检查中的记录。
