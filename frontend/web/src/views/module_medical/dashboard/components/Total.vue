<script setup lang="ts">
import { computed } from "vue";
const props = defineProps<{
  label: string | undefined;
  icon: string | undefined;
  value: number | string | undefined;
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
   <el-card style="--el-card-border-radius : 20px;  --el-card-border-color:#ccc">
     <div class="flex-c">
       <div v-if="icon" class="size-12 rounded-lg flex-cc bg-theme/10 mr-5">
          <FaSvgIcon :icon="icon" class="text-xl text-theme" />
       </div>
       <div>
         <h2>{{ label }}</h2>
         <FaCountTo v-if="typeof value === 'number'" class="text-2xl font-medium" :target="value" :duration="duration" />
         <el-text v-else>{{ value }}</el-text>
       </div>
     </div>
  </el-card>
</template>

<style scoped lang="scss">

</style>
