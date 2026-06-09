<script setup lang="ts">
import { computed } from "vue";
import {
  NButton,
  NDescriptions,
  NDescriptionsItem,
  NModal,
  NSpace,
  NTag,
  NText,
} from "naive-ui";
import type { EpisodeDetail } from "@/api";

const props = defineProps<{
  show: boolean;
  episode: EpisodeDetail | null;
  loading?: boolean;
}>();

const emit = defineEmits<{
  "update:show": [value: boolean];
}>();

const title = computed(() => {
  if (!props.episode) return "";
  const s = String(props.episode.season_number).padStart(2, "0");
  const e = String(props.episode.episode_number).padStart(2, "0");
  return props.episode.title || `第 ${props.episode.season_number} 季 第 ${props.episode.episode_number} 集`;
});

function close() {
  emit("update:show", false);
}
</script>

<template>
  <NModal
    :show="show"
    preset="card"
    :title="title"
    style="width: min(560px, 92vw)"
    @update:show="emit('update:show', $event)"
  >
    <div v-if="episode" class="episode-modal">
      <div v-if="episode.thumb_url" class="episode-modal-thumb">
        <img :src="episode.thumb_url" alt="剧照" />
      </div>

      <NSpace size="small" style="margin-bottom: 12px">
        <NTag size="small" type="info">
          S{{ String(episode.season_number).padStart(2, "0") }}E{{
            String(episode.episode_number).padStart(2, "0")
          }}
        </NTag>
        <NTag v-if="episode.air_date" size="small">{{ episode.air_date }}</NTag>
        <NTag v-if="episode.has_nfo" size="small" type="success">NFO</NTag>
        <NTag v-if="episode.has_thumb" size="small" type="success">剧照</NTag>
      </NSpace>

      <NText depth="2" style="line-height: 1.75; display: block; margin-bottom: 16px">
        {{ episode.overview || "暂无简介（运行刮削任务后会写入库内 NFO 文件）" }}
      </NText>

      <NDescriptions bordered :column="1" size="small" label-placement="left">
        <NDescriptionsItem label="源路径">{{ episode.source_path }}</NDescriptionsItem>
        <NDescriptionsItem v-if="episode.strm_target" label="STRM 指向">
          {{ episode.strm_target }}
        </NDescriptionsItem>
        <NDescriptionsItem label="库路径">
          {{ episode.library_path ?? "尚未整理" }}
        </NDescriptionsItem>
        <NDescriptionsItem label="状态">{{ episode.file_status }}</NDescriptionsItem>
      </NDescriptions>
    </div>

    <template #footer>
      <NButton @click="close">关闭</NButton>
    </template>
  </NModal>
</template>

<style scoped>
.episode-modal-thumb {
  margin: -4px 0 16px;
  border-radius: 10px;
  overflow: hidden;
  background: #eceff4;
}

.episode-modal-thumb img {
  display: block;
  width: 100%;
  max-height: 220px;
  object-fit: cover;
}
</style>
