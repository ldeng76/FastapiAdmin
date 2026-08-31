<!-- 登录页：1:1 复刻原型 01 —— 左暗「数据指挥中心」+ 右亮「账号密码表单卡」 -->
<template>
  <div class="lnrs-login">
    <!-- ============ 左侧 数据指挥中心 ============ -->
    <section class="left">
      <div class="brand">
        <div class="logo">LNRS</div>
        <div>
          <h1>肺结节多维度数据云平台</h1>
          <small>LUNG NODULE RESEARCH SYSTEM · v3.0</small>
        </div>
      </div>

      <div class="hero">
        <div class="eyebrow">MULTI-CENTER · MULTI-OMICS · AI-DRIVEN</div>
        <h2>以<em>多中心数据</em>为基座，<br />驱动肺结节精准科研。</h2>
        <p>
          覆盖影像、病理、随访与基因多维度数据，融合深度学习辅助标注与统计建模，
          为研究者提供从病例入组到论文产出的一体化平台。
        </p>
      </div>

      <!-- 肺 + 数据网 视觉 -->
      <svg class="lung-art" viewBox="0 0 520 520" fill="none">
        <defs>
          <radialGradient id="lg1" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stop-color="#0AC7B5" stop-opacity=".55" />
            <stop offset="100%" stop-color="#0AC7B5" stop-opacity="0" />
          </radialGradient>
          <linearGradient id="lg2" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stop-color="#1B6FA8" stop-opacity=".7" />
            <stop offset="100%" stop-color="#0AC7B5" stop-opacity=".3" />
          </linearGradient>
        </defs>
        <circle cx="260" cy="260" r="230" fill="url(#lg1)" />
        <path
          d="M260 140 C 200 150 160 200 155 280 C 150 360 185 420 230 430 C 245 425 250 400 250 370 L 250 180 C 250 160 255 145 260 140 Z"
          stroke="#0AC7B5" stroke-width="1.5" fill="url(#lg2)" fill-opacity=".25"
        />
        <path
          d="M260 140 C 320 150 360 200 365 280 C 370 360 335 420 290 430 C 275 425 270 400 270 370 L 270 180 C 270 160 265 145 260 140 Z"
          stroke="#0AC7B5" stroke-width="1.5" fill="url(#lg2)" fill-opacity=".25"
        />
        <path d="M260 80 L 260 145" stroke="#7FB8C9" stroke-width="2" />
        <path d="M260 145 C 250 160 245 175 240 195 M260 145 C 270 160 275 175 280 195" stroke="#7FB8C9" stroke-width="1.5" fill="none" />
        <g stroke="#0AC7B5" stroke-width=".8" stroke-opacity=".5" fill="none">
          <line x1="200" y1="240" x2="240" y2="270" />
          <line x1="240" y1="270" x2="290" y2="250" />
          <line x1="290" y1="250" x2="320" y2="300" />
          <line x1="190" y1="320" x2="230" y2="350" />
          <line x1="230" y1="350" x2="280" y2="370" />
          <line x1="280" y1="370" x2="330" y2="340" />
          <line x1="330" y1="340" x2="340" y2="280" />
          <line x1="200" y1="240" x2="190" y2="320" />
          <line x1="320" y1="300" x2="340" y2="280" />
        </g>
        <g fill="#0AC7B5">
          <circle cx="200" cy="240" r="3.5" /><circle cx="290" cy="250" r="4" />
          <circle cx="320" cy="300" r="3" /><circle cx="190" cy="320" r="3" />
          <circle cx="280" cy="370" r="4.5" /><circle cx="330" cy="340" r="3" />
          <circle cx="340" cy="280" r="3" />
        </g>
        <g>
          <circle cx="230" cy="350" r="9" fill="none" stroke="#FF5A5F" stroke-width="1.5" />
          <circle cx="230" cy="350" r="3" fill="#FF5A5F" />
          <line x1="230" y1="341" x2="230" y2="318" stroke="#FF5A5F" stroke-width="1" />
          <text x="230" y="310" fill="#FF5A5F" font-size="11" text-anchor="middle" font-family="monospace">8.2mm</text>
        </g>
        <g>
          <circle cx="290" cy="250" r="11" fill="none" stroke="#F59E0B" stroke-width="1.5" />
          <text x="290" y="225" fill="#F59E0B" font-size="11" text-anchor="middle" font-family="monospace">12.5mm</text>
        </g>
        <line x1="120" y1="290" x2="400" y2="290" stroke="#0AC7B5" stroke-opacity=".4" stroke-dasharray="3 3" />
        <text x="120" y="285" fill="#7FB8C9" font-size="10" font-family="monospace">CT-AX 0.625mm</text>
      </svg>

      <div class="foot">
        <div>© 2025 肺结节多维度数据云平台 · 陕ICP备2025069493号-1</div>
      </div>
    </section>

    <!-- ============ 右侧 登录表单卡 ============ -->
    <section class="right">
      <div class="form-card">
        <h3>{{ panelTitle }}</h3>
        <p class="sub">{{ panelSubTitle }}</p>

        <template v-if="authPanel === 'login'">
          <template v-if="loginFlowMode === 'account'">
            <FaLoginAccountForm
              ref="accountFormRef"
              v-model:is-passing="isPassing"
              v-model:is-click-pass="isClickPass"
              v-model:login-form="loginForm"
              :rules="rules"
              :captcha-state="captchaState"
              :code-loading="codeLoading"
              :demo-account-key="demoAccountKey"
              :accounts="accounts"
              :form-key="formKey"
              :is-dark="isDark"
              :drag-verify-text-color="dragVerifyTextColor"
              :loading="loading"
              @submit="handleSubmit"
              @setup-account="setupAccount"
              @get-captcha="getCaptcha"
              @open-mobile="openMobileLogin"
              @open-qr="openQrLogin"
              @forget="setAuthPanel('forget')"
              @register="setAuthPanel('register')"
              @oauth="handleOAuthLogin"
            />
          </template>

          <FaLoginMobilePanel
            v-else-if="loginFlowMode === 'mobile'"
            @back="backToAccountLogin"
            @register="setAuthPanel('register')"
          />

          <FaLoginQrPanel
            v-else-if="loginFlowMode === 'qr'"
            @back="backToAccountLogin"
            @register="setAuthPanel('register')"
          />
        </template>

        <FaLoginRegisterPanel
          v-else-if="authPanel === 'register'"
          ref="registerPanelRef"
          v-model:register-agreement-read="registerAgreementRead"
          v-model:register-form="registerForm"
          :register-rules="registerRules"
          :form-key="formKey"
          :register-loading="registerLoading"
          :user-agreement-href="userAgreementHref"
          @submit="submitRegister"
          @to-login="setAuthPanel('login')"
        />

        <FaLoginForgetPanel
          v-else
          ref="forgetPanelRef"
          v-model:forget-form="forgetForm"
          :forget-rules="forgetRules"
          :form-key="formKey"
          :forget-loading="forgetLoading"
          @submit="submitForget"
          @to-login="setAuthPanel('login')"
        />
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import type { LocationQuery, RouteLocationRaw } from "vue-router";
import AuthAPI, {
  type CaptchaInfo,
  type LoginFormData,
  type OAuthProvider,
} from "@/api/module_system/auth";
import UserAPI, { type ForgetPasswordForm, type RegisterForm } from "@/api/module_system/user";
import { useConfigStore, useAppStore, useSettingsStore, useUserStore } from "@stores";
import { Auth, HttpError, startOAuthLogin } from "@utils";
import { ElMessage, ElNotification, type FormRules } from "element-plus";
import type { Account, AccountKey } from "./types";
import FaLoginAccountForm from "@/components/views/fa-login/FaLoginAccountForm.vue";
import FaLoginForgetPanel from "@/components/views/fa-login/FaLoginForgetPanel.vue";
import FaLoginMobilePanel from "@/components/views/fa-login/FaLoginMobilePanel.vue";
import FaLoginQrPanel from "@/components/views/fa-login/FaLoginQrPanel.vue";
import FaLoginRegisterPanel from "@/components/views/fa-login/FaLoginRegisterPanel.vue";

