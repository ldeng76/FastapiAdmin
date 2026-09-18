/**
 * dict.store 持久化缓存过期（1 小时 TTL）行为测试
 *
 * 背景：字典 store 通过 pinia persist 存入 localStorage，旧实现一旦缓存即永不再请求，
 * 服务端字典变更后浏览器会一直展示旧选项。现加入 1 小时过期，过期后 getDict 自动重拉。
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { createPinia, setActivePinia } from "pinia";

// "@stores" 会拉起整个 store 聚合入口（含 router 等副作用），测试里直接桩掉
vi.mock("@stores", () => ({ store: {} }));

const getInitDict = vi.fn();
vi.mock("@/api/module_system/dict", () => ({
  default: {
    getInitDict: (...args: unknown[]) => getInitDict(...args),
  },
}));

const { useDictStore } = await import("../dict.store");

const DICT_CACHE_TTL = 60 * 60 * 1000;

function mockDictResponse(items: Array<{ dict_value: string; dict_label: string }>) {
  return { data: { data: items } };
}

describe("dictStore 缓存过期", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    getInitDict.mockReset();
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-18T10:00:00Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("TTL 内重复 getDict 不再请求接口", async () => {
    getInitDict.mockResolvedValue(mockDictResponse([{ dict_value: "CT", dict_label: "CT" }]));
    const store = useDictStore();

    await store.getDict(["med_exam_type"]);
    await store.getDict(["med_exam_type"]);

    expect(getInitDict).toHaveBeenCalledTimes(1);
  });

  it("超过 TTL 后 getDict 清空旧缓存并重新拉取", async () => {
    getInitDict.mockResolvedValue(mockDictResponse([{ dict_value: "CT", dict_label: "CT" }]));
    const store = useDictStore();
    await store.getDict(["med_exam_type"]);
    expect(getInitDict).toHaveBeenCalledTimes(1);

    // 时间前进到 TTL 之后
    vi.setSystemTime(new Date(Date.now() + DICT_CACHE_TTL + 1));

    await store.getDict(["med_exam_type"]);
    expect(getInitDict).toHaveBeenCalledTimes(2);
  });

  it("过期重拉后返回的是服务端最新值", async () => {
    getInitDict.mockResolvedValueOnce(
      mockDictResponse([{ dict_value: "Pathology", dict_label: "病理" }])
    );
    const store = useDictStore();
    const first = await store.getDict(["med_exam_type"], true);
    expect(first["med_exam_type"]).toEqual([{ label: "病理", value: "Pathology" }]);

    getInitDict.mockResolvedValueOnce(
      mockDictResponse([{ dict_value: "pathology_text", dict_label: "病理报告" }])
    );
    vi.setSystemTime(new Date(Date.now() + DICT_CACHE_TTL + 1));

    const second = await store.getDict(["med_exam_type"], true);
    expect(second["med_exam_type"]).toEqual([{ label: "病理报告", value: "pathology_text" }]);
  });

  it("clearDictData 同时重置过期时间戳", async () => {
    getInitDict.mockResolvedValue(mockDictResponse([{ dict_value: "CT", dict_label: "CT" }]));
    const store = useDictStore();
    await store.getDict(["med_exam_type"]);
    expect(store.cachedAt).toBeGreaterThan(0);

    store.clearDictData();
    expect(store.cachedAt).toBe(0);
    expect(store.dictData["med_exam_type"]).toBeUndefined();
  });
});
