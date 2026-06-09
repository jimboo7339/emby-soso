from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.database import Base


def _uuid_str() -> str:
    return str(uuid.uuid4())


class MediaType(str, enum.Enum):
    MOVIE = "movie"
    TV = "tv"


class ScrapeStatus(str, enum.Enum):
    PENDING = "pending"
    PARTIAL = "partial"
    COMPLETE = "complete"
    FAILED = "failed"
    NEEDS_MANUAL_MATCH = "needs_manual_match"


class MatchStatus(str, enum.Enum):
    AUTO = "auto"
    MANUAL = "manual"
    UNMATCHED = "unmatched"


class FieldScrapeStatus(str, enum.Enum):
    PENDING = "pending"
    OK = "ok"
    MISSING = "missing"
    FAILED = "failed"
    SKIPPED = "skipped"


class LinkType(str, enum.Enum):
    HARDLINK = "hardlink"
    SYMLINK = "symlink"


class FileStatus(str, enum.Enum):
    DISCOVERED = "discovered"
    LINKED = "linked"
    ERROR = "error"


class TaskType(str, enum.Enum):
    SCAN_ONLY = "scan_only"
    ORGANIZE_ONLY = "organize_only"
    SCRAPE_INCREMENTAL = "scrape_incremental"
    SCRAPE_FULL = "scrape_full"


class TaskRunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


DEFAULT_SCRAPE_OPTIONS: dict[str, bool] = {
    "basic": True,
    "overview": True,
    "poster": True,
    "backdrop": True,
    "logo": True,
    "cast": True,
    "crew": True,
    "genres": True,
    "keywords": True,
    "trailers": True,
    "external_ids": True,
    "season_poster": True,
    "episode_still": True,
    "episode_overview": True,
}


class SystemSetting(Base):
    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    name: Mapped[str] = mapped_column(String(255))
    source_path: Mapped[str] = mapped_column(String(1024))
    library_path: Mapped[str] = mapped_column(String(1024))
    cron_expr: Mapped[str] = mapped_column(String(64), default="0 */6 * * *")
    task_type: Mapped[TaskType] = mapped_column(
        Enum(TaskType, native_enum=False, length=32),
        default=TaskType.SCRAPE_INCREMENTAL,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    use_global_scrape_config: Mapped[bool] = mapped_column(Boolean, default=True)
    scrape_options: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    runs: Mapped[list[TaskRun]] = relationship(back_populates="task")


class TaskRun(Base):
    __tablename__ = "task_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), index=True)
    status: Mapped[TaskRunStatus] = mapped_column(
        Enum(TaskRunStatus, native_enum=False, length=16),
        default=TaskRunStatus.PENDING,
    )
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    task: Mapped[Task] = relationship(back_populates="runs")


class MediaItem(Base):
    __tablename__ = "media_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    media_type: Mapped[MediaType] = mapped_column(
        Enum(MediaType, native_enum=False, length=16), index=True
    )
    tmdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(512), default="")
    original_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overview: Mapped[str | None] = mapped_column(Text, nullable=True)
    poster_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    backdrop_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    logo_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    scrape_status: Mapped[ScrapeStatus] = mapped_column(
        Enum(ScrapeStatus, native_enum=False, length=32),
        default=ScrapeStatus.PENDING,
        index=True,
    )
    match_status: Mapped[MatchStatus] = mapped_column(
        Enum(MatchStatus, native_enum=False, length=16),
        default=MatchStatus.UNMATCHED,
    )
    match_confidence: Mapped[float | None] = mapped_column(nullable=True)
    last_scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    manual_matched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    scrape_fields: Mapped[list[ScrapeFieldStatus]] = relationship(
        back_populates="media_item", cascade="all, delete-orphan"
    )
    source_files: Mapped[list[SourceFile]] = relationship(
        back_populates="media_item", cascade="all, delete-orphan"
    )
    seasons: Mapped[list[Season]] = relationship(
        back_populates="media_item", cascade="all, delete-orphan"
    )


class ScrapeFieldStatus(Base):
    __tablename__ = "scrape_field_statuses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    media_item_id: Mapped[str] = mapped_column(
        ForeignKey("media_items.id"), index=True
    )
    field_key: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[FieldScrapeStatus] = mapped_column(
        Enum(FieldScrapeStatus, native_enum=False, length=16),
        default=FieldScrapeStatus.PENDING,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    media_item: Mapped[MediaItem] = relationship(back_populates="scrape_fields")


class SourceFile(Base):
    __tablename__ = "source_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    media_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("media_items.id"), nullable=True, index=True
    )
    source_path: Mapped[str] = mapped_column(String(2048), unique=True)
    library_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    link_type: Mapped[LinkType | None] = mapped_column(
        Enum(LinkType, native_enum=False, length=16), nullable=True
    )
    file_status: Mapped[FileStatus] = mapped_column(
        Enum(FileStatus, native_enum=False, length=16),
        default=FileStatus.DISCOVERED,
    )
    parsed_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    parsed_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parsed_season: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parsed_episode: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_mtime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    media_item: Mapped[MediaItem | None] = relationship(back_populates="source_files")


class Season(Base):
    __tablename__ = "seasons"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    media_item_id: Mapped[str] = mapped_column(
        ForeignKey("media_items.id"), index=True
    )
    season_number: Mapped[int] = mapped_column(Integer)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    overview: Mapped[str | None] = mapped_column(Text, nullable=True)
    poster_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    tmdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    media_item: Mapped[MediaItem] = relationship(back_populates="seasons")
    episodes: Mapped[list[Episode]] = relationship(
        back_populates="season", cascade="all, delete-orphan"
    )


class Episode(Base):
    __tablename__ = "episodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    season_id: Mapped[str] = mapped_column(ForeignKey("seasons.id"), index=True)
    episode_number: Mapped[int] = mapped_column(Integer)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    overview: Mapped[str | None] = mapped_column(Text, nullable=True)
    still_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    tmdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    air_date: Mapped[str | None] = mapped_column(String(32), nullable=True)

    season: Mapped[Season] = relationship(back_populates="episodes")


class MatchHistory(Base):
    __tablename__ = "match_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    media_item_id: Mapped[str] = mapped_column(
        ForeignKey("media_items.id"), index=True
    )
    tmdb_id: Mapped[int] = mapped_column(Integer)
    tmdb_type: Mapped[str] = mapped_column(String(16))
    action: Mapped[str] = mapped_column(String(32))
    operator: Mapped[str | None] = mapped_column(String(128), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CacheEntry(Base):
    __tablename__ = "cache_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cache_key: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    cache_value: Mapped[dict] = mapped_column(JSON, default=dict)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