defineOptions({ name: "Login" });

type AuthPanel = "login" | "register" | "forget";

/** 登录区内：账号密码 ↔ 手机号 ↔ 扫码（扫码 / 手机号为演示交互） */
type LoginFlowMode = "account" | "mobile" | "qr";

const configStore = useConfigStore();
const settingStore = useSettingsStore();
const appStore = useAppStore();
const { isDark } = storeToRefs(settingStore);
const { t, locale } = useI18n();

const authPanel = ref<AuthPanel>("login");
const loginFlowMode = ref<LoginFlowMode>("account");

const panelTitle = computed(() => {
  if (authPanel.value === "register") return t("login.reg");
  if (authPanel.value === "forget") return t("login.resetPassword");
  if (
    authPanel.value === "login" &&
    (loginFlowMode.value === "mobile" || loginFlowMode.value === "qr")
  ) {
    return t("login.qrLoginTitle");
  }
  return t("login.title");
});

const panelSubTitle = computed(() => {
  if (authPanel.value === "register") return t("register.subTitle");
  if (authPanel.value === "forget") return t("forgetPassword.subTitle");
  if (authPanel.value === "login" && loginFlowMode.value === "mobile") {
    return t("login.mobileLoginSubTitle");
  }
  if (authPanel.value === "login" && loginFlowMode.value === "qr") {
    return t("login.qrLoginSubTitle");
  }
  return t("login.subTitle");
});

