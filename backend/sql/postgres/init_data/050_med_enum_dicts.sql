-- 医疗枚举字典国标对齐（幂等）
-- HQMS RC001/RC030/RC031、GB/T 3304-1991，以及内部数据中心编码。
-- 该脚本面向已有数据库；新库同时使用 app/scripts/data 下 JSON 种子。

BEGIN;

-- 字典类型：平台租户数据共享，按 tenant_id + dict_type 幂等更新。
INSERT INTO sys_dict_type (dict_name, dict_type, status, description, tenant_id)
VALUES
 ('医疗·性别', 'med_sex', '0', 'HQMS RC001 国标（0=未知，1=男，2=女，9=未说明）', 1),
 ('医疗·吸烟状态', 'med_smoking_status', '0', '医疗吸烟状态（1=从不，2=既往，3=现在，9=未知）', 1),
 ('医疗·民族', 'med_ethnicity', '0', 'GB/T 3304-1991 民族代码', 1),
 ('医疗·ABO血型', 'med_blood_type_abo', '0', 'HQMS RC030 ABO血型代码', 1),
 ('医疗·Rh血型', 'med_blood_type_rh', '0', 'HQMS RC031 Rh血型代码', 1),
 ('医疗·数据中心', 'med_center', '0', '内部医院数据中心编码', 1)
ON CONFLICT (tenant_id, dict_type) DO UPDATE SET
  dict_name = EXCLUDED.dict_name,
  description = EXCLUDED.description,
  status = EXCLUDED.status;

-- 通过 dict_type 反查 ID，避免依赖不同数据库中的自增 ID。
WITH types AS (
  SELECT id, dict_type FROM sys_dict_type
  WHERE tenant_id = 1 AND dict_type IN ('med_sex','med_smoking_status','med_ethnicity','med_blood_type_abo','med_blood_type_rh','med_center')
), values_data(dict_type, dict_sort, dict_label, dict_value, is_default, description) AS (
  VALUES
  ('med_sex',1,'未知','0',true,'医疗性别-未知'),('med_sex',2,'男','1',false,'医疗性别-男'),('med_sex',3,'女','2',false,'医疗性别-女'),('med_sex',4,'未说明','9',false,'医疗性别-未说明'),
  ('med_smoking_status',1,'从不','1',true,'医疗吸烟状态-从不'),('med_smoking_status',2,'既往','2',false,'医疗吸烟状态-既往'),('med_smoking_status',3,'现在','3',false,'医疗吸烟状态-现在'),('med_smoking_status',4,'未知','9',false,'医疗吸烟状态-未知'),
  ('med_blood_type_abo',1,'A','1',true,'RC030 ABO血型-A'),('med_blood_type_abo',2,'B','2',false,'RC030 ABO血型-B'),('med_blood_type_abo',3,'O','3',false,'RC030 ABO血型-O'),('med_blood_type_abo',4,'AB','4',false,'RC030 ABO血型-AB'),('med_blood_type_abo',5,'不详','5',false,'RC030 ABO血型-不详'),('med_blood_type_abo',6,'未查','6',false,'RC030 ABO血型-未查'),
  ('med_blood_type_rh',1,'阴性','1',true,'RC031 Rh血型-阴性'),('med_blood_type_rh',2,'阳性','2',false,'RC031 Rh血型-阳性'),('med_blood_type_rh',3,'不详','3',false,'RC031 Rh血型-不详'),
  ('med_center',1,'省医','shengyi',true,'医疗数据中心-省医'),('med_center',2,'新桥','xinqiao',false,'医疗数据中心-新桥'),('med_center',3,'珠江','zhujiang',false,'医疗数据中心-珠江')
)
INSERT INTO sys_dict_data (dict_sort, dict_label, dict_value, dict_type, dict_type_id, css_class, list_class, is_default, status, description, tenant_id)
SELECT v.dict_sort, v.dict_label, v.dict_value, v.dict_type, t.id, '', NULL, v.is_default, '0', v.description, 1
FROM values_data v JOIN types t USING (dict_type)
ON CONFLICT DO NOTHING;

-- 民族 01~56 + 99。标签来自 GB/T 3304-1991，使用稳定标准码。
WITH types AS (SELECT id FROM sys_dict_type WHERE tenant_id=1 AND dict_type='med_ethnicity'),
eth(dict_sort, dict_label, dict_value) AS (VALUES
(1,'汉族','01'),(2,'蒙古族','02'),(3,'回族','03'),(4,'藏族','04'),(5,'维吾尔族','05'),(6,'苗族','06'),(7,'彝族','07'),(8,'壮族','08'),(9,'布依族','09'),(10,'朝鲜族','10'),(11,'满族','11'),(12,'侗族','12'),(13,'瑶族','13'),(14,'白族','14'),(15,'土家族','15'),(16,'哈尼族','16'),(17,'哈萨克族','17'),(18,'傣族','18'),(19,'黎族','19'),(20,'傈僳族','20'),(21,'佤族','21'),(22,'畲族','22'),(23,'高山族','23'),(24,'拉祜族','24'),(25,'水族','25'),(26,'东乡族','26'),(27,'纳西族','27'),(28,'景颇族','28'),(29,'柯尔克孜族','29'),(30,'土族','30'),(31,'达斡尔族','31'),(32,'仫佬族','32'),(33,'羌族','33'),(34,'布朗族','34'),(35,'撒拉族','35'),(36,'毛南族','36'),(37,'仡佬族','37'),(38,'锡伯族','38'),(39,'阿昌族','39'),(40,'普米族','40'),(41,'塔吉克族','41'),(42,'怒族','42'),(43,'乌孜别克族','43'),(44,'俄罗斯族','44'),(45,'鄂温克族','45'),(46,'德昂族','46'),(47,'保安族','47'),(48,'裕固族','48'),(49,'京族','49'),(50,'塔塔尔族','50'),(51,'独龙族','51'),(52,'鄂伦春族','52'),(53,'赫哲族','53'),(54,'门巴族','54'),(55,'珞巴族','55'),(56,'基诺族','56'),(57,'其他','99'))
INSERT INTO sys_dict_data (dict_sort,dict_label,dict_value,dict_type,dict_type_id,css_class,list_class,is_default,status,description,tenant_id)
SELECT e.dict_sort,e.dict_label,e.dict_value,'med_ethnicity',t.id,'',NULL,e.dict_sort=1,'0','GB/T 3304 民族-'||e.dict_label,1 FROM eth e CROSS JOIN types t
ON CONFLICT DO NOTHING;

-- 将历史 M/F/U 值改为 RC001 标准值；删除旧值后插入标准条目已由上方完成。
UPDATE sys_dict_data SET dict_value='1', description='医疗性别-男' WHERE tenant_id=1 AND dict_type='med_sex' AND dict_label='男';
UPDATE sys_dict_data SET dict_value='2', description='医疗性别-女' WHERE tenant_id=1 AND dict_type='med_sex' AND dict_label='女';
UPDATE sys_dict_data SET dict_value='0', description='医疗性别-未知' WHERE tenant_id=1 AND dict_type='med_sex' AND dict_label='未知';

COMMIT;
