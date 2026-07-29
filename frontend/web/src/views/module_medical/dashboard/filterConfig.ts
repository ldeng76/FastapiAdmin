export interface FilterConfigType {
  label: string;
  value?: string;
  key?: string;
  currFilter?:string | undefined;
  currFilterText?:string | undefined;
  children?: Array<FilterConfigType>;
}

const config: Array<FilterConfigType> = [
  {
    label: "来源中心",
    children: [],
  },
  {
    label: "性别",
    children: [],
  },
  {
    label: "年龄访问",
    children: [],
  },
  {
    label: "吸烟状态",
    children: [],
  },
  {
    label: "病理类型",
    children: [],
  },
  {
    label: "基因突变",
    children: [],
  },
  {
    label: "随访状态",
    children: [],
  },
];

addConfigKey(config, null);

export function addConfigKey(arr: Array<FilterConfigType>, key: string | null) {
  arr.forEach(function (item: FilterConfigType, i) {
    if (!item.key) item.key = key != null ? key + "-" + i.toString() : i.toString();
    addConfigKey(item.children || [], item.key);
  });
}
export default config;
