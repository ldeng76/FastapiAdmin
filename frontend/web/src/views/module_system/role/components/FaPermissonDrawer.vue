<!-- 角色授权 -->
<template>
  <FaDrawer
    v-model="drawerVisible"
    :title="'【' + props.roleName + '】权限分配'"
    :size="drawerSize"
    destroy-on-close
    @close="handleCancel"
  >
    <div class="drawer-perm-content flex flex-col flex-1 overflow-hidden">
      <ElContainer class="h-full min-h-0 flex-1">
        <!-- 数据权限 -->
        <ElAside>
          <div
            class="border-r border-r-(--el-border-color-lighter) b-r-solid h-full p-[20px] box-border"
          >
            <div class="flex items-center">
              <div class="flex gap-[10px]">
                <div class="w-[10px] bg-(--el-color-primary)"></div>
                <div>
                  <span class="text-[16px]">数据授权</span>
                  <ElTooltip placement="right">
                    <template #content>
                      <span>授权用户可操作的数据范围</span>
                    </template>
                    <ElIcon class="ml-1 inline-block cursor-pointer">
                      <QuestionFilled />
                    </ElIcon>
                  </ElTooltip>
                </div>
              </div>
            </div>
            <div class="mt-3">
              <ElForm ref="dataFormRef" :model="permissionState">
                <ElFormItem prop="data_scope">
                  <ElSelect v-model="permissionState.data_scope">
                    <ElOption :key="1" label="仅本人数据权限" :value="1" />
                    <ElOption :key="2" label="本部门数据权限" :value="2" />
                    <ElOption :key="3" label="本部门及以下数据权限" :value="3" />
                    <ElOption :key="4" label="全部数据权限" :value="4" />
                    <ElOption :key="5" label="自定义数据权限" :value="5" />
                  </ElSelect>
                </ElFormItem>
              </ElForm>

              <div
                v-if="permissionState.data_scope === 5 && deptTreeData.length"
                class="mt-5 max-h-[72vh] b-1 b-solid b-[var(--el-border-color-lighter)] p-10px overflow-auto box-border"
              >
                <ElInput v-model="deptFilterText" placeholder="部门名称" />
                <ElTree
                  ref="deptTreeRef"
                  node-key="value"
                  show-checkbox
                  :data="deptTreeData"
                  :filter-node-method="handleFilter"
                  default-expand-all
                  :highlight-current="true"
                  :check-strictly="!parentChildLinked"
                  :style="'height: calc(100% - 60px); margin-top: 10px; overflow-y: auto'"
                  @check="deptTreeCheck"
                >
                  <template #empty>
                    <ElEmpty :image-size="80" description="暂无数据" />
                  </template>
                </ElTree>
              </div>
            </div>
          </div>
        </ElAside>

        <!-- 菜单权限 -->
        <ElMain>
          <div class="flex gap-[10px]">
            <div class="w-[10px] bg-(--el-color-primary)"></div>
            <div>
              <span class="text-[16px]">菜单授权</span>
              <ElTooltip placement="right">
                <template #content>
                  <span>勾选菜单和对应的功能按钮权限</span>
                </template>
                <ElIcon class="ml-1 inline-block cursor-pointer">
                  <QuestionFilled />
                </ElIcon>
              </ElTooltip>
            </div>
          </div>
          <div class="mt-3 flex items-center gap-3">
            <ElInput v-model="permFilterText" placeholder="菜单名称" class="flex-1" />
            <ElButton type="primary" size="small" plain @click="togglePermTree">
              <template #icon>
                <SwitchIcon />
              </template>
              {{ isExpanded ? "收缩" : "展开" }}
            </ElButton>
            <ElCheckbox v-model="parentChildLinked"> 父子联动 </ElCheckbox>
            <ElTooltip placement="bottom">
              <template #content> 勾选父级菜单时自动勾选所有子菜单 </template>
              <ElIcon class="color-[--el-color-primary] inline-block cursor-pointer">
                <QuestionFilled />
              </ElIcon>
            </ElTooltip>
          </div>

          <!-- 菜单树 -->
          <div class="mt-3 b-1 b-solid b-[var(--el-border-color-lighter)] rounded-lg">
            <ElTree
              ref="permTreeRef"
              :data="tableData"
              node-key="id"
              show-checkbox
              :default-expand-all="isExpanded"
              :check-strictly="!parentChildLinked"
              :filter-node-method="handlePermFilter"
              :expand-on-click-node="false"
              :props="{ label: 'name', children: 'children' }"
            >
              <template #default="{ data }">
                <span class="inline-flex items-center gap-1.5">
                  <FaMenuRouteIcon
                    v-if="data.icon"
                    :icon="data.icon"
                    style="vertical-align: -0.15em"
                  />
                  <span>{{ data.name }}</span>
                </span>
              </template>
            </ElTree>
          </div>
        </ElMain>
      </ElContainer>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <ElButton @click="handleCancel">取 消</ElButton>
        <ElButton type="primary" :loading="loading" @click.stop="handleDrawerSave">确 定</ElButton>
      </div>
    </template>
  </FaDrawer>
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted, nextTick } from "vue";
import { QuestionFilled, Switch as SwitchIcon } from "@element-plus/icons-vue";
import type { TreeInstance } from "element-plus";
import FaDrawer from "@/components/modal/fa-drawer/index.vue";
import FaMenuRouteIcon from "@/components/others/fa-menu-routeIcon/index.vue";
import { listToTree, formatTree } from "@utils";
import RoleAPI, { permissionDataType, permissionDeptType } from "@/api/module_system/role";
import DeptAPI from "@/api/module_system/dept";
import MenuAPI, { MenuTable } from "@/api/module_system/menu";
import { DeviceEnum } from "@/enums/settings/device.enum";
import { useAppStore, useUserStore } from "@stores";
import { ElMessage } from "element-plus";

