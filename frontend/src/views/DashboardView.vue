<script setup lang="ts">
import { onMounted, ref } from "vue";
import { NCard, NGrid, NGi, NStatistic, NTag, NSpace, NSpin, NAlert, NButton } from "naive-ui";
import { useRouter } from "vue-router";
import { fetchDashboardStats, fetchHealth, type DashboardStats, type HealthInfo } from "@/api";

const router = useRouter();
const loading = ref(true);
const health = ref<HealthInfo | null>(null);
const stats = ref<DashboardStats | null>(null);
const error = ref("");

onMounted(async () => {
  try {
    [health.value, stats.value] = await Promise.all([
      fetchHealth(),
      fetchDashboardStats(),
    ]);
  } catch (e) {
    error.value = e instanceof Error ? e.message : "加载失败";
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <NSpin :show="loading">
    <NSpace vertical size="large">
      <NAlert v-if="error" type="error" :title="error" />

      <NGrid cols="1 s:2 m:4" responsive="screen" :x-gap="16" :y-gap="16">
        <NGi>
          <NCard title="媒体总数">
            <NStatistic :value="stats?.total_media ?? 0" />
          </NCard>
        </NGi>
        <NGi>
          <NCard title="刮削完成">
            <NStatistic :value="stats?.complete ?? 0" />
          </NCard>
        </NGi>
        <NGi>
          <NCard title="待手动匹配">
            <NStatistic :value="stats?.needs_manual_match ?? 0" />
          </NCard>
        </NGi>
        <NGi>
          <NCard title="已整理文件">
            <NStatistic :value="stats?.linked_files ?? 0">
              <template #suffix>/ {{ stats?.total_files ?? 0 }}</template>
            </NStatistic>
          </NCard>
        </NGi>
      </NGrid>

      <NGrid cols="1 s:2 m:4" :x-gap="16" :y-gap="16">
        <NGi>
          <NCard title="服务状态">
            <NTag :type="health?.status === 'ok' ? 'success' : 'warning'">
              {{ health?.status ?? "-" }}
            </NTag>
          </NCard>
        </NGi>
        <NGi>
          <NCard title="数据库">
            <NTag :type="health?.database === 'connected' ? 'success' : 'error'">
              {{ health?.database ?? "-" }}
            </NTag>
          </NCard>
        </NGi>
        <NGi>
          <NCard title="Redis">
            <NTag>{{ health?.redis ?? "-" }}</NTag>
          </NCard>
        </NGi>
        <NGi>
          <NCard title="运行模式">
            <NStatistic :value="health?.mode ?? '-'" />
          </NCard>
        </NGi>
      </NGrid>

      <NCard title="快捷操作">
        <NSpace>
          <NButton type="primary" @click="router.push('/tasks')">管理任务</NButton>
          <NButton @click="router.push('/media?scrape_status=needs_manual_match')">
            待匹配列表
          </NButton>
          <NButton @click="router.push('/wall')">海报墙</NButton>
        </NSpace>
      </NCard>
    </NSpace>
  </NSpin>
</template>
