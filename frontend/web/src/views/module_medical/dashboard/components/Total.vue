<script setup lang="ts">
import { computed } from "vue";
const props = defineProps<{
  label: string | undefined;
  icon: string | undefined;
  value: number | string | undefined;
  dark?: boolean;
}>();

let duration = computed(function (){
  if(typeof props.value === 'number'){
    if(props.value > 20){
      return 1500
    } else {
      return 0
    }
  }
  return  0
})

</script>

<template>
  <div class="kpi" :class="{ 'kpi--dark': dark }">
    <div class="kpi-ic" v-if="icon">
      <FaSvgIcon :icon="icon" class="kpi-ic-svg" />
    </div>
    <div class="kpi-body">
      <div class="kpi-label">{{ label }}</div>
      <div class="kpi-value">
        <FaCountTo v-if="typeof value === 'number'" :target="value" :duration="duration" />
        <el-text v-else>{{ value }}</el-text>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.kpi{
  background: #fff;
  border: 1px solid var(--lnrs-line);
  border-radius: 12px;
  padding: 20px 22px;
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: 0 1px 2px rgba(10,37,64,.05), 0 8px 24px rgba(10,37,64,.06);
  position: relative;
  overflow: hidden;
}
.kpi::after{
  content: "";position: absolute;right: -32px;top: -32px;
  width: 100px;height: 100px;border-radius: 50%;
  background: radial-gradient(circle, rgba(10,199,181,.07), transparent 70%);
}
.kpi-ic{
  width: 46px;height: 46px;border-radius: 10px;
  background: var(--lnrs-teal-soft);color: var(--lnrs-teal);
  display: grid;place-items: center;flex-shrink: 0;
}
.kpi-ic-svg{font-size: 24px}
.kpi-body{min-width: 0}
.kpi-label{
  font-size: 12px;color: var(--lnrs-ink-3);letter-spacing: 1.5px;
  margin-bottom: 6px;font-weight: 500;
  white-space: nowrap;overflow: hidden;text-overflow: ellipsis;
}
.kpi-value{
  font-size: 28px;font-weight: 600;color: var(--lnrs-navy);
  font-family: var(--lnrs-num);letter-spacing: 1px;line-height: 1.05;
}

/* 深色 AI 底效（移植自 AI 多维数据提取架构）：患者总量 / 检查总量 / 检查模态 */
.kpi--dark{
  background: linear-gradient(135deg, #0A2540 0%, #0F3358 100%);
  border-color: rgba(255,255,255,.08);
  color: #fff;
}
.kpi--dark::before{
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
  background-image: linear-gradient(rgba(255,255,255,.05) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,.05) 1px, transparent 1px);
  background-size: 26px 26px;
  -webkit-mask-image: linear-gradient(135deg, #000 30%, transparent 80%);
  mask-image: linear-gradient(135deg, #000 30%, transparent 80%);
}
.kpi--dark::after{
  background: radial-gradient(circle, rgba(10,199,181,.2), transparent 70%);
}
.kpi--dark .kpi-ic{
  background: linear-gradient(135deg, rgba(10,199,181,.32), rgba(10,199,181,.1));
  color: var(--lnrs-teal-2);
  box-shadow: 0 0 18px rgba(10,199,181,.35);
}
.kpi--dark .kpi-label{color: #7FB8C9}
.kpi--dark .kpi-value{
  color: #fff;
  text-shadow: 0 0 16px rgba(10, 199, 181, .45);
}
</style>
