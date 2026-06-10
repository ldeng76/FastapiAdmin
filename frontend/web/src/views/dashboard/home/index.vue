<template>
  <div class="dashboard-container">
    <!-- 卡片组件演示区 ← workplace -->
    <ElRow :gutter="20">
      <ElCol :xs="24" class="mb-5">
        <Banner />
      </ElCol>

      <ElCol :xs="24" :md="18">
        <ElRow :gutter="20">
          <ElCol :xs="24" :sm="8" :md="24" class="mb-5">
            <CardList />
          </ElCol>
          <ElCol :xs="24" :sm="8" :md="8" class="mb-5">
            <FaStatsCard
              :icon="'ri:money-cny-box-line'"
              :iconStyle="'bg-theme'"
              :boxStyle="'bg-theme/10!'"
              :title="'总收入'"
              :description="'月收入超过¥350,000+'"
              :count="35000"
              :textColor="'var(--theme-color)'"
              :decimals="0"
              :showArrow="false"
              separator=","
              customIconStyle="'text-theme! text-3xl!''"
            />
          </ElCol>
          <ElCol :xs="24" :sm="12" :md="8" class="mb-5">
            <FaProgressCard :percentage="65" :title="'任务进度'" :color="'var(--theme-color)'" />
          </ElCol>
          <ElCol :xs="24" :sm="12" :md="8" class="mb-5">
            <FaProgressCard
              :percentage="80"
              :title="'任务进度'"
              :color="'var(--theme-color)'"
              :icon="'ri:twitch-line'"
              :iconStyle="'bg-theme/12 text-theme'"
            />
          </ElCol>
          <ElCol :xs="24" :sm="8" :md="8" class="mb-5">
            <FaBarChartCard
              :isMiniChart="true"
              :value="15480"
              label="浏览量"
              date="过去14天"
              :percentage="-4.15"
              :height="9.5"
              barWidth="45%"
              :chartData="[120, 100, 150, 140, 90, 120, 130]"
            />
          </ElCol>
          <ElCol :xs="24" :sm="8" :md="8" class="mb-5">
            <FaLineChartCard
              :isMiniChart="true"
              :value="2545"
              label="粉丝数"
              date="过去30天"
              :percentage="1.2"
              :height="9.5"
              :showAreaColor="true"
              :chartData="[150, 180, 160, 200, 180, 220, 240]"
            />
          </ElCol>
          <ElCol :xs="24" :sm="8" :md="8" class="mb-5">
            <FaDonutChartCard
              :value="36358"
              title="粉丝量"
              :percentage="18"
              percentageLabel="较去年"
              :data="[50, 40]"
              :height="9.5"
              currentValue="2022"
              previousValue="2021"
              :radius="['50%', '70%']"
            />
          </ElCol>
        </ElRow>
      </ElCol>
      <ElCol :xs="24" :md="6">
        <ElCard shadow="hover" class="flex flex-col h-108">
          <template #header>
            <div class="workplace-bookmarks-card__header">
              <div>
                <span class="workplace-panel-title workplace-bookmarks-card__title-line">
                  <ElIcon class="workplace-bookmarks-card__star" :size="18"><Star /></ElIcon>
                  我的收藏
                  <ElTag
                    v-if="quickLinks.length > 0"
                    type="info"
                    size="small"
                    effect="plain"
                    round
                    class="workplace-bookmarks-card__count"
                  >
                    {{ quickLinks.length }}/{{ QUICK_LINK_MAX }}
                  </ElTag>
                </span>
              </div>
              <div class="workplace-bookmarks-card__header-actions">
                <ElTooltip content="在顶部标签栏左侧星标上点击，可加入或取消收藏" placement="top">
                  <ElIcon class="workplace-module-bookmarks__help" :size="15">
                    <QuestionFilled />
                  </ElIcon>
                </ElTooltip>
                <ElButton size="small" type="danger" plain @click="clearBookmarks()">
                  <ElIcon><Delete /></ElIcon>
                  {{ t("common.clear") }}
                </ElButton>
              </div>
            </div>
          </template>
          <ElRow v-if="quickLinks.length > 0" :gutter="4">
            <ElCol
              v-for="(item, index) in quickLinks"
              :key="item.id || `${item.href}-${index}`"
              :xs="24"
              :sm="12"
              :md="12"
              class="mb-2.5"
            >
              <div
                class="workplace-quick-row workplace-quick-row--chip"
                role="button"
                tabindex="0"
                @click="handleQuickLinkClick(item)"
                @keydown.enter.prevent="handleQuickLinkClick(item)"
                @keydown.space.prevent="handleQuickLinkClick(item)"
              >
                <span
                  class="workplace-quick-row__accent"
                  :style="{ backgroundColor: getQuickLinkColor(getQuickLinkStableIndex(item)) }"
                />
                <div
                  class="workplace-quick-row__icon"
                  :style="{ color: getQuickLinkColor(getQuickLinkStableIndex(item)) }"
                >
                  <FaMenuRouteIcon :icon="item.icon || 'menu'" />
                </div>
                <div class="workplace-quick-row__text">
                  <span class="workplace-quick-row__title">{{ item.title }}</span>
                </div>
                <div class="workplace-quick-row__actions">
                  <button
                    type="button"
                    class="workplace-quick-row__remove"
                    :disabled="!item.id && !item.href"
                    :title="item.id || item.href ? '移除收藏' : '无法移除（缺少路径）'"
                    :aria-label="`移除收藏 ${item.title}`"
                    @click.stop="handleDeleteLink(item)"
                  >
                    <ElIcon><Close /></ElIcon>
                  </button>
                </div>
              </div>
            </ElCol>
          </ElRow>
          <ElEmpty v-else :image-size="80">
            <template #description>
              <p class="workplace-quick-empty__title">暂无收藏</p>
              <p class="workplace-quick-empty__hint">
                在顶部
                <strong>标签栏</strong>
                左侧星标点击添加
              </p>
            </template>
          </ElEmpty>
        </ElCard>
      </ElCol>

      <ElCol :xs="24" :sm="12" :md="12" class="mb-5">
        <ElCard shadow="hover" class="workplace-surface workplace-ops-card flex flex-col h-full">
          <template #header>
            <div class="workplace-section-card__head">
              <div>
                <span class="workplace-panel-title">日程日历</span>
                <p class="workplace-section-sub workplace-section-sub--inline">
                  点击日期添加或编辑（本地演示）
                </p>
              </div>
            </div>
          </template>
          <div class="workplace-ops-card__body">
            <FaCalendar />
          </div>
        </ElCard>
      </ElCol>
      <ElCol :xs="24" :sm="12" :md="12" class="mb-5">
        <NewUser />
      </ElCol>

      <ElCol :xs="24" :sm="12" :md="6" class="mb-5">
        <TodoList />
      </ElCol>
      <ElCol :xs="24" :sm="12" :md="6" class="mb-5">
        <FaTimelineListCard :list="timelineData" title="最近交易" subtitle="2024年12月20日" />
      </ElCol>
      <ElCol :xs="24" :sm="12" :md="6" class="mb-5">
        <FaDataListCard
          :maxCount="4"
          :list="dataList"
          title="最近活动"
          subtitle="近期活动列表"
          :showMoreButton="true"
          @more="handleMore"
        />
      </ElCol>

      <ElCol :xs="24" :sm="8" :md="6" class="mb-5">
        <FaImageCard
          :imageUrl="imageCards.imageUrl"
          :title="imageCards.title"
          :category="imageCards.category"
          :readTime="imageCards.readTime"
          :views="imageCards.views"
          :comments="imageCards.comments"
          :date="imageCards.date"
          @click="handleImageCardClick(imageCards)"
        />
      </ElCol>

      <ElCol :xs="24" :sm="4" :md="6" class="mb-5">
        <FaCardBanner
          :image="bannerIcon4"
          title="版本更新提醒"
          description="FastapiAdmin v3.0.0 已发布，包含优化和新功能。"
          :button="{
            show: true,
            text: '立即更新',
            color: 'var(--theme-color)',
            textColor: '#fff',
          }"
          :cancelButton="{ show: true, text: '稍后提醒', color: '#eee', textColor: '#333' }"
          @click="handleBannerDemoConfirm"
          @cancel="handleBannerDemoCancel"
        />
      </ElCol>
      <ElCol :xs="24" :sm="12" :md="18" class="mb-5">
        <AboutProject />
      </ElCol>
    </ElRow>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: "Home", inheritAttrs: false });

