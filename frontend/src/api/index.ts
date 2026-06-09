import axios from "axios";

export const api = axios.create({
  baseURL: "/api/v1",
  timeout: 120000,
  withCredentials: true,
});

export interface AuthBootstrap {
  auth_enabled: boolean;
  app_display_name: string;
}

export interface AuthSession {
  username: string;
  app_display_name: string;
  access_token?: string | null;
}

export interface HealthInfo {
  status: string;
  database: string;
  redis: string;
  scheduler: boolean;
  mode: string;
}

export interface ScrapeOptions {
  basic: boolean;
  overview: boolean;
  poster: boolean;
  backdrop: boolean;
  logo: boolean;
  cast: boolean;
  crew: boolean;
  genres: boolean;
  keywords: boolean;
  trailers: boolean;
  external_ids: boolean;
  season_poster: boolean;
  episode_still: boolean;
  episode_overview: boolean;
}

export interface ScrapeConfig {
  scrape_options: ScrapeOptions;
  image_options: {
    language: string;
    fallback_en: boolean;
    download_images: boolean;
    image_storage: string;
  };
  match_options: {
    auto_match_enabled: boolean;
    confidence_threshold: number;
    on_low_confidence: string;
  };
}

export interface SystemSettings {
  scrape_config: ScrapeConfig;
  app_display_name: string;
  tmdb_api_key_set: boolean;
  tmdb_api_key_masked: string | null;
  tmdb_base_url: string;
  tmdb_language: string;
  tmdb_scrape_concurrency: number;
  tmdb_config_source: string;
  data_source_root: string;
  data_library_root: string;
}

