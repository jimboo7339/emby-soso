<script setup lang="ts">
import { ref, watch } from "vue";
import {
  NButton,
  NEmpty,
  NGrid,
  NGi,
  NInput,
  NModal,
  NSpace,
  NSpin,
  NTag,
  NText,
  useMessage,
} from "naive-ui";
import {
  manualMatch,
  posterUrl,
  searchTmdb,
  type MatchContext,
  type TmdbSearchResult,
} from "@/api";

const props = defineProps<{
  show: boolean;
  mediaId: string;
  context: MatchContext | null;
}>();

const emit = defineEmits<{
  (e: "update:show", value: boolean): void;
  (e: "matched"): void;
}>();

const message = useMessage();
const query = ref("");
const loading = ref(false);
const submitting = ref(false);
const results = ref<TmdbSearchResult[]>([]);
const selected = ref<TmdbSearchResult | null>(null);

watch(
  () => props.show,
  (visible) => {
    if (visible && props.context) {
      query.value = props.context.suggested_query || props.context.title || "";
      results.value = [];
      selected.value = null;
      if (query.value) {
        doSearch();
      }
    }
  }
);

async function doSearch() {
  if (!query.value.trim()) return;
  loading.value = true;
  try {
    const mediaType =
      props.context?.media_type === "tv"
        ? "tv"
        : props.context?.media_type === "movie"
          ? "movie"
          : "multi";
    results.value = await searchTmdb(query.value.trim(), mediaType);
  } catch (e) {
    message.error(e instanceof Error ? e.message : "搜索失败");
  } finally {
    loading.value = false;
  }
}

async function confirmMatch() {
  if (!selected.value) {
    message.warning("请先选择一个 TMDB 条目");
    return;
  }
  submitting.value = true;
  try {
    await manualMatch(props.mediaId, {
      tmdb_id: selected.value.tmdb_id,
      tmdb_type: selected.value.media_type,
      scrape_immediately: true,
    });
    message.success("匹配成功，刮削已完成");
    emit("matched");
    emit("update:show", false);
  } catch (e) {
    message.error(e instanceof Error ? e.message : "匹配失败");
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <NModal
    :show="show"
    preset="card"
    title="手动匹配 TMDB"
    style="width: 900px; max-width: 95vw"
    @update:show="emit('update:show', $event)"
  >
    <NText v-if="context?.failure_reason" depth="3" style="display: block; margin-bottom: 12px">
      {{ context.failure_reason }}
    </NText>

    <NSpace vertical size="large">
      <NSpace>
        <NInput v-model:value="query" placeholder="搜索 TMDB" style="width: 360px" />
        <NButton type="primary" :loading="loading" @click="doSearch">搜索</NButton>
      </NSpace>

      <NSpin :show="loading">
        <NEmpty v-if="!results.length" description="输入关键词搜索 TMDB" />
        <NGrid v-else cols="1 s:2" :x-gap="12" :y-gap="12">
          <NGi v-for="item in results" :key="`${item.media_type}-${item.tmdb_id}`">
            <div
              :style="{
                display: 'flex',
                gap: '12px',
                padding: '12px',
                borderRadius: '8px',
                cursor: 'pointer',
                border:
                  selected?.tmdb_id === item.tmdb_id &&
                  selected?.media_type === item.media_type
                    ? '2px solid #18a058'
                    : '1px solid #eee',
              }"
              @click="selected = item"
            >
              <div
                :style="{
                  width: '60px',
                  height: '90px',
                  flexShrink: 0,
                  borderRadius: '4px',
                  background: '#f0f0f0',
                  backgroundImage: item.poster_path
                    ? `url(${posterUrl(item.poster_path, 'w92')})`
                    : undefined,
                  backgroundSize: 'cover',
                }"
              />
              <div>
                <NText strong>{{ item.title }}</NText>
                <div>
                  <NTag size="small">{{ item.media_type }}</NTag>
                  <NText depth="3"> · {{ item.year ?? "-" }}</NText>
                </div>
                <NText depth="3" style="font-size: 12px">
                  {{ item.overview?.slice(0, 80) }}...
                </NText>
              </div>
            </div>
          </NGi>
        </NGrid>
      </NSpin>

      <NSpace justify="end">
        <NButton @click="emit('update:show', false)">取消</NButton>
        <NButton type="primary" :loading="submitting" @click="confirmMatch">
          确认匹配并刮削
        </NButton>
      </NSpace>
    </NSpace>
  </NModal>
</template>