const userAgreementHref = computed(
  () => configStore.configData?.tenant_clause?.config_value || "#"
);

function setAuthPanel(panel: AuthPanel) {
  authPanel.value = panel;
  if (panel !== "login") {
    loginFlowMode.value = "account";
  }
  nextTick(() => {
    accountFormRef.value?.clearValidate?.();
    registerPanelRef.value?.clearValidate?.();
    forgetPanelRef.value?.clearValidate?.();
  });
}

function openMobileLogin() {
  loginFlowMode.value = "mobile";
}

function openQrLogin() {
  loginFlowMode.value = "qr";
}

function backToAccountLogin() {
  loginFlowMode.value = "account";
  nextTick(() => {
    getCaptcha();
    loginForm.captcha = "";
    accountFormRef.value?.resetDragVerify?.();
    isPassing.value = false;
    isClickPass.value = false;
  });
}

function handleOAuthLogin(provider: OAuthProvider) {
  startOAuthLogin(provider);
}

async function tryConsumeOAuthCallback() {
  const q = route.query;
  const oauthError = q.oauth_error as string | undefined;
  const access = q.access_token as string | undefined;
  const refresh = q.refresh_token as string | undefined;

  if (!oauthError && !(access && refresh)) return;

  const rest: Record<string, unknown> = { ...q };
  delete rest.oauth_error;
  delete rest.access_token;
  delete rest.refresh_token;
  delete rest.token_type;

  if (oauthError) {
    ElMessage.error(decodeURIComponent(oauthError));
    await router.replace({ path: route.path, query: rest as LocationQuery });
    return;
  }

  if (access && refresh) {
    try {
      Auth.setTokens(access, refresh, true);
      userStore.setToken(access, refresh);
      userStore.setLoginStatus(true);
      ElNotification({
        title: t("login.oauthNoticeTitle"),
        message: t("login.oauthLoginSuccess"),
        type: "success",
      });
      await router.replace(resolveRedirectTarget(rest as LocationQuery));
      if (settingStore.showGuide) {
        appStore.showGuide(true);
      }
    } catch (error) {
      console.error("[Login] OAuth callback:", error);
      ElMessage.error(t("login.oauthLoginFailed"));
      await router.replace({ path: route.path, query: rest as LocationQuery });
    }
  }
}

const dragVerifyTextColor = computed(() =>
  isDark.value ? "rgba(255, 255, 255, 0.45)" : "var(--fa-gray-700)"
);
const formKey = ref(0);

watch(locale, () => {
  formKey.value++;
});

watch(authPanel, (panel) => {
  if (panel !== "login") return;
  if (loginFlowMode.value !== "account") return;
  getCaptcha();
  loginForm.captcha = "";
  accountFormRef.value?.resetDragVerify?.();
  isPassing.value = false;
  isClickPass.value = false;
});

