-- 医疗枚举字典国标对齐（幂等）
-- HQMS RC001/RC030/RC031、GB/T 3304-1991，以及内部数据中心编码。
-- 该脚本面向已有数据库；新库同时使用 app/scripts/data 下 JSON 种子。
-- 本脚本由 sys_dict_data.json / sys_dict_type.json 自动生成，勿手改。
-- 修复 CRITICAL: sys_dict_type/sys_dict_data 均含 uuid/created_time/
--                updated_time/is_deleted NOT NULL 列，必须显式提供。

BEGIN;

-- ========== sys_dict_type UPSERT ==========
-- uuid 用 uuid5(dict_type) 保证幂等：重跑生成相同 uuid，ON CONFLICT 不创建新行
INSERT INTO sys_dict_type (uuid, dict_name, dict_type, status, description, tenant_id, created_time, updated_time, is_deleted) VALUES
  ('757af6f6-5550-52ca-9ed2-401df4c32ab2', '医疗·性别', 'med_sex', '0', 'HQMS RC001 国标（0=未知，1=男，2=女，9=未说明）', 1, NOW(), NOW(), false),
  ('36701c2f-bbe1-5cf4-82a4-459e8ca75069', '医疗-检查类型', 'med_exam_type', '0', '医疗领域检查类型字典（CT/PETCT/Pathology）', 1, NOW(), NOW(), false),
  ('75b52091-cdb3-52b9-b786-c4835966c45e', '医疗-偏侧性', 'med_laterality', '0', '医疗领域偏侧性字典（L/R/Bilateral/N/A）', 1, NOW(), NOW(), false),
  ('10faca4b-131e-551c-97bf-f74ba453a9f0', '医疗·吸烟状态', 'med_smoking_status', '0', '医疗吸烟状态（1=从不，2=既往，3=现在，9=未知）', 1, NOW(), NOW(), false),
  ('3d2a29ba-51af-5752-993a-cc5691747989', '医疗·民族', 'med_ethnicity', '0', 'GB/T 3304-1991 民族代码', 1, NOW(), NOW(), false),
  ('61dab1c3-a585-5b1c-bb88-7ee21df99cda', '医疗·ABO血型', 'med_blood_type_abo', '0', 'HQMS RC030 ABO血型代码', 1, NOW(), NOW(), false),
  ('06f5b23d-afca-5804-b1f1-054e6f641847', '医疗·Rh血型', 'med_blood_type_rh', '0', 'HQMS RC031 Rh血型代码', 1, NOW(), NOW(), false),
  ('22a4dc7f-24be-5108-9258-9c7f2e34e015', '医疗·数据中心', 'med_center', '0', '内部医院数据中心编码', 1, NOW(), NOW(), false)
ON CONFLICT (tenant_id, dict_type) DO UPDATE SET
  dict_name = EXCLUDED.dict_name,
  description = EXCLUDED.description,
  status = EXCLUDED.status;

