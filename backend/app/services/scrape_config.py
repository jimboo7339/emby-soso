from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import DEFAULT_SCRAPE_OPTIONS, MediaItem, MediaType, SystemSetting
from app.schemas import ScrapeConfig, ScrapeOptions


SCRAPE_CONFIG_KEY = "scrape_config"

# 仅剧集刮削；电影无季/集概念，不参与状态汇总
TV_ONLY_SCRAPE_FIELDS = frozenset({"season_poster", "episode_still", "episode_overview"})


def get_global_scrape_config(db: Session) -> ScrapeConfig:
    row = db.query(SystemSetting).filter(SystemSetting.key == SCRAPE_CONFIG_KEY).first()
    if not row or not row.value:
        return ScrapeConfig()
    return ScrapeConfig.model_validate(row.value)


def save_global_scrape_config(db: Session, config: ScrapeConfig) -> ScrapeConfig:
    row = db.query(SystemSetting).filter(SystemSetting.key == SCRAPE_CONFIG_KEY).first()
    payload = config.model_dump()
    if row:
        row.value = payload
    else:
        row = SystemSetting(key=SCRAPE_CONFIG_KEY, value=payload)
        db.add(row)
    db.commit()
    return config


def resolve_scrape_options(
    db: Session,
    *,
    task_options: dict[str, bool] | None = None,
    use_global: bool = True,
    override: ScrapeOptions | None = None,
) -> dict[str, bool]:
    if override:
        return override.model_dump()

    base = DEFAULT_SCRAPE_OPTIONS.copy()
    if use_global:
        global_config = get_global_scrape_config(db)
        base.update(global_config.scrape_options.model_dump())

    if task_options:
        base.update(task_options)

    return base


def apply_media_scrape_scope(enabled: dict[str, bool], media: MediaItem) -> dict[str, bool]:
    """电影跳过季/集专属刮削项，避免误报「部分完成」。"""
    scoped = enabled.copy()
    if media.media_type == MediaType.MOVIE:
        for key in TV_ONLY_SCRAPE_FIELDS:
            scoped[key] = False
    return scoped