import { ref, onMounted, onUnmounted } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import { Delete, Close, Star, QuestionFilled } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import bannerIcon4 from "@imgs/3d/icon4.webp";
import cover2 from "@imgs/cover/img2.webp";
import { quickStartManager, QUICK_LINK_MAX, type QuickLink } from "@utils";
import FaCardBanner from "@/components/banners/fa-card-banner/index.vue";
import FaImageCard from "@/components/cards/fa-image-card/index.vue";
import FaDataListCard from "@/components/cards/fa-data-list-card/index.vue";
import FaTimelineListCard from "@/components/cards/fa-timeline-list-card/index.vue";
import FaStatsCard from "@/components/cards/fa-stats-card/index.vue";
import FaLineChartCard from "@/components/cards/fa-line-chart-card/index.vue";
import FaBarChartCard from "@/components/cards/fa-bar-chart-card/index.vue";
import FaDonutChartCard from "@/components/cards/fa-donut-chart-card/index.vue";
import FaProgressCard from "@/components/cards/fa-progress-card/index.vue";
import Banner from "./modules/banner.vue";
import NewUser from "./modules/new-user.vue";
import TodoList from "./modules/todo-list.vue";
import CardList from "./modules/card-list.vue";
import AboutProject from "./modules/about-project.vue";

