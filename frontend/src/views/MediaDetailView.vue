<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import {
  NButton,
  NPopconfirm,
  NProgress,
  NSpin,
  NTabPane,
  NTabs,
  NTag,
  useMessage,
} from "naive-ui";
import EpisodeDetailModal from "@/components/EpisodeDetailModal.vue";
import ManualMatchModal from "@/components/ManualMatchModal.vue";
import {
  backdropUrl,
  deleteMediaLibrary,
  deleteSourceFileLibrary,
  fetchEpisodeDetail,
  fetchMatchContext,
  fetchMediaDetail,
  fieldStatusLabels,
  logoUrl,
  posterUrl,
  reorganizeMedia,
  scrapeFieldLabels,
  scrapeMedia,
  scrapeStatusLabels,
  TV_ONLY_SCRAPE_FIELDS,
  type EpisodeDetail,
  type MatchContext,
  type MediaDetail,
  type SourceFile,
} from "@/api";

const props = defineProps<{ id: string }>();
const router = useRouter();
const message = useMessage();

const loading = ref(true);
const scraping = ref(false);
const reorganizing = ref(false);
const deletingAll = ref(false);
const deletingFileId = ref<string | null>(null);
const media = ref<MediaDetail | null>(null);
const matchContext = ref<MatchContext | null>(null);
const showMatch = ref(false);
const showEpisode = ref(false);
const episodeLoading = ref(false);
const episodeDetail = ref<EpisodeDetail | null>(null);
const activeTab = ref("episodes");
const activeSeason = ref<number | null>(null);

const hasLibraryFiles = computed(
  () => media.value?.source_files.some((f) => f.library_path) ?? false
);

const isTv = computed(() => media.value?.media_type === "tv");

const heroBackdrop = computed(() => {
  if (!media.value) return "";
  if (media.value.backdrop_path) return backdropUrl(media.value.backdrop_path, "w1280");
  if (media.value.poster_path) return posterUrl(media.value.poster_path, "w780");
  return "";
});

const heroPosterOnly = computed(
  () => media.value && !media.value.backdrop_path && !!media.value.poster_path
);

const seasonGroups = computed(() => {
  if (!media.value) return [];
  const map = new Map<number, SourceFile[]>();
  for (const file of media.value.source_files) {
    const season = file.parsed_season ?? 1;
    const list = map.get(season) ?? [];
    list.push(file);
    map.set(season, list);
  }
  return [...map.entries()]
    .sort(([a], [b]) => a - b)
    .map(([season, files]) => ({
      season,
      files: [...files].sort(
        (a, b) => (a.parsed_episode ?? 1) - (b.parsed_episode ?? 1)
      ),
    }));
});

watch(seasonGroups, (groups) => {
  if (!groups.length) {
    activeSeason.value = null;
    return;
  }
  if (activeSeason.value == null || !groups.some((g) => g.season === activeSeason.value)) {
    activeSeason.value = groups[0].season;
  }
});

const activeSeasonFiles = computed(() => {
  if (!isTv.value) return media.value?.source_files ?? [];
  const group = seasonGroups.value.find((g) => g.season === activeSeason.value);
  return group?.files ?? [];
});

const visibleScrapeFields = computed(() => {
  if (!media.value) return [];
  return media.value.scrape_fields.filter(
    (f) => isTv.value || !TV_ONLY_SCRAPE_FIELDS.has(f.field_key)
  );
});

const scrapeProgress = computed(() => {
  const fields = visibleScrapeFields.value;
  const active = fields.filter((f) => f.status !== "skipped");
  const ok = active.filter((f) => f.status === "ok").length;
  const missing = active.filter((f) => f.status === "missing").length;
  const pending = active.filter((f) => f.status === "pending").length;
  const failed = active.filter((f) => f.status === "failed").length;
  const done = ok + missing;
  const total = active.length || 1;
  return {
    ok,
    missing,
    pending,
    failed,
    done,
    total,
    percent: Math.round((done / total) * 100),
  };
});

const metaLine = computed(() => {
  if (!media.value) return "";
  const parts: string[] = [];
  parts.push(media.value.media_type === "tv" ? "剧集" : "电影");
  if (media.value.year) parts.push(String(media.value.year));
  if (isTv.value && seasonGroups.value.length) {
    parts.push(`${seasonGroups.value.length} 季`);
  }
  parts.push(`${media.value.source_files.length} 个文件`);
  return parts.join(" · ");
});

