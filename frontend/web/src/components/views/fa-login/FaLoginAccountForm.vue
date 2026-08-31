<!-- 账号密码登录表单（含快捷账号、验证码、滑块） -->
<template>
  <div>
    <ElForm
      ref="formRef"
      :model="loginForm"
      :rules="rules"
      :key="formKey"
      class="login-page-form"
      autocomplete="off"
      :validate-on-rule-change="false"
      @keyup.enter="$emit('submit')"
    >


      <ElFormItem prop="username">
        <ElInput
          class="custom-height"
          v-model.trim="loginForm.username"
          clearable
          :placeholder="$t('login.placeholder.username')"
        >
          <template #prefix>
            <ElIcon><User /></ElIcon>
          </template>
        </ElInput>
      </ElFormItem>

      <ElTooltip :visible="isCapsLock" :content="$t('login.capsLock')" placement="right">
        <ElFormItem prop="password">
          <ElInput
            class="custom-height text-security-disc"
            v-model.trim="loginForm.password"
            clearable
            :placeholder="$t('login.placeholder.password')"
            @keyup="checkCapsLock"
            @keyup.enter="$emit('submit')"
          >
            <template #prefix>
              <ElIcon><Lock /></ElIcon>
            </template>
          </ElInput>
        </ElFormItem>
      </ElTooltip>

      <ElFormItem v-if="captchaState.enable" prop="captcha" class="login-captcha-row">
        <!-- image 模式：传统图片验证码 + 输入框 -->
        <div v-if="captchaState.mode !== 'altcha'" class="flex w-full items-center gap-2.5">
          <ElInput
            v-model.trim="loginForm.captcha"
            class="custom-height flex-1"
            clearable
            :placeholder="$t('login.captchaCode')"
            @keyup.enter="$emit('submit')"
          >
            <template #prefix>
              <FaSvgIcon
                icon="mdi:shield-lock-outline"
                class="size-[18px] text-(--el-text-color-secondary)"
              />
            </template>
          </ElInput>
          <div
            class="login-captcha-img flex h-10 w-[100px] shrink-0 cursor-pointer items-center justify-center overflow-hidden rounded"
            role="button"
            :title="$t('login.captchaClickHint')"
            @click="$emit('getCaptcha')"
          >
            <ElIcon v-if="codeLoading" class="is-loading" :size="20">
              <Loading />
            </ElIcon>
            <ElImage
              v-else-if="captchaState.img_base"
              class="h-full w-full object-cover"
              fit="cover"
              :src="captchaState.img_base"
            />
            <ElText v-else type="info" size="small">
              {{ $t("login.captchaClickHint") }}
            </ElText>
          </div>
        </div>

        <!-- altcha 模式：altcha-widget（PoW 人机验证） -->
        <div v-else class="w-full">
          <altcha-widget
            v-if="altchaChallengeObj"
            ref="altchaRef"
            :challenge="altchaChallengeObj"
            :language="altchaLanguage"
            :expire="captchaState.expire_seconds"
            :hide-footer="false"
            @statechange="onAltchaStateChange"
          />
          <ElSkeleton
            v-else
            :rows="2"
            animated
            :loading="codeLoading"
            class="!mb-0"
          />
          <div v-if="altchaError" class="mt-1 text-xs text-[#f56c6c]">
            {{ altchaError }}
          </div>
        </div>
      </ElFormItem>

      <div class="login-form-tail flex flex-col gap-[1.1rem]">
        <div class="relative pb-3" v-if="!captchaState.enable">
          <div
            class="relative z-2 overflow-hidden select-none rounded-lg border border-transparent tad-300"
            :class="{ 'border-[#FF4E4F]!': !isPassing && isClickPass }"
          >
            <FaDragVerify
              ref="dragVerifyRef"
              v-model:value="isPassing"
              :text="$t('login.sliderText')"
              :text-color="dragVerifyTextColor"
              :success-text="$t('login.sliderSuccessText')"
              progress-bar-bg="var(--el-color-primary)"
              :background="isDark ? '#26272F' : '#F1F1F4'"
              handler-bg="var(--default-box-color)"
            />
          </div>
          <p
            class="absolute top-0 z-1 mt-2 px-px text-xs text-[#f56c6c] tad-300"
            :class="{ 'translate-y-10': !isPassing && isClickPass }"
          >
            {{ $t("login.placeholder.slider") }}
          </p>
        </div>
        <div>
          <ElButton
            class="h-11 w-full rounded-lg! text-base font-medium"
            type="primary"
            :loading="loading"
            v-ripple
            @click="$emit('submit')"
          >
            {{ $t("login.btnText") }}
          </ElButton>
        </div>
      </div>
    </ElForm>
  </div>
</template>

