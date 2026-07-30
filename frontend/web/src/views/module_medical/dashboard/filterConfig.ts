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
  children?: Array<FilterDictDataTable>;
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
    dict_label: "年龄段",
    dict_type:"med_age",
    children: [
      {dict_label :"0岁-39岁",dict_value:"0"},
      {dict_label :"40岁-49岁",dict_value:"40"},
      {dict_label :"50岁-59岁",dict_value:"50"},
      {dict_label :"60岁-69岁",dict_value:"60"},
      {dict_label :"70岁-79岁",dict_value:"70"},
      {dict_label :"80岁以上",dict_value:"80"},
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

export function addConfigKey(arr: Array<FilterDictDataTable>, key: string | null) {
  arr.forEach(function (item: (FilterDictDataTable), i) {
    if (!item.key) item.key = key != null ? key + "-" + i.toString() : i.toString();
    addConfigKey(item.children || [], item.key);
  });
}
export default config;