const accounts = computed<Account[]>(() => [
  {
    key: "super",
    label: t("login.roles.super"),
    username: "super",
    password: "123456",
    roles: ["R_SUPER"],
  },
  {
    key: "admin",
    label: t("login.roles.admin"),
    username: "admin",
    password: "123456",
    roles: ["R_ADMIN"],
  },
  {
    key: "user",
    label: t("login.roles.user"),
    username: "user",
    password: "123456",
    roles: ["R_USER"],
  },
]);

const demoAccountKey = ref<AccountKey>("super");
const userStore = useUserStore();
const router = useRouter();
const route = useRoute();
const isPassing = ref(import.meta.env.DEV);
const isClickPass = ref(false);

const accountFormRef = ref<InstanceType<typeof FaLoginAccountForm> | null>(null);
const registerPanelRef = ref<InstanceType<typeof FaLoginRegisterPanel> | null>(null);
const forgetPanelRef = ref<InstanceType<typeof FaLoginForgetPanel> | null>(null);

const loading = ref(false);
const registerLoading = ref(false);
const forgetLoading = ref(false);
const codeLoading = ref(false);

const registerAgreementRead = ref(false);

const registerForm = reactive<RegisterForm>({
  username: "",
  password: "",
  confirmPassword: "",
});

const forgetForm = reactive<ForgetPasswordForm>({
  username: "",
  new_password: "",
  confirmPassword: "",
});

const validateRegisterPassword = (_rule: unknown, value: string, callback: (e?: Error) => void) => {
  if (!value) {
    callback(new Error(t("login.message.password.required")));
    return;
  }
  if (registerForm.confirmPassword) {
    registerPanelRef.value?.validateField?.("confirmPassword");
  }
  callback();
};

const validateRegisterConfirm = (_rule: unknown, value: string, callback: (e?: Error) => void) => {
  if (!value) {
    callback(new Error(t("login.message.password.required")));
    return;
  }
  if (value !== registerForm.password) {
    callback(new Error(t("login.message.password.inconformity")));
    return;
  }
  callback();
};

const registerRules = computed<FormRules<RegisterForm>>(() => ({
  username: [{ required: true, message: t("login.message.username.required"), trigger: "blur" }],
  password: [
    { required: true, validator: validateRegisterPassword, trigger: "blur" },
    { min: 6, message: t("login.message.password.min"), trigger: "blur" },
  ],
  confirmPassword: [
    { required: true, message: t("login.message.password.required"), trigger: "blur" },
    { min: 6, message: t("login.message.password.min"), trigger: "blur" },
    { validator: validateRegisterConfirm, trigger: "blur" },
  ],
}));

const validateForgetConfirm = (_rule: unknown, value: string, callback: (e?: Error) => void) => {
  if (!value) {
    callback(new Error(t("login.message.password.required")));
    return;
  }
  if (value !== forgetForm.new_password) {
    callback(new Error(t("login.message.password.inconformity")));
    return;
  }
  callback();
};

const forgetRules = computed<FormRules<ForgetPasswordForm>>(() => ({
  username: [{ required: true, message: t("login.message.username.required"), trigger: "blur" }],
  new_password: [
    { required: true, message: t("login.message.password.required"), trigger: "blur" },
    { min: 6, message: t("login.message.password.min"), trigger: "blur" },
  ],
  confirmPassword: [
    { required: true, message: t("login.message.password.required"), trigger: "blur" },
    { min: 6, message: t("login.message.password.min"), trigger: "blur" },
    { validator: validateForgetConfirm, trigger: "blur" },
  ],
}));

const loginForm = reactive<LoginFormData>({
  username: "",
  password: "",
  captcha: "",
  captcha_key: "",
  remember: true,
  login_type: "PC端",
});

const captchaState = reactive<CaptchaInfo>({
  enable: false,
  mode: "image",
  key: "",
  img_base: "",
  challenge: "",
  expire_seconds: 0,
});