<script setup lang="ts">
import { Loading, Lock, User } from "@element-plus/icons-vue";
import type { CaptchaInfo, LoginFormData } from "@/api/module_system/auth";
import type { FormRules } from "element-plus";
import type { Account, AccountKey } from "@views/module_system/auth/login/types";
// 引入 altcha-widget 自定义元素（altcha 包作为 side effect 注册 <altcha-widget>）
import "altcha";
// 载入 altcha 内置中文/英文语言包（altcha 支持 50+ 语言，按需 import）
import "altcha/i18n/zh-cn";
import "altcha/i18n/en";
import { useAppStore } from "@/store";

const loginForm = defineModel<LoginFormData>("loginForm", { required: true });

const props = defineProps<{
  rules: FormRules;
  captchaState: CaptchaInfo;
  codeLoading: boolean;
  demoAccountKey: AccountKey;
  accounts: Account[];
  formKey: number | string;
  isDark: boolean;
  dragVerifyTextColor: string;
  loading: boolean;
}>();

const isPassing = defineModel<boolean>("isPassing", { required: true });
const isClickPass = defineModel<boolean>("isClickPass", { required: true });

defineEmits<{
  submit: [];
  setupAccount: [key: AccountKey];
  getCaptcha: [];
  openMobile: [];
  openQr: [];
  forget: [];
  register: [];
  oauth: [provider: "wechat" | "qq" | "github" | "gitee"];
}>();

const formRef = ref();
const dragVerifyRef = ref<{ reset?: () => void } | null>(null);
const isCapsLock = ref(false);
const altchaRef = ref<any>(null);
const altchaError = ref("");
const appStore = useAppStore();

/**
 * 把项目语言（zh / en）映射成 altcha i18n 要求的 code（小写，区码用 -）
 * 已 import 的语言包：altcha/i18n/zh-cn、altcha/i18n/en
 */
const altchaLanguage = computed<string>(() => {
  const lang = (appStore.language ?? "zh").toLowerCase();
  if (lang.startsWith("zh")) return "zh-cn";
  return "en";
});

interface AltchaChallenge {
  algorithm: "SHA-256" | "SHA-384" | "SHA-512";
  challenge: string;
  maxnumber: number;
  salt: string;
  signature: string;
}

/**
 * 将后端返回的 base64url challenge JSON 解码成对象。
 * widget 接收到 challenge 属性为对象时会直接拿去算 PoW，
 * 不会把它当成 URL 去 fetch（之前就是因为传了字符串导致拼成 /eyJ... 的非法路径 404）。
 */
function decodeAltchaChallenge(b64?: string): AltchaChallenge | null {
  if (!b64) return null;
  try {
    // 兼容 base64url（- / _）与普通 base64
    const base64 = b64.replace(/-/g, "+").replace(/_/g, "/");
    const json = atob(base64);
    const obj = JSON.parse(json);
    if (!obj?.algorithm || !obj?.challenge || !obj?.signature) return null;
    return obj as AltchaChallenge;
  } catch {
    return null;
  }
}

const altchaChallengeObj = computed<AltchaChallenge | null>(() =>
  props.captchaState?.mode === "altcha" ? decodeAltchaChallenge(props.captchaState?.challenge) : null,
);

function checkCapsLock(event: KeyboardEvent) {
  if (event instanceof KeyboardEvent) {
    isCapsLock.value = event.getModifierState("CapsLock");
  }
}

/**
 * 处理 altcha-widget 状态变化：
 * - "verified" 时把 payload 写入 loginForm.captcha（后端作为 ALTCHA 解来校验）
 * - "error" 时清空并提示
 * - "verified" 也满足滑块 isPassing=true 语义（人机验证通过）
 */
function onAltchaStateChange(evt: any) {
  const state: string = evt?.detail?.state ?? "";
  const payload: string | undefined = evt?.detail?.payload;
  if (state === "verified" && payload) {
    altchaError.value = "";
    loginForm.value.captcha = payload;
    loginForm.value.captcha_key = "";
    isPassing.value = true;
  } else if (state === "verifying") {
    altchaError.value = "";
    loginForm.value.captcha = "";
  } else if (state === "error") {
    altchaError.value = "人机验证失败，请重试";
    loginForm.value.captcha = "";
    isPassing.value = false;
  } else {
    // idle/expired
    loginForm.value.captcha = "";
    isPassing.value = false;
  }
}

/**
 * 暴露给父组件调用的方法：
 * - validate / clearValidate：表单校验（保留）
 * - resetDragVerify：滑块重置（保留）
 * - resetAltcha：重新拉取 challenge 时重置 widget 状态
 */
function resetAltcha() {
  if (props.captchaState?.mode === "altcha") {
    loginForm.value.captcha = "";
    altchaError.value = "";
  }
}

defineExpose({
  validate: () => formRef.value?.validate?.(),
  clearValidate: () => formRef.value?.clearValidate?.(),
  resetDragVerify: () => dragVerifyRef.value?.reset?.(),
  resetAltcha,
});
</script>

<style scoped lang="scss">
@use "@styles/custom/fa-login";
</style>
