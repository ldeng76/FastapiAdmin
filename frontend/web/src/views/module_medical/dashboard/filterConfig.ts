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
    dict_label: "来源中心",
    dict_type:"med_center",
    name :"center",
    children: [],
  },
  {
    dict_label: "性别",
    dict_type:"med_sex",
    name :"gender",
    children: [],
  },
  {
    dict_label: "年龄段",
    dict_type:"med_age",
    name :"age_bucket",
    children: [],
  },
  {
    dict_label: "吸烟状态",
    dict_type:"med_smoking_status",
    name :"smoking",
    children: [],
  },
  {
    dict_label: "模态",
    dict_type:"med_exam_type",
    name :"modality",
    children: [],
  },
  {
    dict_label: "偏侧性",
    dict_type:"med_laterality",
    name :"exam_laterality",
    children: [],
  },
];

addConfigKey(config, null);

export function addConfigKey(arr: Array<FilterDictDataTable>, key: string | null) {
  arr.forEach(function (item: (FilterDictDataTable), i) {
    if (!item.key) item.key = key != null ? key + "-" + i.toString() : i.toString();
    addConfigKey(item.children || [], item.key);
  });
}
export default config;
