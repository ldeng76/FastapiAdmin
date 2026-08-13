import {DictDataTable} from "@api/module_system/dict.ts";

export interface FilterDictDataTable extends DictDataTable{
  key?: string;
  children?: Array<FilterConfigType | FilterDictDataTable>
}
export interface FilterConfigType {
  dict_label: string;
  dict_type: string;
  name?:string,
  dict_value?: string;
  key?: string;
  currFilter?:string | undefined;
  currFilterText?:string | undefined;
  children?: Array<FilterDictDataTable>;
}

const config: Array<FilterConfigType> = [
  {
    dict_label: "患者性别",
    dict_type:"med_sex",
    name :"gender",
    children: [],
  },
  {
    dict_label: "患者年龄段",
    dict_type:"med_age",
    name :"age_bucket",
    children: [],
  },
  {
    dict_label: "患者ABO血型",
    dict_type:"med_blood_type_abo",
    name :"abo_blood_type",
    children: [],
  },
  {
    dict_label: "患者RH血型",
    dict_type:"med_blood_type_rh",
    name :"rh_blood_type",
    children: [],
  },
  {
    dict_label: "患者吸烟情况",
    dict_type:"med_smoking_status",
    name :"smoking_status",
    children: [],
  },
  {
    dict_label: "检查模态",
    dict_type:"med_exam_type",
    name :"modality",
    children: [],
  }
]

addConfigKey(config, null);

export function addConfigKey(arr: Array<FilterDictDataTable>, key: string | null) {
  arr.forEach(function (item: (FilterDictDataTable), i) {
    if (!item.key) item.key = key != null ? key + "-" + i.toString() : i.toString();
    addConfigKey(item.children || [], item.key);
  });
}
export default config;
