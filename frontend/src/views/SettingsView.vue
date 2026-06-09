<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import {
  NAlert,
  NButton,
  NCard,
  NCheckbox,
  NForm,
  NFormItem,
  NGrid,
  NGi,
  NInput,
  NInputNumber,
  NSpace,
  NSpin,
  useMessage,
} from "naive-ui";
import { fetchSettings, updateSettings, type ScrapeConfig, type ScrapeOptions } from "@/api";

const message = useMessage();
const loading = ref(false);
const saving = ref(false);
const savingTmdb = ref(false);

const scrapeLabels: Record<keyof ScrapeOptions, string> = {
  basic: "基础信息",
  overview: "简介",
  poster: "海报",
  backdrop: "背景图",
  logo: "Logo",
  cast: "演员",
  crew: "演职员",
  genres: "类型",
  keywords: "关键词",
  trailers: "预告片",
  external_ids: "外部 ID",
  season_poster: "季海报",
  episode_still: "集剧照",
  episode_overview: "集简介",
};

const config = reactive<ScrapeConfig>({
  scrape_options: {
    basic: true,
    overview: true,
    poster: true,
    backdrop: true,
    logo: true,
    cast: true,
    crew: true,
    genres: true,
    keywords: true,
    trailers: true,
    external_ids: true,
    season_poster: true,
    episode_still: true,
    episode_overview: true,
  },
  image_options: {
    language: "zh-CN",
    fallback_en: true,
    download_images: true,
    image_storage: "url",
  },
  match_options: {
    auto_match_enabled: true,
    confidence_threshold: 0.75,
    on_low_confidence: "needs_manual_match",
  },
});

const tmdbForm = reactive({
  api_key: "",
  base_url: "https://api.themoviedb.org/3",
  language: "zh-CN",
  scrape_concurrency: 8,
});

const tmdbInfo = reactive({
  api_key_set: false,
  api_key_masked: null as string | null,
  config_source: "env",
  source_root: "",
  library_root: "",
});

function selectAll(value: boolean) {
  (Object.keys(config.scrape_options) as Array<keyof ScrapeOptions>).forEach((key) => {
    config.scrape_options[key] = value;
  });
}

async function loadSettings() {
  loading.value = true;
  try {
    const data = await fetchSettings();
    Object.assign(config, data.scrape_config);
    tmdbForm.base_url = data.tmdb_base_url;
    tmdbForm.language = data.tmdb_language;
    tmdbForm.scrape_concurrency = data.tmdb_scrape_concurrency;
    tmdbForm.api_key = "";
    tmdbInfo.api_key_set = data.tmdb_api_key_set;
    tmdbInfo.api_key_masked = data.tmdb_api_key_masked;
    tmdbInfo.config_source = data.tmdb_config_source;
    tmdbInfo.source_root = data.data_source_root;
    tmdbInfo.library_root = data.data_library_root;
  } catch (e) {
    message.error(e instanceof Error ? e.message : "加载设置失败");
  } finally {
    loading.value = false;
  }
}

async function saveTmdbSettings() {
  savingTmdb.value = true;
  try {
    const payload: {
      tmdb_base_url: string;
      tmdb_language: string;
      tmdb_scrape_concurrency: number;
      tmdb_api_key?: string;
    } = {
      tmdb_base_url: tmdbForm.base_url.trim(),
      tmdb_language: tmdbForm.language.trim(),
      tmdb_scrape_concurrency: tmdbForm.scrape_concurrency,
    };
    if (tmdbForm.api_key.trim()) {
      payload.tmdb_api_key = tmdbForm.api_key.trim();
    }
    const data = await updateSettings(payload);
    tmdbForm.api_key = "";
    tmdbInfo.api_key_set = data.tmdb_api_key_set;
    tmdbInfo.api_key_masked = data.tmdb_api_key_masked;
    tmdbInfo.config_source = data.tmdb_config_source;
    message.success("TMDB 配置已保存");
  } catch (e) {
    message.error(e instanceof Error ? e.message : "保存失败");
  } finally {
    savingTmdb.value = false;
  }
}

async function clearTmdbApiKey() {
  savingTmdb.value = true;
  try {
    const data = await updateSettings({ tmdb_api_key: "" });
    tmdbForm.api_key = "";
    tmdbInfo.api_key_set = data.tmdb_api_key_set;
    tmdbInfo.api_key_masked = data.tmdb_api_key_masked;
    message.success("已清除 TMDB API Key");
  } catch (e) {
    message.error(e instanceof Error ? e.message : "清除失败");
  } finally {
    savingTmdb.value = false;
  }
}