function episodeLabel(file: SourceFile) {
  const s = String(file.parsed_season ?? 1).padStart(2, "0");
  const e = String(file.parsed_episode ?? 1).padStart(2, "0");
  return `E${e}`;
}

function episodeCode(file: SourceFile) {
  const s = String(file.parsed_season ?? 1).padStart(2, "0");
  const e = String(file.parsed_episode ?? 1).padStart(2, "0");
  return `S${s}E${e}`;
}

function fileStatusType(status: string) {
  if (status === "linked") return "success";
  if (status === "error") return "error";
  return "default";
}

function scrapeChipClass(status: string) {
  if (status === "ok" || status === "missing") return "ok";
  if (status === "failed") return "failed";
  if (status === "pending") return "pending";
  return "default";
}

async function load() {
  loading.value = true;
  try {
    media.value = await fetchMediaDetail(props.id);
    matchContext.value = await fetchMatchContext(props.id);
  } catch (e) {
    message.error(e instanceof Error ? e.message : "加载失败");
  } finally {
    loading.value = false;
  }
}

async function handleScrape(force = false) {
  scraping.value = true;
  try {
    media.value = await scrapeMedia(props.id, force);
    message.success("刮削完成");
  } catch (e) {
    message.error(e instanceof Error ? e.message : "刮削失败");
  } finally {
    scraping.value = false;
  }
}

async function handleDeleteAllLibrary() {
  deletingAll.value = true;
  try {
    const result = await deleteMediaLibrary(props.id);
    await load();
    message.success(`已删除库内 ${result.removed} 个文件，源文件保留`);
  } catch (e) {
    message.error(e instanceof Error ? e.message : "删除失败");
  } finally {
    deletingAll.value = false;
  }
}

async function handleDeleteFileLibrary(sourceFileId: string) {
  deletingFileId.value = sourceFileId;
  try {
    await deleteSourceFileLibrary(props.id, sourceFileId);
    await load();
    message.success("已删除该集库内文件");
  } catch (e) {
    message.error(e instanceof Error ? e.message : "删除失败");
  } finally {
    deletingFileId.value = null;
  }
}

async function handleReorganize() {
  reorganizing.value = true;
  try {
    media.value = await reorganizeMedia(props.id);
    message.success("重新整理完成");
  } catch (e) {
    message.error(e instanceof Error ? e.message : "整理失败");
  } finally {
    reorganizing.value = false;
  }
}