const { t } = useI18n();
const router = useRouter();

const quickLinks = ref<QuickLink[]>(quickStartManager.getQuickLinks());
const handleQuickLinkClick = (item: QuickLink) => {
  if (item.href) {
    router.push(item.href).catch(() => {
      ElMessage.warning(`路由 ${item.href} 不存在，请检查配置`);
    });
  } else {
    ElMessage.info(`${item.title} 功能待开发`);
  }
};
const QUICK_LINK_PALETTE = ["#4080ff", "#23c343", "#ff9a2e", "#f76560", "#a9aeb8", "#00b42a"];
const getQuickLinkColor = (index: number) => QUICK_LINK_PALETTE[index % QUICK_LINK_PALETTE.length];
const getQuickLinkStableIndex = (item: QuickLink): number => {
  const i = quickLinks.value.findIndex((l) =>
    l.id != null && l.id !== "" ? l.id === item.id : l.href === item.href
  );
  return i >= 0 ? i : 0;
};
const handleDeleteLink = async (item: QuickLink) => {
  try {
    await ElMessageBox.confirm(`确定要取消收藏"${item.title}"吗？`, "取消收藏确认", {
      confirmButtonText: "确定",
      cancelButtonText: "取消",
      type: "warning",
    });
    if (item.id) quickStartManager.removeQuickLink(item.id);
    else if (item.href) quickStartManager.removeQuickLinkByHref(item.href);
    else {
      ElMessage.warning("无法移除：缺少标识");
      return;
    }
    ElMessage.success(`已取消收藏：${item.title}`);
  } catch {
    /* 用户取消 */
  }
};
const clearBookmarks = async () => {
  try {
    await ElMessageBox.confirm("确定要清空收藏吗？", "清空收藏确认", {
      confirmButtonText: "确定",
      cancelButtonText: "取消",
      type: "warning",
    });
    quickStartManager.clearQuickLinks();
    ElMessage.success("已清空收藏");
  } catch {
    /* 用户取消 */
  }
};
const updateQuickLinks = (links: QuickLink[]) => {
  quickLinks.value = links;
};

function handleBannerDemoConfirm() {
  console.log("confirm clicked");
}
function handleBannerDemoCancel() {
  console.log("cancel clicked");
}
// === 卡片演示数据 ← workplace ===
const imageCards = {
  id: 1,
  imageUrl: cover2,
  title: "大数据分析助力企业决策的实践案例",
  category: "技术",
  readTime: "3分钟",
  views: 7234,
  comments: 5,
  date: "12月20日 周二",
};