const rules = computed<FormRules>(() => {
  const base: FormRules = {
    username: [
      {
        required: true,
        trigger: "blur",
        message: t("login.message.username.required"),
      },
    ],
    password: [
      {
        required: true,
        trigger: "blur",
        message: t("login.message.password.required"),
      },
      {
        min: 6,
        message: t("login.message.password.min"),
        trigger: "blur",
      },
    ],
  };
  // 图片验证码模式下：captcha 字段必填；ALTCHA 模式下：captcha 由 widget@statechange 事件填充，
  // 提交前通过 isPassing 做语义校验（captcha 本身是表单字段，保持非空校验更稳）。
  if (captchaState.enable) {
    base.captcha = [
      {
        required: true,
        trigger: "blur",
        message:
          captchaState.mode === "altcha"
            ? "请完成人机验证"
            : t("login.message.captchaCode.required"),
      },
    ];
  }
  return base;
});

function setupAccount(key: AccountKey) {
  const selected = accounts.value.find((a: Account) => a.key === key);
  demoAccountKey.value = key;
  loginForm.username = selected?.username ?? "";
  loginForm.password = selected?.password ?? "";
}

async function getCaptcha() {
  try {
    codeLoading.value = true;
    const response = await AuthAPI.getCaptcha();
    const data = response.data.data;
    loginForm.captcha_key = data.key ?? "";
    loginForm.captcha = data.mode === "altcha" ? "" : loginForm.captcha;
    captchaState.img_base = data.img_base ?? "";
    captchaState.enable = data.enable;
    captchaState.mode = data.mode ?? "image";
    captchaState.challenge = data.challenge ?? "";
    captchaState.expire_seconds = data.expire_seconds ?? 0;

    // ALTCHA：challenge 更新后通知子组件重置本地状态
    if (data.mode === "altcha") {
      nextTick(() => {
        accountFormRef.value?.resetAltcha?.();
      });
    }
  } catch {
    captchaState.enable = false;
    loginForm.captcha = "";
    loginForm.captcha_key = "";
    captchaState.challenge = "";
  } finally {
    codeLoading.value = false;
  }
}

function resolveRedirectTarget(query: LocationQuery): RouteLocationRaw {
  const defaultPath = "/";
  const rawRedirect = (query.redirect as string) || defaultPath;
  try {
    const resolved = router.resolve(rawRedirect);
    return {
      path: resolved.path,
      query: resolved.query,
    };
  } catch {
    return { path: defaultPath };
  }
}

onMounted(async () => {
  await configStore.getConfig(true);
  await tryConsumeOAuthCallback();
  if (userStore.isLogin) {
    await router.replace(resolveRedirectTarget(route.query));
    return;
  }
  await getCaptcha();
  // 未启用验证码 → 跳过滑块/人机验证（isPassing=true）
  // image 模式下已启用验证码但走的是图片验证码（非滑块模式在表单上方），保持 isPassing=true 避免滑块挡住
  // altcha 模式下 isPassing 由 widget 的 verified 事件控制，不能默认放行
  if (!captchaState.enable || captchaState.mode === "image") {
    isPassing.value = true;
  }
});

onActivated(() => {
  if (authPanel.value !== "login" || loginFlowMode.value !== "account") return;
  getCaptcha();
  loginForm.captcha = "";
});

watch(
  () => route.fullPath,
  () => {
    if (authPanel.value !== "login" || loginFlowMode.value !== "account") return;
    getCaptcha();
    loginForm.captcha = "";
  }
);

const handleSubmit = async () => {
  if (!accountFormRef.value) return;

  try {
    const valid = await accountFormRef.value.validate?.();
    if (!valid) return;

    if (!isPassing.value) {
      isClickPass.value = true;
      return;
    }

    loading.value = true;

    await userStore.login(loginForm);

    // 多租户：读取登录响应中的租户列表
    const tenants = userStore.tenantList;
    if (tenants.length > 1) {
      await router.replace({
        name: "TenantSelect",
        query: { redirect: route.query.redirect as string },
      });
    } else if (tenants.length === 1) {
      await userStore.setCurrentTenant(tenants[0]);
      await router.replace(resolveRedirectTarget(route.query));
    } else {
      await router.replace(resolveRedirectTarget(route.query));
    }

    if (settingStore.showGuide) {
      appStore.showGuide(true);
    }
  } catch (error) {
    await getCaptcha();
    if (!(error instanceof HttpError)) {
      console.error("[Login] Unexpected error:", error);
      let errorMsg:any = error instanceof Error ? error.message : error;
      if(errorMsg != null && typeof errorMsg === 'object'){
        for(let key in errorMsg){
          errorMsg = errorMsg[key]?.[0]?.message || ''
          break;
        }
      } else {
        errorMsg = String(errorMsg)
      }

      ElNotification({
        title: "提示",
        message: errorMsg,
        type: "error",
      });
    }
  } finally {
    loading.value = false;
    accountFormRef.value?.resetDragVerify?.();
  }
};