async function saveSettings() {
  saving.value = true;
  try {
    await updateSettings({ scrape_config: config });
    message.success("刮削配置已保存");
  } catch (e) {
    message.error(e instanceof Error ? e.message : "保存失败");
  } finally {
    saving.value = false;
  }
}

onMounted(loadSettings);
</script>

<template>
  <NSpin :show="loading">
    <NSpace vertical size="large">
      <NCard title="TMDB 配置">
        <NAlert type="info" style="margin-bottom: 16px">
          在此配置 TMDB API Key 与代理地址，保存后立即生效。留空 API Key 输入框则保持现有密钥不变。
        </NAlert>
        <NForm label-placement="left" label-width="120">
          <NFormItem label="API Key">
            <NInput
              v-model:value="tmdbForm.api_key"
              type="password"
              show-password-on="click"
              :placeholder="
                tmdbInfo.api_key_set
                  ? `已配置 ${tmdbInfo.api_key_masked ?? ''}，输入新 Key 可覆盖`
                  : '请输入 TMDB API Key'
              "
            />
          </NFormItem>
          <NFormItem label="代理 / Base URL">
            <NInput
              v-model:value="tmdbForm.base_url"
              placeholder="https://api.themoviedb.org/3 或 https://你的代理/3"
            />
          </NFormItem>
          <NAlert type="warning" style="margin-bottom: 12px">
            地址需包含 API 版本路径 <code>/3</code>。若填 https://api.tmdb.org 会自动补全为 .../3
          </NAlert>
          <NFormItem label="语言">
            <NInput v-model:value="tmdbForm.language" placeholder="zh-CN" />
          </NFormItem>
          <NFormItem label="刮削并发数">
            <NInputNumber
              v-model:value="tmdbForm.scrape_concurrency"
              :min="1"
              :max="32"
              :step="1"
              style="width: 160px"
            />
          </NFormItem>
          <NAlert type="info" style="margin-bottom: 12px">
            控制 TMDB 刮削时每集元数据与图片下载的并发线程数（1～32，默认 8）。数值越大越快，但可能更容易触发 TMDB 速率限制。
          </NAlert>
          <NFormItem label="配置来源">
            <span>{{ tmdbInfo.config_source === "db" ? "系统设置" : tmdbInfo.config_source === "mixed" ? "系统设置 + 环境变量" : "环境变量" }}</span>
          </NFormItem>
          <NSpace>
            <NButton type="primary" :loading="savingTmdb" @click="saveTmdbSettings">
              保存 TMDB 配置
            </NButton>
            <NButton v-if="tmdbInfo.api_key_set" :loading="savingTmdb" @click="clearTmdbApiKey">
              清除 API Key
            </NButton>
          </NSpace>
        </NForm>
      </NCard>

      <NCard title="数据目录（只读）">
        <NGrid cols="1 m:2" :x-gap="16" :y-gap="8">
          <NGi>源目录：{{ tmdbInfo.source_root }}</NGi>
          <NGi>影视库目录：{{ tmdbInfo.library_root }}</NGi>
        </NGrid>
        <NAlert type="warning" style="margin-top: 12px" title="数据目录仍通过环境变量配置" />
      </NCard>

      <NCard title="刮削项配置（默认全选）">
        <NSpace style="margin-bottom: 12px">
          <NButton size="small" @click="selectAll(true)">全选</NButton>
          <NButton size="small" @click="selectAll(false)">全不选</NButton>
          <NButton size="small" @click="selectAll(true)">恢复默认</NButton>
        </NSpace>
        <NGrid cols="2 s:3 m:4" :x-gap="12" :y-gap="8">
          <NGi v-for="(label, key) in scrapeLabels" :key="key">
            <NCheckbox v-model:checked="config.scrape_options[key as keyof ScrapeOptions]">
              {{ label }}
            </NCheckbox>
          </NGi>
        </NGrid>
      </NCard>

      <NCard title="匹配策略">
        <NForm label-placement="left" label-width="140">
          <NFormItem label="自动匹配">
            <NCheckbox v-model:checked="config.match_options.auto_match_enabled" />
          </NFormItem>
          <NFormItem label="置信度阈值">
            <NInputNumber
              v-model:value="config.match_options.confidence_threshold"
              :min="0"
              :max="1"
              :step="0.05"
            />
          </NFormItem>
          <NFormItem label="低置信度策略">
            <NInput v-model:value="config.match_options.on_low_confidence" />
          </NFormItem>
        </NForm>
      </NCard>

      <NButton type="primary" :loading="saving" @click="saveSettings">保存刮削配置</NButton>
    </NSpace>
  </NSpin>
</template>