-- ========== sys_dict_data UPSERT ==========
-- 通过 dict_type 反查 ID 填充 dict_type_id
WITH types AS (
  SELECT id, dict_type FROM sys_dict_type WHERE tenant_id=1 AND dict_type IN (
    'med_sex','med_exam_type','med_laterality','med_smoking_status','med_ethnicity','med_blood_type_abo','med_blood_type_rh','med_center'
  )
), src AS (
  SELECT * FROM (VALUES
    ('903144ac-d685-507e-af20-83db94c4e058', 1, 'A型', '1', 'med_blood_type_abo', true, 'RC030 ABO血型-A型'),
    ('00626710-dc53-5309-baac-2a74a12661ac', 2, 'B型', '2', 'med_blood_type_abo', false, 'RC030 ABO血型-B型'),
    ('6a7a42a6-7860-5753-ac53-33fcd85500e3', 3, 'O型', '3', 'med_blood_type_abo', false, 'RC030 ABO血型-O型'),
    ('3e164ceb-e8da-5a7f-94e5-6de1abff80ec', 4, 'AB型', '4', 'med_blood_type_abo', false, 'RC030 ABO血型-AB型'),
    ('792ba4f6-350b-5ef0-8bf7-7026c27cab09', 5, '不详', '5', 'med_blood_type_abo', false, 'RC030 ABO血型-不详'),
    ('9efd5ced-e745-5fbb-9370-ce2f8fb30878', 6, '未查', '6', 'med_blood_type_abo', false, 'RC030 ABO血型-未查'),
    ('c2a1fe0f-9bac-591e-b8af-0020ec66b4e0', 1, '阴性', '1', 'med_blood_type_rh', true, 'RC031 Rh血型-阴性'),
    ('5a231313-62c4-5a77-be09-a64ce284ba32', 2, '阳性', '2', 'med_blood_type_rh', false, 'RC031 Rh血型-阳性'),
    ('67317904-0b49-5471-a7e6-d591cb80c3c5', 3, '不详', '3', 'med_blood_type_rh', false, 'RC031 Rh血型-不详'),
    ('af05f155-29f4-5a26-bb4e-3fba18226b5c', 4, '未查', '4', 'med_blood_type_rh', false, 'RC031 Rh血型-未查'),
    ('c935b2f1-f364-592b-9230-6ffb6ea793f1', 1, '省医', 'shengyi', 'med_center', true, '医疗数据中心-省医'),
    ('5d0fbf0d-8390-5232-b5b0-3aaf0a78e584', 2, '新桥', 'xinqiao', 'med_center', false, '医疗数据中心-新桥'),
    ('41caea48-ec3d-5228-a9a2-a2ca8a48918e', 3, '珠江', 'zhujiang', 'med_center', false, '医疗数据中心-珠江'),
    ('6dd335ca-2f20-5f91-93e6-0932b5b4f18a', 1, '汉族', '01', 'med_ethnicity', true, 'GB/T 3304 民族-汉族'),
    ('eff9cd92-4504-5d17-a715-a7538abd3abf', 2, '蒙古族', '02', 'med_ethnicity', false, 'GB/T 3304 民族-蒙古族'),
    ('c6b85489-c44a-5b31-b15b-6f44cc84cae6', 3, '回族', '03', 'med_ethnicity', false, 'GB/T 3304 民族-回族'),
    ('e71e1567-bcb6-5135-b322-aac4ef925755', 4, '藏族', '04', 'med_ethnicity', false, 'GB/T 3304 民族-藏族'),
    ('e614b20d-807a-558f-a517-ea42cca7cc1d', 5, '维吾尔族', '05', 'med_ethnicity', false, 'GB/T 3304 民族-维吾尔族'),
    ('03291fd5-a89e-5bdf-9612-2bac0b4612ae', 6, '苗族', '06', 'med_ethnicity', false, 'GB/T 3304 民族-苗族'),
    ('a7b0bf79-ee0e-5092-b46a-46d6d5cab4b0', 7, '彝族', '07', 'med_ethnicity', false, 'GB/T 3304 民族-彝族'),
    ('caf59b6e-7aa9-555d-86de-ecc380f1f80d', 8, '壮族', '08', 'med_ethnicity', false, 'GB/T 3304 民族-壮族'),
    ('d4086fc5-217b-5cf1-8a94-2aabd62c230c', 9, '布依族', '09', 'med_ethnicity', false, 'GB/T 3304 民族-布依族'),
    ('756bb347-fb07-5911-a981-4cfafc46fc9c', 10, '朝鲜族', '10', 'med_ethnicity', false, 'GB/T 3304 民族-朝鲜族'),
    ('35feae19-d682-595c-8f35-bb1c9964d0d3', 11, '满族', '11', 'med_ethnicity', false, 'GB/T 3304 民族-满族'),
    ('2e344b9f-9294-5f69-abab-3989925e4a0c', 12, '侗族', '12', 'med_ethnicity', false, 'GB/T 3304 民族-侗族'),
    ('f91f0c2f-c3bb-5f65-9f25-3a799e32ebcc', 13, '瑶族', '13', 'med_ethnicity', false, 'GB/T 3304 民族-瑶族'),
    ('b3059528-11e6-5dd1-b256-098806f671bc', 14, '白族', '14', 'med_ethnicity', false, 'GB/T 3304 民族-白族'),
    ('a288bce3-dcb6-5987-b9b6-b5634fdd28a0', 15, '土家族', '15', 'med_ethnicity', false, 'GB/T 3304 民族-土家族'),
    ('8f6d5996-e8f2-5dd9-8980-6f0bcf883aa5', 16, '哈尼族', '16', 'med_ethnicity', false, 'GB/T 3304 民族-哈尼族'),
    ('0189ecb8-f93b-58eb-a503-4a849c0fb4c5', 17, '哈萨克族', '17', 'med_ethnicity', false, 'GB/T 3304 民族-哈萨克族'),
    ('5284273e-42ca-52f3-aeea-dc70a447e2b3', 18, '傣族', '18', 'med_ethnicity', false, 'GB/T 3304 民族-傣族'),
    ('25d9fcb7-e40d-5daa-bcab-138e84b4f404', 19, '黎族', '19', 'med_ethnicity', false, 'GB/T 3304 民族-黎族'),
    ('d97e5b76-9e77-5885-aeec-9f2dfe6816f3', 20, '傈僳族', '20', 'med_ethnicity', false, 'GB/T 3304 民族-傈僳族'),
    ('873443c8-e64d-53e6-ac32-35191af55b70', 21, '佤族', '21', 'med_ethnicity', false, 'GB/T 3304 民族-佤族'),
    ('f50e57bc-2885-548b-9ee3-8d97ec2db372', 22, '畲族', '22', 'med_ethnicity', false, 'GB/T 3304 民族-畲族'),
    ('64563c28-74c4-5a1b-afbf-5560667058e5', 23, '高山族', '23', 'med_ethnicity', false, 'GB/T 3304 民族-高山族'),
    ('3179ed08-cb79-58b5-acf7-7d972b1e07f4', 24, '拉祜族', '24', 'med_ethnicity', false, 'GB/T 3304 民族-拉祜族'),
    ('552250d9-4405-550c-a2e1-722dfd29fac3', 25, '水族', '25', 'med_ethnicity', false, 'GB/T 3304 民族-水族'),
    ('8cc46037-bd17-5379-9c3f-f969a0b57f10', 26, '东乡族', '26', 'med_ethnicity', false, 'GB/T 3304 民族-东乡族'),
    ('c38d9059-498e-59c3-be45-fcf76da7790f', 27, '纳西族', '27', 'med_ethnicity', false, 'GB/T 3304 民族-纳西族'),
    ('71edef23-5f6e-5783-8897-4bf20ce20141', 28, '景颇族', '28', 'med_ethnicity', false, 'GB/T 3304 民族-景颇族'),
    ('529a2bc2-e42c-5cc2-bdb7-56ca03b3d7ad', 29, '柯尔克孜族', '29', 'med_ethnicity', false, 'GB/T 3304 民族-柯尔克孜族'),
    ('ba7e2822-b024-5859-89d5-ebb4a6bf0451', 30, '土族', '30', 'med_ethnicity', false, 'GB/T 3304 民族-土族'),
    ('ba8c20f5-03af-5471-85f8-d4594f78fce0', 31, '达斡尔族', '31', 'med_ethnicity', false, 'GB/T 3304 民族-达斡尔族'),
    ('207f25ea-9b6f-5ec2-83bf-f21f98052c5d', 32, '仫佬族', '32', 'med_ethnicity', false, 'GB/T 3304 民族-仫佬族'),
    ('0ccfc639-778e-5aa1-b049-ac6ad9be3c4a', 33, '羌族', '33', 'med_ethnicity', false, 'GB/T 3304 民族-羌族'),
    ('33f466b7-6f65-5583-80c6-131877a3e22c', 34, '布朗族', '34', 'med_ethnicity', false, 'GB/T 3304 民族-布朗族'),
    ('65f7025e-ebdf-533a-8191-28124796ec0d', 35, '撒拉族', '35', 'med_ethnicity', false, 'GB/T 3304 民族-撒拉族'),
    ('27af0cc6-c684-5b43-a058-26345f0c1a8f', 36, '毛南族', '36', 'med_ethnicity', false, 'GB/T 3304 民族-毛南族'),
    ('7bf45326-1877-5a12-a83f-58a010ba600a', 37, '仡佬族', '37', 'med_ethnicity', false, 'GB/T 3304 民族-仡佬族'),
    ('11b11ea0-0f0b-557c-877f-6d11b51dba10', 38, '锡伯族', '38', 'med_ethnicity', false, 'GB/T 3304 民族-锡伯族'),
    ('0de18c76-e8cb-5c3a-a09a-f915b41b0689', 39, '阿昌族', '39', 'med_ethnicity', false, 'GB/T 3304 民族-阿昌族'),
    ('71e37a59-e314-5447-bc62-b2cbbc67cb4b', 40, '普米族', '40', 'med_ethnicity', false, 'GB/T 3304 民族-普米族'),
    ('b463e0e1-88c5-51b1-b3ce-7d8e070ce5b9', 41, '塔吉克族', '41', 'med_ethnicity', false, 'GB/T 3304 民族-塔吉克族'),
    ('dc7968ec-4415-5c0e-8645-528e00377ba8', 42, '怒族', '42', 'med_ethnicity', false, 'GB/T 3304 民族-怒族'),
    ('3320774b-34f3-5ca3-8f02-4fef3987865b', 43, '乌孜别克族', '43', 'med_ethnicity', false, 'GB/T 3304 民族-乌孜别克族'),
    ('f38f8956-1cfd-51d5-b762-0f1d9993f281', 44, '俄罗斯族', '44', 'med_ethnicity', false, 'GB/T 3304 民族-俄罗斯族'),
    ('7a81c6eb-5e40-534b-a10c-2cbc5249965a', 45, '鄂温克族', '45', 'med_ethnicity', false, 'GB/T 3304 民族-鄂温克族'),
    ('03434c70-d484-5a85-b206-0edb4f471a75', 46, '德昂族', '46', 'med_ethnicity', false, 'GB/T 3304 民族-德昂族'),
    ('6b5579b4-176b-58e4-8b73-2a2f12d9b8e4', 47, '保安族', '47', 'med_ethnicity', false, 'GB/T 3304 民族-保安族'),
    ('faf01b77-d401-5bc4-97d4-bd2298fc4238', 48, '裕固族', '48', 'med_ethnicity', false, 'GB/T 3304 民族-裕固族'),
    ('8a9b1ae9-7387-5dcc-8462-75e1a0f2261f', 49, '京族', '49', 'med_ethnicity', false, 'GB/T 3304 民族-京族'),
    ('04adca0a-7d21-569c-a0cb-9de926b46f56', 50, '塔塔尔族', '50', 'med_ethnicity', false, 'GB/T 3304 民族-塔塔尔族'),
    ('b2419836-c1b6-5bc2-892a-675058e0ddf4', 51, '独龙族', '51', 'med_ethnicity', false, 'GB/T 3304 民族-独龙族'),
    ('5986c845-d8ea-57db-8aec-9625ff142abd', 52, '鄂伦春族', '52', 'med_ethnicity', false, 'GB/T 3304 民族-鄂伦春族'),
    ('bce70996-97ea-529a-9e17-fcb62a682cf3', 53, '赫哲族', '53', 'med_ethnicity', false, 'GB/T 3304 民族-赫哲族'),
    ('154b4950-2835-5605-8d89-99321ead3bb0', 54, '门巴族', '54', 'med_ethnicity', false, 'GB/T 3304 民族-门巴族'),
    ('e5c63110-c820-52d7-8d76-7c514c42a6cc', 55, '珞巴族', '55', 'med_ethnicity', false, 'GB/T 3304 民族-珞巴族'),
    ('94509b89-de2a-5ef4-85b4-0d5e9fd68e96', 56, '基诺族', '56', 'med_ethnicity', false, 'GB/T 3304 民族-基诺族'),
    ('07a1af19-6c36-58dc-a59d-a36d742d99b6', 57, '其他', '99', 'med_ethnicity', false, 'GB/T 3304 民族-其他'),
    ('19c45e34-6808-5774-b877-1598e3bcc6e7', 1, 'CT', 'CT', 'med_exam_type', true, '医疗检查类型-CT'),
    ('28bdd25f-8409-5649-85f0-284964878525', 2, 'PET-CT', 'PETCT', 'med_exam_type', false, '医疗检查类型-PET-CT'),
    ('ae321c43-ab00-556b-a725-d02ed906ab16', 3, '病理', 'Pathology', 'med_exam_type', false, '医疗检查类型-病理'),
    ('d71876f3-9678-5bd5-b755-753af4f2f5ad', 1, '左', 'L', 'med_laterality', false, '医疗偏侧性-左'),
    ('4228244c-48cc-5dc9-88f3-bbe7a04dcf91', 2, '右', 'R', 'med_laterality', false, '医疗偏侧性-右'),
    ('c83b8aef-8485-514e-979e-a10770d55bbf', 3, '双侧', 'Bilateral', 'med_laterality', false, '医疗偏侧性-双侧'),
    ('029c43cc-d7a3-59ac-9ff0-c2fc004c4d39', 4, '不适用', 'N/A', 'med_laterality', true, '医疗偏侧性-不适用'),
    ('c6530e70-4b9c-5c28-9e1e-1837399053c9', 1, '未知的性别', '0', 'med_sex', true, '医疗性别-未知'),
    ('84656537-a03e-516e-be6c-bb5f6bbd25fd', 2, '男', '1', 'med_sex', false, '医疗性别-男'),
    ('104a05ba-68e2-58c6-8b39-8b8d07631500', 3, '女', '2', 'med_sex', false, '医疗性别-女'),
    ('a790bf15-65c0-5440-8333-62a039c6193f', 4, '未说明的性别', '9', 'med_sex', false, '医疗性别-未说明'),
    ('2fd6d9df-4912-514a-bb8a-02d9736e870a', 1, '从不', '1', 'med_smoking_status', true, '医疗吸烟状态-从不'),
    ('4bf635bf-c3df-5fc6-917f-3b989ae596c6', 2, '既往', '2', 'med_smoking_status', false, '医疗吸烟状态-既往'),
    ('1ba87459-a04a-5559-833b-169b95f0135c', 3, '现在', '3', 'med_smoking_status', false, '医疗吸烟状态-现在'),
    ('5b8daffb-76a6-5969-8db2-c08807b74218', 4, '未知', '9', 'med_smoking_status', false, '医疗吸烟状态-未知')
  ) AS v(uuid, dict_sort, dict_label, dict_value, dict_type, is_default, description)
)
INSERT INTO sys_dict_data (uuid, dict_sort, dict_label, dict_value, dict_type, dict_type_id, css_class, list_class, is_default, status, description, tenant_id, created_time, updated_time, is_deleted)
SELECT v.uuid, v.dict_sort, v.dict_label, v.dict_value, v.dict_type, t.id, '', NULL, v.is_default, '0', v.description, 1, NOW(), NOW(), false
FROM src v JOIN types t USING (dict_type)
ON CONFLICT (tenant_id, dict_type, dict_value) DO UPDATE SET
  dict_sort = EXCLUDED.dict_sort,
  dict_label = EXCLUDED.dict_label,
  is_default = EXCLUDED.is_default,
  description = EXCLUDED.description,
  status = '0';

COMMIT;