const props = defineProps<{
  roleName: string;
  roleId: number;
  modelValue: boolean;
}>();

const emit = defineEmits<{
  "update:modelValue": [v: boolean];
  saved: [];
}>();

const appStore = useAppStore();
const drawerSize = computed(() => (appStore.device === DeviceEnum.DESKTOP ? "1200px" : "60%"));

const drawerVisible = computed({
  get() {
    return props.modelValue;
  },
  set(value: boolean) {
    emit("update:modelValue", value);
  },
});

const deptTreeRef = ref<TreeInstance>();
const permTreeRef = ref<TreeInstance>();
const deptFilterText = ref("");
const permFilterText = ref("");
const isExpanded = ref(false);
/** 父子联动开关：开启后勾选父节点会自动勾选子节点 */
const parentChildLinked = ref(false);
const loading = ref(false);
const deptTreeData = ref<permissionDeptType[]>([]);
const rawMenuTree = ref<MenuTable[]>([]);
const tableData = ref<MenuTable[]>([]);

const permissionState = ref<permissionDataType>({
  role_ids: [],
  menu_ids: [],
  data_scope: 1,
  dept_ids: [],
});

/** 递归遍历树节点并对每个节点执行回调 */
function walkTree(nodes: MenuTable[], fn: (node: MenuTable) => void) {
  for (const node of nodes) {
    fn(node);
    if (node.children) walkTree(node.children, fn);
  }
}

const init = async () => {
  loading.value = true;

  try {
    const deptResponse = await DeptAPI.listDept();
    deptTreeData.value = formatTree(listToTree(deptResponse.data.data));

    const menuResponse = await MenuAPI.listMenu();
    const rawTree = menuResponse.data.data || [];
    rawMenuTree.value = rawTree;
    tableData.value = rawTree;

    const roleResponse = await RoleAPI.detailRole(props.roleId);
    const savedMenuIds = roleResponse.data.data.menus?.map((menu) => menu.id) || [];

    permissionState.value = {
      role_ids: [props.roleId],
      menu_ids: savedMenuIds,
      data_scope: roleResponse.data.data.data_scope || 1,
      dept_ids: roleResponse.data.data.depts?.map((dept) => dept.id) || [],
    };

    // 设置树的勾选状态
    await nextTick();
    if (permTreeRef.value) {
      permTreeRef.value.setCheckedKeys(savedMenuIds, false);
    }

    if (permissionState.value.data_scope === 5 && deptTreeRef.value) {
      await deptTreeRef.value.setCheckedKeys(permissionState.value.dept_ids);
    }
  } catch (error: unknown) {
    const msg = error instanceof Error ? error.message : String(error);
    ElMessage.error("获取权限数据失败: " + msg);
  } finally {
    loading.value = false;
  }
};