async function openEpisode(file: SourceFile) {
  showEpisode.value = true;
  episodeLoading.value = true;
  episodeDetail.value = null;
  try {
    episodeDetail.value = await fetchEpisodeDetail(props.id, file.id);
  } catch (e) {
    message.error(e instanceof Error ? e.message : "加载集详情失败");
    showEpisode.value = false;
  } finally {
    episodeLoading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <NSpin :show="loading">
    <div v-if="media" class="detail-page">
      <!-- 顶部 Banner：借鉴 Jellyfin / Emby 宽幅背景 -->
      <section class="hero-banner">
        <img
          v-if="heroBackdrop"
          class="hero-banner-img"
          :class="{ 'hero-banner-img--poster': heroPosterOnly }"
          :src="heroBackdrop"
          :alt="media.title"
        />
        <div v-else class="hero-banner-fallback" />
        <div class="hero-shade-left" />
        <div class="hero-shade-bottom" />

        <button type="button" class="back-btn" @click="router.back()">
          ← 返回列表
        </button>

        <div class="hero-banner-content">
          <div class="hero-poster-wrap">
            <img
              v-if="media.poster_path"
              class="hero-poster"
              :src="posterUrl(media.poster_path, 'w342')"
              :alt="media.title"
            />
            <div v-else class="hero-poster hero-poster-empty">暂无海报</div>
          </div>

          <div class="hero-text">
            <p class="hero-meta-line">{{ metaLine }}</p>
            <div class="hero-title-block">
              <img
                v-if="media.logo_path"
                class="hero-logo"
                :src="logoUrl(media.logo_path, 'w500')"
                :alt="media.title"
              />
              <h1 v-else class="hero-title">{{ media.title }}</h1>
            </div>
            <p
              v-if="media.original_title && media.original_title !== media.title"
              class="hero-original"
            >
              {{ media.original_title }}
            </p>

            <div class="hero-badges">
              <NTag
                size="small"
                round
                :bordered="false"
                :type="media.scrape_status === 'complete' ? 'success' : 'warning'"
              >
                {{ scrapeStatusLabels[media.scrape_status] ?? media.scrape_status }}
              </NTag>
              <NTag v-if="media.tmdb_id" size="small" round :bordered="false">
                TMDB {{ media.tmdb_id }}
              </NTag>
              <NTag
                v-if="media.match_confidence != null"
                size="small"
                round
                :bordered="false"
                type="info"
              >
                匹配置信 {{ Math.round(media.match_confidence * 100) }}%
              </NTag>
            </div>

            <p class="hero-overview">{{ media.overview || "暂无简介" }}</p>
          </div>
        </div>
      </section>

      <!-- 主体：深色内容区 + 操作栏 + Tab -->
      <div class="detail-body">
        <div class="body-inner">
          <div class="action-bar">
            <NButton type="primary" class="action-btn action-btn-primary" @click="showMatch = true">
              手动匹配
            </NButton>
            <NButton
              class="action-btn"
              :loading="reorganizing"
              :disabled="!media.tmdb_id"
              @click="handleReorganize"
            >
              重新整理
            </NButton>
            <NButton class="action-btn" :loading="scraping" @click="handleScrape(false)">
              增量刮削
            </NButton>
            <NButton
              type="primary"
              class="action-btn"
              :loading="scraping"
              @click="handleScrape(true)"
            >
              全量重刮
            </NButton>
            <NPopconfirm v-if="hasLibraryFiles" @positive-click="handleDeleteAllLibrary">
              <template #trigger>
                <NButton type="warning" ghost class="action-btn" :loading="deletingAll">
                  删除库内整理
                </NButton>
              </template>
              仅删除影视库链接，源文件保留
            </NPopconfirm>
          </div>

          <div class="stats-card">
            <div class="stat-item">
              <span class="stat-label">刮削进度</span>
              <div class="stat-progress">
                <NProgress
                  type="line"
                  :percentage="scrapeProgress.percent"
                  :height="8"
                  :border-radius="4"
                  :show-indicator="false"
                  color="#6366f1"
                  rail-color="rgba(255,255,255,0.08)"
                />
                <span class="stat-value">
                  {{ scrapeProgress.done }}/{{ scrapeProgress.total }}
                  <template v-if="scrapeProgress.pending || scrapeProgress.failed">
                    · 待处理 {{ scrapeProgress.pending }} · 失败 {{ scrapeProgress.failed }}
                  </template>
                </span>
              </div>
            </div>
          </div>

          <NTabs v-model:value="activeTab" type="line" animated class="detail-tabs">
            <NTabPane name="episodes" :tab="isTv ? '剧集' : '文件'">
              <template v-if="isTv && seasonGroups.length > 1">
                <div class="season-pills">
                  <button
                    v-for="group in seasonGroups"
                    :key="group.season"
                    type="button"
                    class="season-pill"
                    :class="{ active: activeSeason === group.season }"
                    @click="activeSeason = group.season"
                  >
                    第 {{ group.season }} 季
                    <span class="season-pill-count">{{ group.files.length }}</span>
                  </button>
                </div>
              </template>

              <div class="episode-grid">
                <article
                  v-for="file in activeSeasonFiles"
                  :key="file.id"
                  class="episode-card"
                  @click="openEpisode(file)"
                >
                  <div class="episode-card-top">
                    <span class="episode-num">{{ isTv ? episodeLabel(file) : "文件" }}</span>
                    <span v-if="isTv" class="episode-code">{{ episodeCode(file) }}</span>
                  </div>
                  <h3 class="episode-title">
                    {{ file.episode_title || file.parsed_title || "未命名" }}
                  </h3>
                  <div class="episode-card-foot">
                    <div class="episode-tags">
                      <NTag v-if="file.has_nfo" size="tiny" :bordered="false" type="success">
                        NFO
                      </NTag>
                      <NTag v-if="file.has_thumb" size="tiny" :bordered="false" type="success">
                        剧照
                      </NTag>
                      <NTag size="tiny" :bordered="false" :type="fileStatusType(file.file_status)">
                        {{ file.file_status }}
                      </NTag>
                    </div>
                    <NPopconfirm
                      v-if="file.library_path"
                      @positive-click="handleDeleteFileLibrary(file.id)"
                    >
                      <template #trigger>
                        <NButton
                          size="tiny"
                          quaternary
                          type="warning"
                          :loading="deletingFileId === file.id"
                          @click.stop
                        >
                          删库内
                        </NButton>
                      </template>
                      仅删除库内该集
                    </NPopconfirm>
                  </div>
                </article>
              </div>
            </NTabPane>

            <NTabPane name="scrape" tab="刮削状态">
              <div class="scrape-grid">
                <div
                  v-for="field in visibleScrapeFields"
                  :key="field.field_key"
                  class="scrape-card"
                  :class="scrapeChipClass(field.status)"
                >
                  <span class="scrape-card-label">
                    {{ scrapeFieldLabels[field.field_key] ?? field.field_key }}
                  </span>
                  <span class="scrape-card-status">
                    {{ fieldStatusLabels[field.status] ?? field.status }}
                  </span>
                </div>
              </div>
            </NTabPane>

            <NTabPane name="sources" tab="源文件">
              <div class="source-grid">
                <div v-for="file in media.source_files" :key="file.id" class="source-card">
                  <div class="source-card-head">
                    <NTag size="tiny" :bordered="false">
                      {{ file.is_strm ? "STRM" : "视频" }}
                    </NTag>
                    <span v-if="isTv" class="source-ep">{{ episodeCode(file) }}</span>
                  </div>
                  <p class="source-path">{{ file.source_path }}</p>
                  <p v-if="file.library_path" class="source-path lib">库：{{ file.library_path }}</p>
                </div>
              </div>
            </NTabPane>
          </NTabs>
        </div>
      </div>

      <EpisodeDetailModal
        v-model:show="showEpisode"
        :episode="episodeDetail"
        :loading="episodeLoading"
      />

      <ManualMatchModal
        v-model:show="showMatch"
        :media-id="props.id"
        :context="matchContext"
        @matched="load"
      />
    </div>
  </NSpin>
</template>

<style scoped>
.detail-page {
  margin: -24px;
  min-height: calc(100vh - 56px);
  background: #0f1117;
  color: #e8eaef;
}

/* ---- Hero Banner (Emby / Jellyfin style) ---- */
.hero-banner {
  position: relative;
  width: 100%;
  aspect-ratio: 21 / 9;
  max-height: 420px;
  min-height: 240px;
  overflow: hidden;
  background: #1a1d28;
}

.hero-banner-img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center 30%;
}

.hero-banner-img--poster {
  object-fit: contain;
  object-position: right center;
  width: auto;
  max-width: 38%;
  right: clamp(16px, 5vw, 64px);
  left: auto;
  filter: drop-shadow(0 12px 40px rgba(0, 0, 0, 0.55));
}

.hero-banner-fallback {
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, #1e2230 0%, #2a3044 100%);
}

.hero-shade-left {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    to right,
    rgba(15, 17, 23, 0.95) 0%,
    rgba(15, 17, 23, 0.55) 48%,
    transparent 75%
  );
  pointer-events: none;
  z-index: 1;
}

