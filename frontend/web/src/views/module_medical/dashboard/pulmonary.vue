<template>
  <el-container class="layout-container">
    <el-header class="top-header flex">
      <el-text size="large" :style="'width: '+asideWidth+'px'">肺结节/肺癌科研数据管理仪表板</el-text>
      <div style="position: relative">
        <el-tabs style="position: absolute;bottom:0;margin-bottom: -15px" :default-value="'first'" @tab-click="function(){}">
          <el-tab-pane label="数据概览" name="first"></el-tab-pane>
          <el-tab-pane label="影像特征" name="second"></el-tab-pane>
          <el-tab-pane label="病理与分子" name="third"></el-tab-pane>
          <el-tab-pane label="生存随访" name="fourth"></el-tab-pane>
        </el-tabs>
      </div>
    </el-header>
    <el-container class="layout-body">
      <!-- 2. 左侧侧边栏 -->
      <el-aside :width="asideWidth+'px'" class="layout-aside">
        <el-menu class="el-menu-vertical">
          <el-sub-menu v-for="item1 in searchConfig" :index="item1.key" :key="item1.key">
            <template #title>
              <div style="display: flex; justify-content: space-between;align-items: center;width: 100%;">
                <div>
                  <el-icon v-if="item1.currFilter" :size="20">
                    <CircleCheckFilled color="var(--color-success)" />
                  </el-icon>
                  <el-icon v-else :size="20">
                    <CirclePlus />
                  </el-icon>
                  <el-text style="width: 160px" truncated>
                    {{ item1.dict_label}}{{ item1.currFilterText ? "：" + item1.currFilterText : "" }}
                  </el-text>
                </div>
                <div v-if="item1.currFilterText">
                  <el-button type="danger" style="vertical-align: initial" size="small" @click="clearSearch(item1,$event)" plain>清除</el-button>
                </div>
              </div>
            </template>
            <el-menu-item
              v-for="item2 in item1.children"
              @click="search(item1, item2)"
              :index="item2.key"
              :key="item2.key"
              :class="{'selected' : item1.currFilter === item2.dict_value}"
              class="menu-item"
            >
              {{ item2.dict_label }}
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
import {useDictStore} from "@stores";
let searchConfig = ref(filterConfig);
const asideWidth = 300;
function clearSearch(item1,e) {
  item1.currFilter = '';
  item1.currFilterText = '';
  e.stopPropagation()
}

function search(item1, item2) {
  item1.currFilter = item2.dict_value;
  item1.currFilterText = item2.dict_label;
}
const dictStore = useDictStore();
onMounted(async function () {
  const dictKeyArr = [
    "med_sex",
    "med_exam_type",
    "med_laterality",
    "med_smoking_status",
    "med_ethnicity",
    "med_blood_type_abo",
    "med_blood_type_rh",
    "med_center",
  ]
  const dictMap = await dictStore.getDict(dictKeyArr);
  searchConfig.value.forEach(function (n){
    if(dictMap[n.dict_type] != null){
      n.children = dictMap[n.dict_type]
    }
  })

  addConfigKey(searchConfig.value);
});
</script>

<style scoped>
.top-header{
  background-color: #fff;
  border-bottom: 1px solid #dddddd;
}
.layout-container {
  height: 100vh;
  background-color: #f0f2f5;
}
.menu-item.is-active{
  color: inherit;
}
.menu-item.selected{
  color:  var(--el-menu-active-color);;
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
