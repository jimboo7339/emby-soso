<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import { NEmpty, NSpin, useMessage } from "naive-ui";
import { backdropUrl, fetchMedia, posterUrl, type MediaItem } from "@/api";

type WallCategory = "movie" | "tv" | "anime" | "variety";

const router = useRouter();
const message = useMessage();

const loading = ref(false);
const items = ref<MediaItem[]>([]);
const heroIndex = ref(0);
let heroTimer: ReturnType<typeof setInterval> | null = null;

const ANIME_KEYS = ["animation", "anime", "动画", "动漫"];
const VARIETY_KEYS = [
  "reality",
  "talk",
  "news",
  "documentary",
  "真人秀",
  "综艺",
  "脱口秀",
  "纪录",
];

function genreText(item: MediaItem) {
  return (item.genres ?? []).join(" ").toLowerCase();
}

function matchesKeywords(text: string, keys: string[]) {
  return keys.some((k) => text.includes(k.toLowerCase()));
}

function categorize(item: MediaItem): WallCategory {
  if (item.media_type === "movie") return "movie";

  const g = genreText(item);
  const title = (item.title ?? "").toLowerCase();

  if (matchesKeywords(g, ANIME_KEYS) || matchesKeywords(title, ANIME_KEYS)) {
    return "anime";
  }
  if (matchesKeywords(g, VARIETY_KEYS) || matchesKeywords(title, ["综艺", "真人秀"])) {
    return "variety";
  }
  return "tv";
}

const categorized = computed(() => {
  const buckets: Record<WallCategory, MediaItem[]> = {
    movie: [],
    tv: [],
    anime: [],
    variety: [],
  };
  for (const item of items.value) {
    buckets[categorize(item)].push(item);
  }
  return buckets;
});

const heroItems = computed(() =>
  items.value.filter((i) => i.backdrop_path || i.poster_path).slice(0, 8)
);

const currentHero = computed(() => heroItems.value[heroIndex.value] ?? null);

function heroImage(item: MediaItem) {
  if (item.backdrop_path) return backdropUrl(item.backdrop_path, "w1280");
  if (item.poster_path) return posterUrl(item.poster_path, "w780");
  return "";
}

function heroUsesPosterOnly(item: MediaItem) {
  return !item.backdrop_path && !!item.poster_path;
}

const sections = computed(() => {
  const cats = categorized.value;
  return [
    { key: "movie", title: "电影", icon: "🎬", list: cats.movie },
    { key: "tv", title: "电视剧", icon: "📺", list: cats.tv },
    { key: "anime", title: "动漫", icon: "✨", list: cats.anime },
    { key: "variety", title: "综艺", icon: "🎤", list: cats.variety },
  ].filter((s) => s.list.length > 0);
});

const hasData = computed(() => items.value.length > 0);

function goDetail(id: string) {
  router.push(`/media/${id}`);
}

function setHero(idx: number) {
  if (heroItems.value.length) {
    heroIndex.value = idx % heroItems.value.length;
  }
}

function startHeroRotation() {
  stopHeroRotation();
  if (heroItems.value.length <= 1) return;
  heroTimer = setInterval(() => {
    setHero(heroIndex.value + 1);
  }, 6000);
}

function stopHeroRotation() {
  if (heroTimer) {
    clearInterval(heroTimer);
    heroTimer = null;
  }
}

async function loadMedia() {
  loading.value = true;
  try {
    const data = await fetchMedia({ page: 1, page_size: 100 });
    items.value = data.items;
    heroIndex.value = 0;
    startHeroRotation();
  } catch (e) {
    message.error(e instanceof Error ? e.message : "加载媒体失败");
  } finally {
    loading.value = false;
  }
}

onMounted(loadMedia);
onUnmounted(stopHeroRotation);
</script>