.hero-shade-bottom {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    to top,
    #0f1117 0%,
    rgba(15, 17, 23, 0.75) 28%,
    transparent 60%
  );
  pointer-events: none;
  z-index: 1;
}

.back-btn {
  position: absolute;
  top: 16px;
  left: clamp(16px, 3vw, 32px);
  z-index: 3;
  border: 1px solid rgba(255, 255, 255, 0.2);
  background: rgba(15, 17, 23, 0.55);
  backdrop-filter: blur(10px);
  color: #fff;
  font-size: 13px;
  padding: 8px 14px;
  border-radius: 999px;
  cursor: pointer;
  transition: background 0.2s, border-color 0.2s;
}

.back-btn:hover {
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(255, 255, 255, 0.35);
}

.hero-banner-content {
  position: absolute;
  left: 0;
  bottom: 0;
  z-index: 2;
  display: flex;
  align-items: flex-end;
  gap: clamp(16px, 3vw, 28px);
  padding: 0 clamp(16px, 3vw, 32px) clamp(20px, 4vw, 36px);
  max-width: min(920px, 92%);
}

.hero-poster-wrap {
  flex-shrink: 0;
}

.hero-poster {
  width: clamp(100px, 14vw, 148px);
  height: auto;
  aspect-ratio: 2 / 3;
  object-fit: cover;
  border-radius: 10px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.55);
  border: 2px solid rgba(255, 255, 255, 0.12);
  display: block;
}

.hero-poster-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(145deg, #3d4460, #252836);
  color: rgba(255, 255, 255, 0.45);
  font-size: 12px;
}

.hero-text {
  min-width: 0;
  padding-bottom: 4px;
}

.hero-meta-line {
  margin: 0 0 8px;
  font-size: 12px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgba(255, 255, 255, 0.55);
}

.hero-title-block {
  min-height: 48px;
  display: flex;
  align-items: flex-end;
}