async function submitRegister() {
  if (!registerAgreementRead.value) {
    ElMessage.warning(t("login.message.agree.required"));
    return;
  }
  if (!registerPanelRef.value) return;
  try {
    await registerPanelRef.value.validate?.();
    registerLoading.value = true;
    await UserAPI.registerUser(registerForm);
    loginForm.username = registerForm.username;
    loginForm.password = registerForm.password;
    registerForm.username = "";
    registerForm.password = "";
    registerForm.confirmPassword = "";
    registerAgreementRead.value = false;
    setAuthPanel("login");
  } catch (error) {
    console.error("[Login] register:", error);
  } finally {
    registerLoading.value = false;
  }
}

async function submitForget() {
  if (!forgetPanelRef.value) return;
  try {
    await forgetPanelRef.value.validate?.();
    forgetLoading.value = true;
    await UserAPI.forgetPassword(forgetForm);
    loginForm.username = forgetForm.username;
    loginForm.password = forgetForm.new_password;
    forgetForm.username = "";
    forgetForm.new_password = "";
    forgetForm.confirmPassword = "";
    setAuthPanel("login");
  } catch (error) {
    console.error("[Login] forget password:", error);
  } finally {
    forgetLoading.value = false;
  }
}
</script>

<style scoped lang="scss">
/* ===== 整体：左暗 / 右亮 分屏（原型 01） ===== */
.lnrs-login {
  display: grid;
  grid-template-columns: 1.05fr 1fr;
  min-height: 100vh;
  background: var(--lnrs-bg);
}

/* ===== 左侧：数据指挥中心 ===== */
.left {
  position: relative;
  background: linear-gradient(160deg, #081d33 0%, #0a2540 45%, #0e3358 100%);
  color: #fff;
  padding: 44px 56px;
  overflow: hidden;
}
.left::before {
  content: "";
  position: absolute;
  inset: 0;
  background-image: linear-gradient(rgba(255, 255, 255, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.04) 1px, transparent 1px);
  background-size: 44px 44px;
  -webkit-mask-image: radial-gradient(ellipse at 50% 40%, #000 30%, transparent 75%);
  mask-image: radial-gradient(ellipse at 50% 40%, #000 30%, transparent 75%);
}
.left::after {
  content: "";
  position: absolute;
  right: -180px;
  top: -180px;
  width: 520px;
  height: 520px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(0, 181, 165, 0.18), transparent 60%);
}
.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  position: relative;
  z-index: 2;
}
.logo {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  background: linear-gradient(135deg, #0ac7b5, #0a2540);
  display: grid;
  place-items: center;
  font-weight: 800;
  letter-spacing: 1px;
  font-size: 11px;
  box-shadow: 0 6px 18px rgba(10, 199, 181, 0.35);
}
.brand h1 {
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 1px;
  margin: 0;
}
.brand small {
  display: block;
  font-size: 11px;
  color: #7fb8c9;
  letter-spacing: 3px;
  margin-top: 2px;
  font-weight: 400;
}
.hero {
  position: relative;
  z-index: 2;
  margin-top: 72px;
  max-width: 520px;
}
.hero .eyebrow {
  font-size: 12px;
  color: var(--lnrs-teal-2);
  letter-spacing: 4px;
  font-weight: 500;
}
.hero h2 {
  font-size: 38px;
  line-height: 1.25;
  margin: 14px 0 16px;
  font-weight: 600;
  letter-spacing: 0.5px;
}
.hero h2 em {
  font-style: normal;
  color: var(--lnrs-teal-2);
}
.hero p {
  color: #9fb3c8;
  font-size: 14px;
  line-height: 1.8;
  max-width: 440px;
}
.lung-art {
  position: absolute;
  right: -40px;
  bottom: 30px;
  width: 520px;
  height: 520px;
  z-index: 1;
  opacity: 0.95;
}
.foot {
  position: absolute;
  left: 56px;
  bottom: 32px;
  right: 56px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  z-index: 2;
  font-size: 11px;
  color: #6b8aa0;
  letter-spacing: 1px;
}
.foot .dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--lnrs-teal-2);
  box-shadow: 0 0 8px var(--lnrs-teal-2);
  margin-right: 8px;
  animation: pulse 2s infinite;
}
@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.4;
  }
}

