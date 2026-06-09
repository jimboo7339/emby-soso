from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models import DEFAULT_SCRAPE_OPTIONS, TaskType


class ScrapeOptions(BaseModel):
    basic: bool = True
    overview: bool = True
    poster: bool = True
    backdrop: bool = True
    logo: bool = True
    cast: bool = True
    crew: bool = True
    genres: bool = True
    keywords: bool = True
    trailers: bool = True
    external_ids: bool = True
    season_poster: bool = True
    episode_still: bool = True
    episode_overview: bool = True

    @classmethod
    def default(cls) -> ScrapeOptions:
        return cls(**DEFAULT_SCRAPE_OPTIONS)


class ImageOptions(BaseModel):
    language: str = "zh-CN"
    fallback_en: bool = True
    download_images: bool = True
    image_storage: str = "local"


class MatchOptions(BaseModel):
    auto_match_enabled: bool = True
    confidence_threshold: float = 0.75
    on_low_confidence: str = "needs_manual_match"


class ScrapeConfig(BaseModel):
    scrape_options: ScrapeOptions = Field(default_factory=ScrapeOptions.default)
    image_options: ImageOptions = Field(default_factory=ImageOptions)
    match_options: MatchOptions = Field(default_factory=MatchOptions)


class SystemSettingsUpdate(BaseModel):
    scrape_config: ScrapeConfig | None = None
    app_display_name: str | None = None
    tmdb_api_key: str | None = None
    tmdb_base_url: str | None = None
    tmdb_language: str | None = None
    tmdb_scrape_concurrency: int | None = Field(default=None, ge=1, le=32)


class SystemSettingsResponse(BaseModel):
    scrape_config: ScrapeConfig
    app_display_name: str
    tmdb_api_key_set: bool
    tmdb_api_key_masked: str | None = None
    tmdb_base_url: str
    tmdb_language: str
    tmdb_scrape_concurrency: int = 8
    tmdb_config_source: str = "env"
    data_source_root: str
    data_library_root: str


class HealthResponse(BaseModel):
    status: str
    database: str
    redis: str
    scheduler: bool
    mode: str


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    username: str
    app_display_name: str
    access_token: str | None = None


class LogoutResponse(BaseModel):
    status: str


class AuthBootstrapResponse(BaseModel):
    auth_enabled: bool
    app_display_name: str


class TaskCreate(BaseModel):
    name: str
    source_path: str
    library_path: str
    cron_expr: str = "0 */6 * * *"
    task_type: TaskType = TaskType.SCRAPE_INCREMENTAL
    enabled: bool = True
    use_global_scrape_config: bool = True
    scrape_options: ScrapeOptions | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class TaskUpdate(BaseModel):
    name: str | None = None
    source_path: str | None = None
    library_path: str | None = None
    cron_expr: str | None = None
    task_type: TaskType | None = None
    enabled: bool | None = None
    use_global_scrape_config: bool | None = None
    scrape_options: ScrapeOptions | None = None
    config: dict[str, Any] | None = None


class TaskResponse(BaseModel):
    id: str
    name: str
    source_path: str
    library_path: str
    cron_expr: str
    task_type: TaskType
    enabled: bool
    use_global_scrape_config: bool
    scrape_options: dict[str, bool] | None
    config: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MediaItemSummary(BaseModel):
    id: str
    media_type: str
    title: str
    year: int | None
    poster_path: str | None
    backdrop_path: str | None = None
    overview: str | None = None
    genres: list[str] = Field(default_factory=list)
    scrape_status: str
    match_status: str
    tmdb_id: int | None

    model_config = {"from_attributes": True}


class MediaListResponse(BaseModel):
    items: list[MediaItemSummary]
    total: int
    page: int
    page_size: int


class ManualMatchRequest(BaseModel):
    tmdb_id: int
    tmdb_type: str
    season: int | None = None
    episode: int | None = None
    note: str | None = None
    scrape_immediately: bool = True
    scrape_options: ScrapeOptions | None = None


class TmdbSearchResult(BaseModel):
    tmdb_id: int
    media_type: str
    title: str
    original_title: str | None
    year: int | None
    overview: str | None
    poster_path: str | None
    vote_average: float | None


class ScrapeFieldStatusItem(BaseModel):
    field_key: str
    status: str
    error_message: str | None

    model_config = {"from_attributes": True}


class SourceFileItem(BaseModel):
    id: str
    source_path: str
    library_path: str | None
    link_type: str | None
    file_status: str
    parsed_title: str | None
    parsed_season: int | None
    parsed_episode: int | None
    error_message: str | None
    is_strm: bool = False
    strm_target: str | None = None
    episode_title: str | None = None
    has_nfo: bool = False
    has_thumb: bool = False

    model_config = {"from_attributes": True}


class EpisodeDetailResponse(BaseModel):
    source_file_id: str
    season_number: int
    episode_number: int
    title: str | None
    overview: str | None
    air_date: str | None
    has_nfo: bool
    has_thumb: bool
    thumb_url: str | None = None
    source_path: str
    library_path: str | None
    file_status: str
    is_strm: bool = False
    strm_target: str | None = None


class EpisodeItem(BaseModel):
    id: str
    episode_number: int
    name: str | None
    overview: str | None
    still_path: str | None
    air_date: str | None

    model_config = {"from_attributes": True}


class SeasonItem(BaseModel):
    id: str
    season_number: int
    name: str | None
    poster_path: str | None
    episodes: list[EpisodeItem] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class MediaDetailResponse(BaseModel):
    id: str
    media_type: str
    title: str
    original_title: str | None
    year: int | None
    overview: str | None
    poster_path: str | None
    backdrop_path: str | None
    logo_path: str | None
    tmdb_id: int | None
    scrape_status: str
    match_status: str
    match_confidence: float | None
    metadata_json: dict[str, Any]
    scrape_fields: list[ScrapeFieldStatusItem]
    source_files: list[SourceFileItem]
    last_scraped_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MatchContextResponse(BaseModel):
    media_id: str
    title: str
    year: int | None
    media_type: str
    scrape_status: str
    match_confidence: float | None
    source_files: list[SourceFileItem]
    suggested_query: str
    failure_reason: str | None


class LibraryCleanupResponse(BaseModel):
    removed: int
    skipped: int
    errors: int


class MediaResetResponse(BaseModel):
    library_folders_removed: int
    media_deleted: bool
    removed_paths: list[str] = Field(default_factory=list)
    related_media_reset: int = 1


class OrganizeResponse(BaseModel):
    linked: int
    failed: int
    skipped: int


class DashboardStats(BaseModel):
    total_media: int
    complete: int
    partial: int
    pending: int
    failed: int
    needs_manual_match: int
    total_files: int
    linked_files: int
    total_tasks: int
    enabled_tasks: int


class TaskRunResponse(BaseModel):
    id: str
    task_id: str
    status: str
    message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