.hero-logo {
  max-width: min(380px, 90%);
  max-height: 96px;
  width: auto;
  height: auto;
  object-fit: contain;
  object-position: left bottom;
  display: block;
  filter: drop-shadow(0 2px 16px rgba(0, 0, 0, 0.55));
}

.hero-title {
  margin: 0;
  font-size: clamp(22px, 3.8vw, 40px);
  font-weight: 700;
  line-height: 1.12;
  letter-spacing: -0.02em;
  color: #fff;
}

.hero-original {
  margin: 6px 0 0;
  font-size: 14px;
  color: rgba(255, 255, 255, 0.55);
}

.hero-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.hero-overview {
  margin: 14px 0 0;
  font-size: 14px;
  line-height: 1.65;
  color: rgba(255, 255, 255, 0.78);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* ---- Body ---- */
.detail-body {
  position: relative;
  margin-top: -24px;
  padding-top: 8px;
  background: linear-gradient(to bottom, transparent, #0f1117 32px);
}

.body-inner {
  max-width: 1100px;
  margin: 0 auto;
  padding: 0 clamp(16px, 3vw, 32px) 40px;
}

.action-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  padding: 16px 0 20px;
}

.action-btn {
  border-radius: 999px !important;
  font-weight: 500;
}

.action-btn-primary {
  box-shadow: 0 4px 16px rgba(99, 102, 241, 0.35);
}

.stats-card {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 14px;
  padding: 16px 18px;
  margin-bottom: 20px;
}

.stat-label {
  display: block;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.45);
  margin-bottom: 10px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.stat-progress {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.stat-value {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.65);
}

.detail-tabs :deep(.n-tabs-nav) {
  margin-bottom: 4px;
}

.detail-tabs :deep(.n-tabs-tab) {
  color: rgba(255, 255, 255, 0.5) !important;
  font-weight: 500;
}

.detail-tabs :deep(.n-tabs-tab--active) {
  color: #fff !important;
}

.detail-tabs :deep(.n-tabs-bar) {
  background: #6366f1 !important;
}

/* ---- Season pills ---- */
.season-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.season-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.04);
  color: rgba(255, 255, 255, 0.7);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.season-pill:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
}

.season-pill.active {
  background: #6366f1;
  border-color: #6366f1;
  color: #fff;
}

.season-pill-count {
  font-size: 11px;
  opacity: 0.75;
  background: rgba(0, 0, 0, 0.2);
  padding: 2px 7px;
  border-radius: 999px;
}

/* ---- Episode cards ---- */
.episode-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
}

.episode-card {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  padding: 14px 16px;
  cursor: pointer;
  transition: background 0.2s, border-color 0.2s, transform 0.15s;
}

.episode-card:hover {
  background: rgba(255, 255, 255, 0.07);
  border-color: rgba(99, 102, 241, 0.4);
  transform: translateY(-2px);
}

.episode-card-top {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 8px;
}

.episode-num {
  font-size: 22px;
  font-weight: 700;
  color: #6366f1;
  line-height: 1;
}

.episode-code {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.4);
  font-variant-numeric: tabular-nums;
}

.episode-title {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.88);
  line-height: 1.45;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 2.9em;
}

.episode-card-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.episode-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

/* ---- Scrape grid ---- */
.scrape-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
}

.scrape-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px 14px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.03);
}

.scrape-card.ok {
  border-color: rgba(52, 211, 153, 0.25);
  background: rgba(52, 211, 153, 0.08);
}

.scrape-card.failed {
  border-color: rgba(248, 113, 113, 0.25);
  background: rgba(248, 113, 113, 0.08);
}

.scrape-card.pending {
  border-color: rgba(251, 191, 36, 0.25);
  background: rgba(251, 191, 36, 0.08);
}

.scrape-card-label {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.85);
}

.scrape-card-status {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.45);
}

/* ---- Source files ---- */
.source-grid {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.source-card {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  padding: 12px 14px;
}

.source-card-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.source-ep {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.45);
  font-variant-numeric: tabular-nums;
}

.source-path {
  margin: 0;
  font-size: 12px;
  line-height: 1.55;
  color: rgba(255, 255, 255, 0.65);
  word-break: break-all;
}

.source-path.lib {
  margin-top: 6px;
  color: rgba(255, 255, 255, 0.38);
}

@media (max-width: 768px) {
  .hero-banner {
    aspect-ratio: 16 / 10;
    max-height: 320px;
  }

  .hero-banner-content {
    flex-direction: column;
    align-items: flex-start;
    max-width: 100%;
  }

  .hero-poster {
    width: 88px;
  }

  .episode-grid {
    grid-template-columns: 1fr;
  }
}
</style>