/* ===== 右侧：表单卡 ===== */
.right {
  display: grid;
  place-items: center;
  padding: 40px;
  background: var(--lnrs-bg);
  position: relative;
}
.form-card {
  width: 100%;
  max-width: 400px;
  background: #fff;
  border-radius: 14px;
  padding: 40px 36px;
  box-shadow: 0 1px 2px rgba(10, 37, 64, 0.06), 0 8px 24px rgba(10, 37, 64, 0.06);
  border: 1px solid var(--lnrs-line-2);
}
.form-card h3 {
  font-size: 22px;
  font-weight: 600;
  letter-spacing: 0.5px;
  margin: 0;
}
.form-card .sub {
  margin-top: 8px;
  font-size: 13.5px;
  color: var(--lnrs-ink-2);
}
.form-card .sub b {
  color: var(--lnrs-navy);
  font-weight: 600;
}

/* 表单控件：44px 高、圆角 8、focus 青边（对齐原型） */
.form-card :deep(.el-form-item) {
  margin-bottom: 20px;
}
.form-card :deep(.el-input__wrapper),
.form-card :deep(.el-input__wrapper.is-focus) {
  height: 44px;
  border-radius: 8px;
  padding: 0 14px;
  box-shadow: 0 0 0 1px var(--lnrs-line) inset;
}
.form-card :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px var(--lnrs-teal) inset, 0 0 0 3px rgba(0, 181, 165, 0.12);
}
.form-card :deep(.el-input__prefix) {
  color: var(--lnrs-ink-3);
}
.form-card :deep(.el-input__inner) {
  font-size: 14px;
  color: var(--lnrs-navy);
}
/* 验证码图片框 */
.form-card :deep(.login-captcha-img) {
  height: 44px;
  border: 1px solid var(--lnrs-line);
  border-radius: 8px;
}
/* 滑块区域 */
.form-card :deep(.login-form-tail) {
  margin-top: 4px;
}
.form-card :deep(.login-form-tail .flex.relative.pb-3) {
  margin-bottom: 8px;
}
/* 忘记密码行 */
.form-card :deep(.login-options-row) {
  margin: 2px 0 18px;
}
.form-card :deep(.login-options-row .el-link) {
  color: var(--lnrs-teal);
}
/* 登录按钮：46px 渐变（对齐原型） */
.form-card :deep(.el-button--primary) {
  height: 46px;
  border-radius: 8px;
  background: linear-gradient(135deg, #0ac7b5, #0a2540);
  border: none;
  font-size: 15px;
  letter-spacing: 4px;
  font-weight: 500;
  box-shadow: 0 6px 18px rgba(10, 199, 181, 0.3);
}
.form-card :deep(.el-button--primary:hover) {
  background: linear-gradient(135deg, #0ed4c2, #0a2540);
  transform: translateY(-1px);
}

/* 右上 帮助/语言 */
.top-links {
  position: absolute;
  top: 24px;
  right: 32px;
  display: flex;
  gap: 18px;
  font-size: 12px;
  color: var(--lnrs-ink-2);
  z-index: 3;
}
.top-links a {
  color: var(--lnrs-ink-2);
  text-decoration: none;
}
.top-links a:hover {
  color: var(--lnrs-teal);
}

@media (max-width: 960px) {
  .lnrs-login {
    grid-template-columns: 1fr;
  }
  .left {
    display: none;
  }
}
</style>