function handleCancel() {
  drawerVisible.value = false;
}

async function handleDrawerSave() {
  try {
    if (props.roleId === 1) {
      ElMessage.warning("系统默认角色，不可操作");
      return;
    }
    loading.value = true;

    // 收集所有选中的节点 ID
    const allIds = new Set<number>();

    // 选中的节点
    const checkedMenuIds = (permTreeRef.value?.getCheckedKeys() || []).map((key: any) => Number(key));
    // 半选状态（部分子节点选中时父节点半选，仅联动模式生效）
    const halfCheckedMenuIds = (permTreeRef.value?.getHalfCheckedKeys() || []).map((key: any) => Number(key));

    [...checkedMenuIds, ...halfCheckedMenuIds].forEach((id) => allIds.add(id));

    const menu_ids = expandMenuIdsWithAncestors([...allIds], rawMenuTree.value);

    const submitData: permissionDataType = {
      role_ids: [props.roleId],
      menu_ids,
      data_scope: permissionState.value.data_scope,
      dept_ids: (deptTreeRef.value?.getCheckedKeys() || []).map((key) => Number(key)),
    };

    await RoleAPI.setPermission(submitData);

    const userStore = useUserStore();
    await userStore.getUserInfo();

    drawerVisible.value = false;
    emit("saved");
  } catch (error: unknown) {
    console.error(error);
  } finally {
    loading.value = false;
  }
}

const deptTreeCheck = (checkedIds: number[]) => {
  permissionState.value.dept_ids = checkedIds;
};

/** 展开/收缩所有树节点 */
function togglePermTree() {
  isExpanded.value = !isExpanded.value;
  nextTick(() => {
    const tree = permTreeRef.value as any;
    if (!tree || !tableData.value.length) return;
    const store = tree.store;
    if (!store) return;
    walkTree(tableData.value, (node:any) => {
      const treeNode = store.nodesMap[node.id];
      if (treeNode) treeNode.expanded = isExpanded.value;
    });
  });
}

watch(deptFilterText, (val) => {
  deptTreeRef.value!.filter(val);
});

watch(permFilterText, (val) => {
  permTreeRef.value?.filter(val);
  if (val) {
    isExpanded.value = true;
    nextTick(() => {
      const tree = permTreeRef.value as any;
      const store = tree?.store;
      if (!store) return;
      walkTree(tableData.value, (node) => {
        const treeNode = store.nodesMap[node.id];
        if (treeNode) treeNode.expanded = true;
      });
    });
  }
});

function handleFilter(value: string, data: { [key: string]: any }) {
  if (!value) return true;
  return data.label?.includes(value);
}

function handlePermFilter(value: string, data: any) {
  if (!value) return true;
  return data.name?.includes(value) || false;
}

function expandMenuIdsWithAncestors(checkedIds: number[], roots: MenuTable[]): number[] {
  const parentById = new Map<number, number | undefined>();
  const walk = (nodes: MenuTable[], parent: number | undefined) => {
    for (const n of nodes) {
      const id = n.id!;
      parentById.set(id, parent);
      if (n.children?.length) walk(n.children as MenuTable[], id);
    }
  };
  walk(roots, undefined);
  const out = new Set<number>();
  for (const id of checkedIds) {
    let cur: number | undefined = id;
    while (cur !== undefined) {
      out.add(cur);
      cur = parentById.get(cur);
    }
  }
  return [...out];
}

onMounted(async () => {
  await init();
});
</script>
