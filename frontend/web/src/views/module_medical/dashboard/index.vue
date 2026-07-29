<template>
  <el-container class="layout-container">
    <el-container class="layout-body">
      <!-- 2. 左侧侧边栏 -->
      <el-aside width="300px" class="layout-aside">
        <el-menu class="el-menu-vertical">
          <el-sub-menu v-for="item1 in searchConfig" :index="item1.key" :key="item1.key">
            <template #title>
              <div style="display: flex; justify-content: space-between;align-items: center;vertical-align: middle; width: 100%">
                <div>
                  <el-icon v-if="item1.currFilter" :size="20">
                    <CircleCheckFilled color="var(--color-success)" />
                  </el-icon>
                  <el-icon v-else :size="20">
                    <CirclePlus />
                  </el-icon>
                  <span>{{ item1.label}}{{ item1.currFilterText ? "：" + item1.currFilterText : "" }}</span>
                </div>
                <div v-if="item1.currFilterText">
                  <el-button type="danger" size="small" @click="clearSearch(item1,$event)" plain>清除</el-button>
                </div>
              </div>
            </template>
            <el-menu-item
              v-for="item2 in item1.children"
              @click="search(item1, item2)"
              :index="item2.key"
              :key="item2.key"
            >
              {{ item2.label }}
            </el-menu-item>
          </el-sub-menu>
        </el-menu>
      </el-aside>

      <!-- 3. 右侧主要内容区域 -->
      <el-main class="layout-main"> 122 </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { CirclePlus, CircleCheckFilled } from "@element-plus/icons-vue";
import filterConfig, { addConfigKey } from "./filterConfig.ts";
import { ref, onMounted } from "vue";
import StatisticsAPI from "@api/module_medical/statistics.ts";
let searchConfig = ref(filterConfig);

function clearSearch(item1,e) {
  item1.currFilter = '';
  item1.currFilterText = '';
  e.stopPropagation()
}
function search(item1, item2) {
  item1.currFilter = item2.value;
  item1.currFilterText = item2.label;
}

onMounted(async function () {
  const res = await StatisticsAPI.getOverview();
  let center = res?.data?.data?.filters?.center?.options;
  let centerFilterConfig = searchConfig.value.find(function (n) {
    return n.label === "来源中心";
  });
  center.forEach(function (str) {
    centerFilterConfig.children.push({
      label: str,
      value: str,
    });
  });
  addConfigKey(searchConfig.value);
});
</script>

<style scoped>
.layout-container {
  height: 100vh;
  background-color: #f0f2f5;
}

.el-menu-vertical {
  height: 100%;
  border-right: none;
}
.layout-main {
  padding: 20px;
  background-color: #f0f2f5;
  height: 100%;
  overflow-y: auto;
}
</style>
