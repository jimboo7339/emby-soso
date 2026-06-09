<script setup lang="ts">
import { h, onActivated, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  NButton,
  NDataTable,
  NInput,
  NPagination,
  NPopconfirm,
  NSelect,
  NSpace,
  NSpin,
  NTag,
  useMessage,
  type DataTableColumns,
} from "naive-ui";
import {
  fetchMedia,
  resetMedia,
  scrapeStatusLabels,
  type MediaItem,
} from "@/api";

const route = useRoute();
const router = useRouter();
const message = useMessage();

const loading = ref(false);
const resettingId = ref<string | null>(null);
const items = ref<MediaItem[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const q = ref("");
const scrapeStatus = ref<string | null>(
  (route.query.scrape_status as string) || null
);

const statusOptions = [
  { label: "全部", value: null },
  ...Object.entries(scrapeStatusLabels).map(([value, label]) => ({ label, value })),
];

async function handleReset(id: string) {
  resettingId.value = id;
  try {
    const result = await resetMedia(id);
    if (result.library_folders_removed === 0) {
      message.warning(
        "数据库已清空，但未找到可删除的影视库文件夹。请检查任务的 library_path 是否与 .env 中 DATA_LIBRARY_ROOT 一致。"
      );
    } else {
      const scopeNote =
        (result.related_media_reset ?? 1) > 1
          ? `（同剧集 ${result.related_media_reset} 条记录已一并重置）`
          : "";
      message.success(
        `已重置：删除 ${result.library_folders_removed} 个库目录，源文件保留。${scopeNote}请重新运行任务扫描。`
      );
    }
    await loadMedia();
  } catch (e) {
    message.error(e instanceof Error ? e.message : "重置失败");
  } finally {
    resettingId.value = null;
  }
}

const columns: DataTableColumns<MediaItem> = [
  { title: "标题", key: "title", ellipsis: { tooltip: true } },
  {
    title: "类型",
    key: "media_type",
    width: 72,
    render: (row) => (row.media_type === "tv" ? "剧集" : "电影"),
  },
  { title: "年份", key: "year", width: 72 },
  { title: "TMDB", key: "tmdb_id", width: 96 },
  {
    title: "刮削状态",
    key: "scrape_status",
    width: 120,
    render: (row) =>
      h(
        NTag,
        { size: "small", type: row.scrape_status === "complete" ? "success" : "warning" },
        { default: () => scrapeStatusLabels[row.scrape_status] ?? row.scrape_status }
      ),
  },
  {
    title: "操作",
    key: "actions",
    width: 160,
    render: (row) =>
      h(NSpace, { size: 8 }, () => [
        h(
          NButton,
          { size: "small", type: "primary", secondary: true, onClick: () => router.push(`/media/${row.id}`) },
          { default: () => "详情" }
        ),
        h(
          NPopconfirm,
          {
            onPositiveClick: () => handleReset(row.id),
          },
          {
            trigger: () =>
              h(
                NButton,
                {
                  size: "small",
                  type: "error",
                  secondary: true,
                  loading: resettingId.value === row.id,
                },
                { default: () => "重置" }
              ),
            default: () =>
              "将删除影视库中该剧/电影的全部文件（含 NFO、图片、链接），并清空数据库记录。源目录文件不会删除，需重新运行任务扫描整理。确定继续？",
          }
        ),
      ]),
  },
];

async function loadMedia() {
  loading.value = true;
  try {
    const data = await fetchMedia({
      page: page.value,
      page_size: pageSize.value,
      scrape_status: scrapeStatus.value ?? undefined,
      q: q.value || undefined,
    });
    items.value = data.items;
    total.value = data.total;
    if (total.value > 0 && items.value.length === 0 && page.value > 1) {
      page.value = 1;
      return;
    }
  } catch (e) {
    message.error(e instanceof Error ? e.message : "加载失败");
  } finally {
    loading.value = false;
  }
}

function handleSearch() {
  page.value = 1;
  void loadMedia();
}

watch(pageSize, () => {
  page.value = 1;
  void loadMedia();
});

watch(scrapeStatus, () => {
  page.value = 1;
  void loadMedia();
});

watch(page, loadMedia);
onMounted(loadMedia);
onActivated(loadMedia);
</script>

<template>
  <div class="media-list-page">
    <section class="list-toolbar panel">
      <NSpace>
        <NInput v-model:value="q" placeholder="搜索标题" style="width: 240px" @keyup.enter="handleSearch" />
        <NSelect
          v-model:value="scrapeStatus"
          :options="statusOptions"
          placeholder="刮削状态"
          style="width: 180px"
          clearable
        />
        <NButton type="primary" @click="handleSearch">搜索</NButton>
      </NSpace>
      <p class="list-meta">
        共 {{ total }} 条媒体
        <template v-if="total > 0">
          ，当前第 {{ page }} / {{ Math.max(1, Math.ceil(total / pageSize)) }} 页
        </template>
      </p>
    </section>

    <NSpin :show="loading">
      <section class="list-table panel">
        <NDataTable :columns="columns" :data="items" :bordered="false" />
        <div v-if="total > 0" class="list-pagination">
          <NPagination
            v-model:page="page"
            v-model:page-size="pageSize"
            :item-count="total"
            :page-sizes="[20, 50, 100]"
            show-size-picker
          />
        </div>
      </section>
    </NSpin>
  </div>
</template>

<style scoped>
.media-list-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.panel {
  background: #fff;
  border-radius: 14px;
  border: 1px solid #eef0f4;
  box-shadow: 0 2px 12px rgba(15, 23, 42, 0.04);
}

.list-toolbar {
  padding: 16px 18px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}

.list-meta {
  margin: 0;
  font-size: 13px;
  color: #8b95a5;
}

.list-table {
  padding: 4px 8px 8px;
  overflow: hidden;
}

.list-table :deep(.n-data-table-th) {
  background: #f8f9fb;
  font-weight: 600;
}

.list-table :deep(.n-data-table-tr:hover .n-data-table-td) {
  background: #f5f7fb;
}

.list-pagination {
  display: flex;
  justify-content: flex-end;
  padding: 12px 8px 8px;
}
</style>