<template>
  <div class="wall-page">
    <NSpin :show="loading">
      <NEmpty
        v-if="!loading && !hasData"
        description="暂无媒体数据。请先创建任务并运行扫描刮削。"
        class="wall-empty"
      />

      <template v-else-if="hasData">
        <!-- 顶部 Banner 轮播 -->
        <section v-if="currentHero" class="hero-section">
          <div
            class="hero-frame"
            :class="{ 'hero-frame--poster': heroUsesPosterOnly(currentHero) }"
            :style="
              heroUsesPosterOnly(currentHero) && heroImage(currentHero)
                ? { '--hero-poster-bg': `url(${heroImage(currentHero)})` }
                : undefined
            "
            @click="goDetail(currentHero.id)"
          >
            <img
              v-if="heroImage(currentHero)"
              class="hero-img"
              :src="heroImage(currentHero)"
              :alt="currentHero.title"
              loading="lazy"
            />
            <div class="hero-shade-bottom" />
            <div class="hero-shade-left" />
            <div class="hero-content">
              <p class="hero-tag">
                {{ categorize(currentHero) === "movie" ? "电影" : "剧集" }}
                <span v-if="currentHero.year"> · {{ currentHero.year }}</span>
              </p>
              <h2 class="hero-title">{{ currentHero.title || "未命名" }}</h2>
              <p class="hero-overview">
                {{ currentHero.overview || "暂无简介" }}
              </p>
            </div>
          </div>

          <div v-if="heroItems.length > 1" class="hero-dots">
            <button
              v-for="(item, idx) in heroItems"
              :key="item.id"
              class="hero-dot"
              :class="{ active: idx === heroIndex }"
              @mouseenter="setHero(idx)"
              @click.stop="setHero(idx)"
            />
          </div>
        </section>

        <div class="categories-wrap">
        <section v-for="section in sections" :key="section.key" class="category-section">
          <div class="category-head">
            <h3 class="category-title">
              <span class="category-icon">{{ section.icon }}</span>
              {{ section.title }}
            </h3>
            <span class="category-count">{{ section.list.length }} 部</span>
          </div>

          <div class="poster-row-outer">
            <div class="poster-row">
            <article
              v-for="item in section.list"
              :key="item.id"
              class="poster-card"
              @click="goDetail(item.id)"
            >
              <div class="poster-thumb-wrap">
                <img
                  v-if="item.poster_path"
                  class="poster-thumb"
                  :src="posterUrl(item.poster_path, 'w342')"
                  :alt="item.title"
                  loading="lazy"
                />
                <div v-else class="poster-thumb poster-thumb-empty">无海报</div>
              </div>
              <p class="poster-title" :title="item.title">{{ item.title || "未命名" }}</p>
              <p class="poster-meta">{{ item.year ?? "-" }}</p>
            </article>
            </div>
          </div>
        </section>
        </div>
      </template>
    </NSpin>
  </div>
</template>

<style scoped>
.wall-page {
  margin: -24px;
  min-height: calc(100vh - 56px);
  background: #0f1117;
  color: #fff;
}

.wall-empty {
  padding: 80px 24px;
}

/* ---- Hero Banner ---- */
.hero-section {
  position: relative;
  margin-bottom: 0;
}

.hero-frame {
  position: relative;
  width: 100%;
  aspect-ratio: 21 / 9;
  max-height: 460px;
  min-height: 220px;
  overflow: hidden;
  cursor: pointer;
  background: #1a1d28;
}

.hero-img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center 35%;
  display: block;
}

.hero-frame--poster .hero-img {
  object-fit: contain;
  object-position: right center;
  width: auto;
  max-width: 42%;
  right: clamp(16px, 4vw, 48px);
  left: auto;
  filter: drop-shadow(0 8px 24px rgba(0, 0, 0, 0.5));
}

