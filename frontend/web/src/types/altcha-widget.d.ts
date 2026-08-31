// ALTCHA 自定义元素（@altcha-lib/web-component）：注册到全局 JSX.IntrinsicElements / HTMLElementTagNameMap
// 让 TS + Vue 模板都能识别 <altcha-widget>。
interface AltchaWidgetStateDetail {
  state: "idle" | "verifying" | "verified" | "error" | "expired";
  payload?: string;
  challenge?: string;
}

interface AltchaWidgetEventMap {
  statechange: CustomEvent<AltchaWidgetStateDetail>;
  verified: CustomEvent<{ payload: string }>;
  error: CustomEvent<{ message: string }>;
  expired: CustomEvent;
}

interface AltchaWidgetElement extends HTMLElement {
  // props (HTML attribute / property)
  challenge: string;
  expire?: number;
  hideFooter?: boolean;
  strings?: Record<string, string>;
  stringsUrl?: string;
  // imperative API
  reset(): void;
  state: AltchaWidgetStateDetail["state"];
  addEventListener<K extends keyof AltchaWidgetEventMap>(
    type: K,
    listener: (this: HTMLElement, ev: AltchaWidgetEventMap[K]) => any,
    options?: boolean | AddEventListenerOptions,
  ): void;
  addEventListener(
    type: string,
    listener: EventListenerOrEventListenerObject,
    options?: boolean | AddEventListenerOptions,
  ): void;
  removeEventListener<K extends keyof AltchaWidgetEventMap>(
    type: K,
    listener: (this: HTMLElement, ev: AltchaWidgetEventMap[K]) => any,
    options?: boolean | EventListenerOptions,
  ): void;
  removeEventListener(
    type: string,
    listener: EventListenerOrEventListenerObject,
    options?: boolean | EventListenerOptions,
  ): void;
}

declare global {
  interface HTMLElementTagNameMap {
    "altcha-widget": AltchaWidgetElement;
  }
  namespace JSX {
    interface IntrinsicElements {
      "altcha-widget": Partial<AltchaWidgetElement> & { onStatechange?: (e: AltchaWidgetEventMap["statechange"]) => void };
    }
  }
}

declare module "altcha" {
  // 该包仅作为 side effect 引入（在 window 下注册 <altcha-widget> 自定义元素），不导出 JS API。
  const register: () => void;
  export default register;
}

export {};