export interface TaskItem {
  id: string;
  name: string;
  source_path: string;
  library_path: string;
  cron_expr: string;
  task_type: string;
  enabled: boolean;
  use_global_scrape_config: boolean;
  scrape_options: ScrapeOptions | null;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface TaskRun {
  id: string;
  task_id: string;
  status: string;
  message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface MediaItem {
  id: string;
  media_type: string;
  title: string;
  year: number | null;
  poster_path: string | null;
  backdrop_path?: string | null;
  overview?: string | null;
  genres?: string[];
  scrape_status: string;
  match_status: string;
  tmdb_id: number | null;
}

export interface ScrapeFieldStatus {
  field_key: string;
  status: string;
  error_message: string | null;
}

export interface SourceFile {
  id: string;
  source_path: string;
  library_path: string | null;
  link_type: string | null;
  file_status: string;
  parsed_title: string | null;
  parsed_season: number | null;
  parsed_episode: number | null;
  error_message: string | null;
  is_strm?: boolean;
  strm_target?: string | null;
  episode_title?: string | null;
  has_nfo?: boolean;
  has_thumb?: boolean;
}

export interface EpisodeDetail {
  source_file_id: string;
  season_number: number;
  episode_number: number;
  title: string | null;
  overview: string | null;
  air_date: string | null;
  has_nfo: boolean;
  has_thumb: boolean;
  thumb_url: string | null;
  source_path: string;
  library_path: string | null;
  file_status: string;
  is_strm?: boolean;
  strm_target?: string | null;
}

export interface MediaDetail extends MediaItem {
  original_title: string | null;
  overview: string | null;
  backdrop_path: string | null;
  logo_path: string | null;
  match_confidence: number | null;
  metadata_json: Record<string, unknown>;
  scrape_fields: ScrapeFieldStatus[];
  source_files: SourceFile[];
  last_scraped_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface MatchContext {
  media_id: string;
  title: string;
  year: number | null;
  media_type: string;
  scrape_status: string;
  match_confidence: number | null;
  source_files: SourceFile[];
  suggested_query: string;
  failure_reason: string | null;
}

export interface TmdbSearchResult {
  tmdb_id: number;
  media_type: string;
  title: string;
  original_title: string | null;
  year: number | null;
  overview: string | null;
  poster_path: string | null;
  vote_average: number | null;
}

export interface DashboardStats {
  total_media: number;
  complete: number;
  partial: number;
  pending: number;
  failed: number;
  needs_manual_match: number;
  total_files: number;
  linked_files: number;
  total_tasks: number;
  enabled_tasks: number;
}

export async function authBootstrap() {
  const { data } = await api.get<AuthBootstrap>("/auth/bootstrap");
  return data;
}

export async function authLogin(username: string, password: string) {
  const { data } = await api.post<AuthSession>("/auth/login", { username, password });
  return data;
}

export async function authMe() {
  const { data } = await api.get<AuthSession>("/auth/me");
  return data;
}

export async function authLogout() {
  await api.post("/auth/logout");
}

export async function fetchHealth() {
  const { data } = await api.get<HealthInfo>("/health");
  return data;
}

export async function fetchDashboardStats() {
  const { data } = await api.get<DashboardStats>("/dashboard/stats");
  return data;
}

export async function fetchSettings() {
  const { data } = await api.get<SystemSettings>("/settings");
  return data;
}

export async function updateSettings(payload: {
  scrape_config?: ScrapeConfig;
  app_display_name?: string;
  tmdb_api_key?: string | null;
  tmdb_base_url?: string;
  tmdb_language?: string;
  tmdb_scrape_concurrency?: number;
}) {
  const { data } = await api.put<SystemSettings>("/settings", payload);
  return data;
}

export async function fetchTasks() {
  const { data } = await api.get<TaskItem[]>("/tasks");
  return data;
}

export async function createTask(payload: Record<string, unknown>) {
  const { data } = await api.post<TaskItem>("/tasks", payload);
  return data;
}

export async function deleteTask(id: string) {
  await api.delete(`/tasks/${id}`);
}

export async function runTask(id: string) {
  const { data } = await api.post<{ status: string; task_id: string }>(`/tasks/${id}/run`);
  return data;
}

export async function runTaskSync(id: string) {
  const { data } = await api.post<TaskRun>(`/tasks/${id}/run/sync`);
  return data;
}

export async function fetchTaskRuns(id: string) {
  const { data } = await api.get<TaskRun[]>(`/tasks/${id}/runs`);
  return data;
}

export async function fetchMedia(params?: {
  page?: number;
  page_size?: number;
  scrape_status?: string;
  media_type?: string;
  q?: string;
}) {
  const { data } = await api.get<{
    items: MediaItem[];
    total: number;
    page: number;
    page_size: number;
  }>("/media", { params });
  return data;
}

export async function fetchMediaDetail(id: string) {
  const { data } = await api.get<MediaDetail>(`/media/${id}`);
  return data;
}

export async function fetchMatchContext(id: string) {
  const { data } = await api.get<MatchContext>(`/media/${id}/match-context`);
  return data;
}

export async function scrapeMedia(id: string, force = false) {
  const { data } = await api.post<MediaDetail>(`/media/${id}/scrape`, null, {
    params: { force },
  });
  return data;
}

export async function manualMatch(
  id: string,
  payload: {
    tmdb_id: number;
    tmdb_type: string;
    note?: string;
    scrape_immediately?: boolean;
  }
) {
  const { data } = await api.post<MediaDetail>(`/media/${id}/manual-match`, payload);
  return data;
}

export interface LibraryCleanupResult {
  removed: number;
  skipped: number;
  errors: number;
}

export async function deleteMediaLibrary(id: string) {
  const { data } = await api.delete<LibraryCleanupResult>(`/media/${id}/library`);
  return data;
}

export interface MediaResetResult {
  library_folders_removed: number;
  media_deleted: boolean;
  removed_paths: string[];
  related_media_reset?: number;
}

export async function resetMedia(id: string) {
  const { data } = await api.delete<MediaResetResult>(`/media/${id}`);
  return data;
}

export async function deleteSourceFileLibrary(mediaId: string, sourceFileId: string) {
  const { data } = await api.delete<LibraryCleanupResult>(
    `/media/${mediaId}/library/files/${sourceFileId}`
  );
  return data;
}

export async function reorganizeMedia(id: string) {
  const { data } = await api.post<MediaDetail>(`/media/${id}/reorganize`);
  return data;
}

export async function fetchEpisodeDetail(mediaId: string, sourceFileId: string) {
  const { data } = await api.get<EpisodeDetail>(
    `/media/${mediaId}/files/${sourceFileId}/episode`
  );
  return data;
}

export async function searchTmdb(q: string, media_type = "multi") {
  const { data } = await api.get<TmdbSearchResult[]>("/tmdb/search", {
    params: { q, media_type },
  });
  return data;
}

export function posterUrl(path: string | null, size = "w342") {
  if (!path) return "";
  if (path.startsWith("http")) return path;
  return `https://image.tmdb.org/t/p/${size}${path}`;
}

export function backdropUrl(path: string | null, size = "w1280") {
  return posterUrl(path, size);
}

/** TMDB 剧集/电影 Logo（透明 PNG） */
export function logoUrl(path: string | null, size = "w500") {
  return posterUrl(path, size);
}

export const scrapeStatusLabels: Record<string, string> = {
  pending: "待刮削",
  partial: "部分完成",
  complete: "已完成",
  failed: "失败",
  needs_manual_match: "待手动匹配",
};

export const fieldStatusLabels: Record<string, string> = {
  pending: "待处理",
  ok: "成功",
  missing: "无数据(已跳过)",
  failed: "失败",
  skipped: "已跳过",
};

export const scrapeFieldLabels: Record<string, string> = {
  basic: "基础信息",
  overview: "简介",
  poster: "海报",
  backdrop: "背景图",
  logo: "Logo",
  cast: "演员",
  crew: "制作人员",
  genres: "类型",
  keywords: "关键词",
  trailers: "预告片",
  external_ids: "外部 ID",
  season_poster: "季海报（仅剧集）",
  episode_still: "集剧照（仅剧集）",
  episode_overview: "集 NFO（仅剧集）",
};

/** 电影无季/集，不参与刮削进度与状态汇总 */
export const TV_ONLY_SCRAPE_FIELDS = new Set([
  "season_poster",
  "episode_still",
  "episode_overview",
]);
