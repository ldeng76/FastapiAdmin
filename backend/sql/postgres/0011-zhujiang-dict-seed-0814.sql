-- =====================================================================
-- 0011 - 珠江中心 0814 新批次数据（zhujiang0814.parquet）补充字典映射
-- 背景: 2026-08-14 珠江新数据枚举值域与 0723 sample 不同，
--       0008 种子未覆盖的标签导入时会落 NULL + med_dict_unmatched。
-- 内容（幂等 ON CONFLICT DO NOTHING，可重复执行）:
--   med_ethnicity      (22): 汉族/壮族/佤族/... 全量民族标签（GB3304 两位码）
--                            外籍人士 → 99（其他）
--   med_blood_type_abo (2):  未查→6, 不详→5
--   med_blood_type_rh  (4):  阳→2, 阴→1, 未查→4, 不详→3（0008 只有 阳性/阴性 全称）
-- 注: 与 0008 相同，med_dict_mapping 无 dict_value 列，
--     dict_data_id 通过 JOIN sys_dict_data 反查。
-- =====================================================================

BEGIN;

SET LOCAL search_path = lnrs;

WITH hosp AS (
    SELECT id AS hospital_id FROM med_hospital WHERE code = 'zhujiang'
)
INSERT INTO med_dict_mapping (
    uuid, hospital_id, dict_type_id, dict_data_id, raw_label, raw_value,
    tenant_id, status, description, created_time, updated_time, is_deleted
)
SELECT
    gen_random_uuid(),
    h.hospital_id,
    dt.id,
    sd.id,
    m.raw_label,
    m.raw_value,
    1,
    '0',
    m.note,
    NOW(), NOW(),
    FALSE
FROM hosp h
CROSS JOIN (
    VALUES
        -- med_ethnicity (22): 0814 批次实际出现的民族标签
        ('med_ethnicity', '汉族',     '01', 'ethnicity', '0814批次-汉族'),
        ('med_ethnicity', '蒙古族',   '02', 'ethnicity', '0814批次-蒙古族'),
        ('med_ethnicity', '回族',     '03', 'ethnicity', '0814批次-回族'),
        ('med_ethnicity', '维吾尔族', '05', 'ethnicity', '0814批次-维吾尔族'),
        ('med_ethnicity', '苗族',     '06', 'ethnicity', '0814批次-苗族'),
        ('med_ethnicity', '彝族',     '07', 'ethnicity', '0814批次-彝族'),
        ('med_ethnicity', '壮族',     '08', 'ethnicity', '0814批次-壮族'),
        ('med_ethnicity', '布依族',   '09', 'ethnicity', '0814批次-布依族'),
        ('med_ethnicity', '朝鲜族',   '10', 'ethnicity', '常用补充-朝鲜族'),
        ('med_ethnicity', '满族',     '11', 'ethnicity', '0814批次-满族'),
        ('med_ethnicity', '侗族',     '12', 'ethnicity', '0814批次-侗族'),
        ('med_ethnicity', '瑶族',     '13', 'ethnicity', '0814批次-瑶族'),
        ('med_ethnicity', '白族',     '14', 'ethnicity', '0814批次-白族'),
        ('med_ethnicity', '土家族',   '15', 'ethnicity', '0814批次-土家族'),
        ('med_ethnicity', '哈尼族',   '16', 'ethnicity', '0814批次-哈尼族'),
        ('med_ethnicity', '哈萨克族', '17', 'ethnicity', '0814批次-哈萨克族'),
        ('med_ethnicity', '傣族',     '18', 'ethnicity', '0814批次-傣族'),
        ('med_ethnicity', '黎族',     '19', 'ethnicity', '0814批次-黎族'),
        ('med_ethnicity', '佤族',     '21', 'ethnicity', '0814批次-佤族'),
        ('med_ethnicity', '畲族',     '22', 'ethnicity', '0814批次-畲族'),
        ('med_ethnicity', '拉祜族',   '24', 'ethnicity', '0814批次-拉祜族'),
        ('med_ethnicity', '布朗族',   '34', 'ethnicity', '0814批次-布朗族'),
        ('med_ethnicity', '外籍人士', '99', 'ethnicity', '0814批次-外籍人士归其他'),
        -- med_blood_type_abo (2)
        ('med_blood_type_abo', '未查', '6', 'blood_type_abo', '0814批次-未查'),
        ('med_blood_type_abo', '不详', '5', 'blood_type_abo', '0814批次-不详'),
        -- med_blood_type_rh (4): 0814 批次用单字 阳/阴
        ('med_blood_type_rh', '阳',   '2', 'blood_type_rh',  '0814批次-阳性简称'),
        ('med_blood_type_rh', '阴',   '1', 'blood_type_rh',  '0814批次-阴性简称'),
        ('med_blood_type_rh', '未查', '4', 'blood_type_rh',  '0814批次-未查'),
        ('med_blood_type_rh', '不详', '3', 'blood_type_rh',  '0814批次-不详')
) AS m(dict_type, raw_label, dict_value, raw_value, note)
JOIN sys_dict_type dt ON dt.dict_type = m.dict_type
JOIN sys_dict_data sd ON sd.dict_type = m.dict_type AND sd.dict_value = m.dict_value
ON CONFLICT (hospital_id, dict_type_id, raw_label) DO NOTHING;

COMMIT;