const dataList = [
  {
    title: "新加坡之行",
    status: "进行中",
    time: "5分钟",
    class: "bg-theme/12 text-theme",
    icon: "ri:camera-4-line",
  },
  {
    title: "归档数据",
    status: "进行中",
    time: "10分钟",
    class: "bg-secondary/12 text-secondary",
    icon: "ri:bar-chart-box-line",
  },
  {
    title: "客户会议",
    status: "待处理",
    time: "15分钟",
    class: "bg-warning/12 text-warning",
    icon: "ri:user-3-line",
  },
  {
    title: "筛选任务团队",
    status: "进行中",
    time: "20分钟",
    class: "bg-error/12 text-error",
    icon: "ri:account-circle-line",
  },
  {
    title: "发送信封给小王",
    status: "已完成",
    time: "20分钟",
    class: "bg-success/12 text-success",
    icon: "ri:message-3-line",
  },
  {
    title: "筛选任务团队",
    status: "进行中",
    time: "20分钟",
    class: "bg-error/12 text-error",
    icon: "ri:account-circle-line",
  },
];
const timelineData = [
  {
    time: "上午 09:30",
    status: "rgb(73, 190, 255)",
    content: "收到 John Doe 支付的 385.90 美元",
  },
  { time: "上午 10:00", status: "rgb(54, 158, 255)", content: "新销售记录", code: "ML-3467" },
  { time: "上午 12:00", status: "rgb(103, 232, 207)", content: "向 Michael 支付了 64.95 美元" },
  { time: "下午 14:30", status: "rgb(255, 193, 7)", content: "系统维护通知", code: "MT-2023" },
  {
    time: "下午 15:45",
    status: "rgb(255, 105, 105)",
    content: "紧急订单取消提醒",
    code: "OR-9876",
  },
  { time: "下午 17:00", status: "rgb(103, 232, 207)", content: "完成每日销售报表" },
  {
    time: "上午 09:30",
    status: "rgb(73, 190, 255)",
    content: "收到订单 #38291 支付 ¥385.90",
  },
  {
    time: "上午 10:00",
    status: "rgb(54, 158, 255)",
    content: "新商品上架",
    code: "SKU-3467",
  },
  {
    time: "上午 12:00",
    status: "rgb(103, 232, 207)",
    content: "向供应商支付了 ¥6495.00",
  },
  {
    time: "下午 14:30",
    status: "rgb(255, 193, 7)",
    content: "促销活动开始",
    code: "PROMO-2023",
  },
  {
    time: "下午 15:45",
    status: "rgb(255, 105, 105)",
    content: "订单取消提醒",
    code: "ORD-9876",
  },
  {
    time: "下午 17:00",
    status: "rgb(103, 232, 207)",
    content: "完成日销售报表",
  },
];

function handleMore() {
  ElMessage.info("查看更多");
}
function handleImageCardClick(card: typeof imageCards) {
  console.log("点击卡片:", card);
}
onMounted(() => {
  quickStartManager.addListener(updateQuickLinks);
});
onUnmounted(() => {
  quickStartManager.removeListener(updateQuickLinks);
});
</script>

<style scoped lang="scss">
:deep(.el-card) {
  --el-card-border-radius: calc(var(--custom-radius) + 2px);

  border: 1px solid var(--fa-card-border);
}

.dashboard-container {
  position: relative;
  display: flex;
  flex-direction: column;

  > * {
    margin-bottom: 16px;
  }

  > :last-child {
    margin-bottom: 0;
  }

  &::after {
    display: block;
    flex-shrink: 0;
    height: 16px;
    content: "";
  }
}

.version-item {
  padding: 10px 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 8px;
  transition: all 0.2s;

  &.latest-item {
    background: var(--el-color-primary-light-9);
    border: 1px solid var(--el-color-primary-light-5);
  }

  &:hover {
    transform: translateX(5px);
  }

  .version-content {
    display: block;
    margin-top: 6px;
    margin-bottom: 8px;
    font-size: 13px;
    line-height: 1.4;
    color: var(--el-text-color-secondary);
  }
}

