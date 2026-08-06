import type { App } from "vue";
import { createRouter, createWebHashHistory } from "vue-router";
import { HOME_ROUTE_NAME, ROOT_LAYOUT_ROUTE_NAME, staticRoutes } from "./staticRoutes";
import { setupAfterEachGuard } from "./afterEach";
import "@utils/ui";

/**
 * 路由入口：`staticRoutes` 首屏注册；业务路由由 `beforeEach` 内 `RouteRegistry` 动态挂载。
 * `initRouter` 注册前置/后置守卫并 `app.use(router)`。
 *
 * 选择 Hash 模式（createWebHashHistory）而非 History 模式的原因：
 * - 纯静态部署场景下无需服务端 URL 回落配置（NGINX try_files 等）
 * - 兼容 Electron 等非 HTTP 协议环境
 * - 开发环境 HMR 不受影响
 */

/**
 * 解析 hash 路由的 base：从 `VITE_BASE_URL` 读取（与 Vite 构建/部署子路径对齐），
 * 缺省 `/`。注意 vue-router 4 的 `createWebHashHistory(base)` 期望 base 以 `/` 结尾，
 * 因此对原始 `'/web'` 之类补正为 `'/web/'`，避免 `to.path` 被意外加上 `/web` 前缀。
 *
 * 历史背景：路由引入时未传 base，部署在子路径 `/web` 下访问 `#/medical/patient`
 * 时 vue-router 内部仍能正确解析，但首屏守卫走到的 "兜底 `CatchAll404`" 路径
 * 会被 `to.matched.length > 0` 命中（pathMatch 通配），导致 404 页面闪现。
 * 显式传 base 后，子路由注册时序与 base 一致，守卫判定稳定。
 */
function resolveHashHistoryBase(): string {
  const raw = ((import.meta.env.VITE_BASE_URL as string | undefined) || "/").trim();
  // 兜底确保以 `/` 起始与 `/` 结尾（vue-router 内部要求）
  if (!raw.startsWith("/")) return "/";
  return raw.endsWith("/") ? raw : `${raw}/`;
}

export const router = createRouter({
  history: createWebHashHistory(resolveHashHistoryBase()),
  routes: staticRoutes,
  scrollBehavior: () => ({ left: 0, top: 0 }),
});

export async function initRouter(app: App<Element>): Promise<void> {
  const { setupBeforeEachGuard } = await import("./beforeEach");
  setupBeforeEachGuard(router);
  setupAfterEachGuard(router);
  app.use(router);
}

/** 须与 `staticRoutes` 首页子路由 path 一致 */
export const HOME_PAGE_PATH = "/home";

export { HOME_ROUTE_NAME, ROOT_LAYOUT_ROUTE_NAME };

/** 动态路由注册与菜单转换（一般从 `@/router` 按需导入） */
export { RouteRegistry, ComponentLoader, RouteTransformer, RouteValidator } from "./dynamicRoutes";
export type { ValidationResult } from "./dynamicRoutes";
export { IframeRouteManager } from "./staticRoutes";
export { MenuProcessor, builtinFrontendRoutes } from "./MenuProcessor";
