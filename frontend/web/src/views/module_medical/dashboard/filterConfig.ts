import {DictDataTable} from "@api/module_system/dict.ts";
export interface FilterDictDataTable extends DictDataTable{
  key?: string;
  children?: Array<FilterConfigType | FilterDictDataTable>
}
export interface FilterConfigType {
  dict_label: string;
  dict_type: string;
  dict_value?: string;
  key?: string;
  currFilter?:string | undefined;
  currFilterText?:string | undefined;
  children?: Array<FilterConfigType | FilterDictDataTable>;
}

const config: Array<FilterConfigType> = [
  {
    dict_label: "来源中心",
    dict_type:"med_center",
    children: [],
  },
  {
    dict_label: "性别",
    dict_type:"med_sex",
    children: [],
  },
  {
    dict_label: "年龄",
    dict_type:"med_age",
    children: [
      {dict_label :"0岁-10岁",dict_value:"10"},
      {dict_label :"11岁-20岁",dict_value:"20"},
      {dict_label :"21岁-30岁",dict_value:"30"},
      {dict_label :"31岁-40岁",dict_value:"40"},
      {dict_label :"51岁以上",dict_value:"50"},
    ],
  },
  {
    dict_label: "吸烟状态",
    dict_type:"med_smoking_status",
    children: [],
  },
  {
    dict_label: "病理类型",
    dict_type:"med_exam_type",
    children: [],
  },
  {
    dict_label: "偏侧性",
    dict_type:"med_laterality",
    children: [],
  },
];

addConfigKey(config, null);

export function addConfigKey(arr: Array<FilterConfigType | FilterDictDataTable>, key: string | null) {
  arr.forEach(function (item: (FilterConfigType | FilterDictDataTable), i) {
    if (!item.key) item.key = key != null ? key + "-" + i.toString() : i.toString();
    addConfigKey(item.children || [], item.key);
  });
}
export default config;