.workplace-section-sub {
  margin: 4px 0 0;
  font-size: 12px;
  font-weight: normal;
  line-height: 1.45;
  color: var(--el-text-color-secondary);
}

.workplace-section-sub--inline {
  margin: 2px 0 0;
}

.workplace-surface {
  overflow: hidden;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;

  :deep(.el-card__header) {
    border-bottom-color: var(--el-border-color-extra-light);
  }
}

.workplace-ops-card__body--calendar {
  max-height: min(300px, 36vh);
  overflow: auto;
}

.workplace-panel-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  letter-spacing: 0.02em;
}

.workplace-hero__greeting {
  margin-bottom: 6px;
  font-size: 20px;
  font-weight: 700;
  line-height: 1.3;
  color: var(--el-text-color-primary);
}

.workplace-hero__meta {
  font-size: 13px;
  line-height: 1.5;
  color: var(--el-text-color-secondary);
}

.workplace-bookmarks-card__header {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  align-items: flex-start;
  justify-content: space-between;
}

.workplace-bookmarks-card__title-line {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.workplace-bookmarks-card__star {
  flex-shrink: 0;
  color: var(--el-color-warning);
}

.workplace-bookmarks-card__count {
  height: 22px;
  font-variant-numeric: tabular-nums;
}

.workplace-bookmarks-card__header-actions {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
  align-items: center;
}

.workplace-module-bookmarks__help {
  flex-shrink: 0;
  color: var(--el-text-color-secondary);
  cursor: help;
}

.workplace-quick-row {
  position: relative;
  display: flex;
  gap: 10px;
  align-items: center;
  min-height: 40px;
  padding: 8px 10px 8px 6px;
  cursor: pointer;
  outline: none;
  background: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--el-border-radius-base);
  transition:
    border-color 0.2s,
    box-shadow 0.2s,
    background 0.2s;

  &:hover {
    background: var(--el-bg-color);
    border-color: var(--el-color-primary-light-5);
    box-shadow: var(--el-box-shadow-light);
  }

  &:focus-visible {
    border-color: var(--el-color-primary);
    box-shadow: 0 0 0 2px var(--el-color-primary-light-7);
  }
}

.workplace-quick-row__accent {
  flex-shrink: 0;
  align-self: stretch;
  width: 3px;
  min-height: 24px;
  border-radius: 2px;
}

.workplace-quick-row__icon {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  font-size: 14px;
  line-height: 1;
  background: var(--el-color-primary-light-9);
  border-radius: 6px;
}

.workplace-quick-row__text {
  flex: 1;
  min-width: 0;
}

.workplace-quick-row__title {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.3;
  color: var(--el-text-color-primary);
  white-space: nowrap;
}

.workplace-quick-row__actions {
  display: flex;
  flex-shrink: 0;
  gap: 2px;
  align-items: center;
}

.workplace-quick-row__remove {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  padding: 0;
  color: var(--el-text-color-secondary);
  cursor: pointer;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 8px;
  transition:
    color 0.2s,
    background 0.2s,
    border-color 0.2s,
    opacity 0.2s;

  .workplace-quick-row--chip & {
    width: 20px;
    height: 20px;
  }

  &:disabled {
    cursor: not-allowed;
    opacity: 0.35;
  }

  &:hover:not(:disabled) {
    color: var(--el-color-danger);
    background: var(--el-color-danger-light-9);
    border-color: var(--el-color-danger-light-7);
  }
}

.workplace-quick-empty__title {
  margin: 0 0 8px;
  font-size: 14px;
  color: var(--el-text-color-regular);
}

.workplace-quick-empty__hint {
  margin: 0;
  font-size: 13px;
  line-height: 1.55;
  color: var(--el-text-color-secondary);
}

.workplace-section-card__head {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: flex-start;
  justify-content: space-between;
  width: 100%;
}
</style>