.hero-frame--poster::before {
  content: "";
  position: absolute;
  inset: 0;
  background: var(--hero-poster-bg, #1a1d28) center / cover no-repeat;
  filter: blur(28px) brightness(0.45);
  transform: scale(1.08);
  z-index: 0;
}

.hero-frame--poster .hero-img {
  z-index: 1;
}

.hero-shade-left {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    to right,
    rgba(15, 17, 23, 0.92) 0%,
    rgba(15, 17, 23, 0.5) 42%,
    transparent 72%
  );
  pointer-events: none;
  z-index: 2;
}

.hero-frame--poster .hero-shade-left {
  background: linear-gradient(
    to right,
    rgba(15, 17, 23, 0.95) 0%,
    rgba(15, 17, 23, 0.55) 50%,
    transparent 78%
  );
}

.hero-shade-bottom {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    to top,
    #0f1117 0%,
    rgba(15, 17, 23, 0.6) 22%,
    transparent 55%
  );
  pointer-events: none;
  z-index: 2;
}

.hero-content {
  position: absolute;
  left: 0;
  bottom: 0;
  padding: 28px clamp(20px, 4vw, 48px) 36px;
  max-width: min(520px, 88%);
  z-index: 3;
}

.hero-tag {
  margin: 0 0 8px;
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  opacity: 0.75;
}

.hero-title {
  margin: 0 0 10px;
  font-size: clamp(22px, 3.5vw, 36px);
  font-weight: 700;
  line-height: 1.15;
  letter-spacing: -0.02em;
}

.hero-overview {
  margin: 0;
  font-size: 14px;
  line-height: 1.6;
  opacity: 0.82;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.hero-dots {
  position: absolute;
  bottom: 16px;
  right: clamp(20px, 4vw, 48px);
  display: flex;
  gap: 8px;
  z-index: 2;
}

.hero-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  border: none;
  padding: 0;
  background: rgba(255, 255, 255, 0.35);
  cursor: pointer;
  transition: transform 0.2s, background 0.2s;
}

.hero-dot.active {
  background: #fff;
  transform: scale(1.25);
}

.categories-wrap {
  position: relative;
  z-index: 3;
  margin-top: -32px;
  padding-top: 40px;
  background: linear-gradient(to bottom, transparent 0, #0f1117 48px);
}

/* ---- Category Rows ---- */
.category-section {
  padding: 8px 0 20px;
  overflow: visible;
}

.category-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  padding: 0 clamp(16px, 3vw, 32px) 12px;
}

.category-title {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}

.category-icon {
  font-size: 18px;
}

.category-count {
  font-size: 12px;
  opacity: 0.45;
}

.poster-row-outer {
  overflow: visible;
  padding: 12px 0 8px;
}

.poster-row {
  display: flex;
  gap: 14px;
  overflow-x: auto;
  overflow-y: visible;
  padding: 12px clamp(16px, 3vw, 32px) 12px;
  scroll-snap-type: x mandatory;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.2) transparent;
}

.poster-row::-webkit-scrollbar {
  height: 6px;
}

.poster-row::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.18);
  border-radius: 3px;
}

.poster-card {
  flex: 0 0 112px;
  cursor: pointer;
  scroll-snap-align: start;
  position: relative;
  z-index: 1;
}

.poster-card:hover {
  z-index: 10;
}

.poster-thumb-wrap {
  padding: 0;
}

.poster-thumb {
  width: 112px;
  height: 168px;
  border-radius: 8px;
  object-fit: cover;
  display: block;
  background: #252836;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.4);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  transform-origin: center center;
}

.poster-card:hover .poster-thumb {
  transform: scale(1.05);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.6);
}

.poster-thumb-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  opacity: 0.5;
  color: #fff;
}

.poster-title {
  margin: 8px 0 2px;
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.poster-meta {
  margin: 0;
  font-size: 11px;
  opacity: 0.45;
}

@media (max-width: 640px) {
  .hero-frame {
    aspect-ratio: 16 / 9;
    max-height: 280px;
  }

  .poster-card {
    flex-basis: 96px;
  }

  .poster-thumb {
    width: 96px;
    height: 144px;
  }
}
</style>
