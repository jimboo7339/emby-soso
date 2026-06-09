from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.datetime_utils import ensure_utc, utc_now
from pathlib import Path
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.models import (
    DEFAULT_SCRAPE_OPTIONS,
    FieldScrapeStatus,
    MediaItem,
    MediaType,
    ScrapeFieldStatus,
    ScrapeStatus,
    SourceFile,
)
from app.services.library_paths import (
    iter_library_files,
    resolve_library_root_for_media,
    resolve_movie_folder,
    resolve_show_folder,
)
from app.services.nfo_writer import (
    ImageJob,
    _should_write,
    collect_episode_still_job,
    download_images_parallel,
    episode_thumb_path,
    tmdb_image_url,
    write_episode_nfo_only,
    write_movie_artwork,
    write_movie_nfo_file,
    write_season_nfo_file,
    write_show_artwork,
    write_tvshow_nfo_file,
)
from app.services.scrape_config import apply_media_scrape_scope, TV_ONLY_SCRAPE_FIELDS
from app.services.tmdb_client import TmdbClientSync
from app.services.tmdb_images import pick_image
from app.services.tmdb_settings import get_tmdb_config, normalize_scrape_concurrency

logger = logging.getLogger(__name__)

SCRAPE_FIELD_KEYS = list(DEFAULT_SCRAPE_OPTIONS.keys())


def _set_field_status(
    db: Session,
    media: MediaItem,
    field_key: str,
    status: FieldScrapeStatus,
    error: str | None = None,
) -> None:
    row = (
        db.query(ScrapeFieldStatus)
        .filter(
            ScrapeFieldStatus.media_item_id == media.id,
            ScrapeFieldStatus.field_key == field_key,
        )
        .first()
    )
    if not row:
        row = ScrapeFieldStatus(media_item_id=media.id, field_key=field_key)
        db.add(row)
    row.status = status
    row.error_message = error
    row.updated_at = utc_now()


def _field_updated_ts(row: ScrapeFieldStatus) -> datetime:
    return ensure_utc(row.updated_at) or datetime.min.replace(tzinfo=timezone.utc)


def _skip_tv_only_fields_for_movie(db: Session, media: MediaItem) -> None:
    if media.media_type != MediaType.MOVIE:
        return
    for key in TV_ONLY_SCRAPE_FIELDS:
        _set_field_status(db, media, key, FieldScrapeStatus.SKIPPED)


def _init_field_statuses(
    db: Session, media: MediaItem, enabled: dict[str, bool]
) -> None:
    for key in SCRAPE_FIELD_KEYS:
        if not enabled.get(key, False):
            _set_field_status(db, media, key, FieldScrapeStatus.SKIPPED)
        else:
            existing = (
                db.query(ScrapeFieldStatus)
                .filter(
                    ScrapeFieldStatus.media_item_id == media.id,
                    ScrapeFieldStatus.field_key == key,
                )
                .first()
            )
            if not existing:
                _set_field_status(db, media, key, FieldScrapeStatus.PENDING)
            elif existing.status == FieldScrapeStatus.SKIPPED and enabled.get(key):
                _set_field_status(db, media, key, FieldScrapeStatus.PENDING)


def _dedupe_field_rows(rows: list[ScrapeFieldStatus]) -> list[ScrapeFieldStatus]:
    latest: dict[str, ScrapeFieldStatus] = {}
    for row in rows:
        existing = latest.get(row.field_key)
        if not existing or _field_updated_ts(row) >= _field_updated_ts(existing):
            latest[row.field_key] = row
    return list(latest.values())


def _cleanup_duplicate_field_statuses(db: Session, media: MediaItem) -> None:
    rows = (
        db.query(ScrapeFieldStatus)
        .filter(ScrapeFieldStatus.media_item_id == media.id)
        .order_by(ScrapeFieldStatus.updated_at.desc())
        .all()
    )
    seen: set[str] = set()
    for row in rows:
        if row.field_key in seen:
            db.delete(row)
        else:
            seen.add(row.field_key)


def _aggregate_status(db: Session, media: MediaItem) -> ScrapeStatus:
    rows = (
        db.query(ScrapeFieldStatus)
        .filter(ScrapeFieldStatus.media_item_id == media.id)
        .all()
    )
    if not rows:
        return ScrapeStatus.PENDING

    active = [r for r in _dedupe_field_rows(rows) if r.status != FieldScrapeStatus.SKIPPED]
    if media.media_type == MediaType.MOVIE:
        active = [r for r in active if r.field_key not in TV_ONLY_SCRAPE_FIELDS]
    if not active:
        return ScrapeStatus.PENDING

    resolved = {FieldScrapeStatus.OK, FieldScrapeStatus.MISSING}
    unresolved = {FieldScrapeStatus.PENDING, FieldScrapeStatus.FAILED}

    if all(r.status in resolved for r in active):
        return ScrapeStatus.COMPLETE
    if any(r.status == FieldScrapeStatus.FAILED for r in active):
        if any(r.status in resolved for r in active):
            return ScrapeStatus.PARTIAL
        return ScrapeStatus.FAILED
    if any(r.status in resolved for r in active) and any(
        r.status in unresolved for r in active
    ):
        return ScrapeStatus.PARTIAL
    if any(r.status in resolved for r in active):
        return ScrapeStatus.PARTIAL
    return ScrapeStatus.PENDING


def scrape_media_item(
    db: Session,
    media: MediaItem,
    *,
    enabled_fields: dict[str, bool] | None = None,
    force: bool = False,
    client: TmdbClientSync | None = None,
    library_root: str | None = None,
    scrape_concurrency: int | None = None,
) -> MediaItem:
    if not media.tmdb_id:
        media.scrape_status = ScrapeStatus.NEEDS_MANUAL_MATCH
        db.commit()
        return media

    enabled = apply_media_scrape_scope(enabled_fields or DEFAULT_SCRAPE_OPTIONS.copy(), media)
    _cleanup_duplicate_field_statuses(db, media)
    _skip_tv_only_fields_for_movie(db, media)
    _init_field_statuses(db, media, enabled)

    if force:
        for key, on in enabled.items():
            if on:
                _set_field_status(db, media, key, FieldScrapeStatus.PENDING)

    client = client or TmdbClientSync.from_db(db)
    concurrency = normalize_scrape_concurrency(
        scrape_concurrency if scrape_concurrency is not None else get_tmdb_config(db).scrape_concurrency
    )
    media_type = "movie" if media.media_type == MediaType.MOVIE else "tv"

    try:
        details = client.get_details(media_type, media.tmdb_id)
    except Exception as exc:
        logger.exception("Failed to fetch TMDB details for %s", media.id)
        for key, on in enabled.items():
            if on:
                _set_field_status(db, media, key, FieldScrapeStatus.FAILED, str(exc))
        media.scrape_status = ScrapeStatus.FAILED
        db.commit()
        return media

    images = details.get("images") or {}

    def should_scrape(key: str) -> bool:
        if not enabled.get(key):
            return False
        row = (
            db.query(ScrapeFieldStatus)
            .filter(
                ScrapeFieldStatus.media_item_id == media.id,
                ScrapeFieldStatus.field_key == key,
            )
            .first()
        )
        if not row:
            return True
        if force:
            return True
        return row.status in {
            FieldScrapeStatus.PENDING,
            FieldScrapeStatus.FAILED,
            FieldScrapeStatus.MISSING,
        }

    if should_scrape("basic"):
        title = details.get("title") or details.get("name")
        if title:
            media.title = title
            media.original_title = details.get("original_title") or details.get(
                "original_name"
            )
            date = details.get("release_date") or details.get("first_air_date") or ""
            if len(date) >= 4 and date[:4].isdigit():
                media.year = int(date[:4])
            _set_field_status(db, media, "basic", FieldScrapeStatus.OK)
        else:
            _set_field_status(db, media, "basic", FieldScrapeStatus.MISSING)

    if should_scrape("overview"):
        overview = details.get("overview")
        if overview:
            media.overview = overview
            _set_field_status(db, media, "overview", FieldScrapeStatus.OK)
        else:
            _set_field_status(db, media, "overview", FieldScrapeStatus.MISSING)

    if should_scrape("poster"):
        path = details.get("poster_path") or pick_image(images, "posters", client.language)
        if path:
            media.poster_path = path
            _set_field_status(db, media, "poster", FieldScrapeStatus.OK)
        else:
            _set_field_status(db, media, "poster", FieldScrapeStatus.MISSING)

    if should_scrape("backdrop"):
        path = details.get("backdrop_path") or pick_image(
            images, "backdrops", client.language
        )
        if path:
            media.backdrop_path = path
            _set_field_status(db, media, "backdrop", FieldScrapeStatus.OK)
        else:
            _set_field_status(db, media, "backdrop", FieldScrapeStatus.MISSING)

    if should_scrape("logo"):
        path = pick_image(images, "logos", client.language)
        if path:
            media.logo_path = path
            _set_field_status(db, media, "logo", FieldScrapeStatus.OK)
        else:
            _set_field_status(db, media, "logo", FieldScrapeStatus.MISSING)

    nfo_keys = {"cast", "crew", "genres", "keywords", "trailers", "external_ids"}
    for key in nfo_keys:
        if not should_scrape(key):
            continue
        value = None
        if key == "cast":
            value = (details.get("credits") or {}).get("cast")
        elif key == "crew":
            value = (details.get("credits") or {}).get("crew")
        elif key == "genres":
            value = details.get("genres")
        elif key == "keywords":
            kw = details.get("keywords") or {}
            value = kw.get("keywords") or kw.get("results")
        elif key == "trailers":
            videos = (details.get("videos") or {}).get("results") or []
            value = [v for v in videos if v.get("site") == "YouTube"]
        elif key == "external_ids":
            value = details.get("external_ids")

        if value:
            _set_field_status(db, media, key, FieldScrapeStatus.OK)
        else:
            _set_field_status(db, media, key, FieldScrapeStatus.MISSING)

    if not library_root:
        library_root = resolve_library_root_for_media(db, media)

    library_pairs = iter_library_files(media, library_root)

    if library_pairs:
        if media.media_type == MediaType.TV:
            _write_tv_library_metadata(
                db,
                media,
                client,
                details,
                images,
                enabled,
                should_scrape,
                force,
                library_root,
                library_pairs,
                scrape_concurrency=concurrency,
            )
        else:
            _write_movie_library_metadata(
                db,
                media,
                details,
                images,
                client.language,
                enabled,
                should_scrape,
                force,
                library_pairs,
                client=client,
                scrape_concurrency=concurrency,
            )
    else:
        if media.media_type == MediaType.TV:
            for key in TV_ONLY_SCRAPE_FIELDS:
                if enabled.get(key) and should_scrape(key):
                    _set_field_status(
                        db,
                        media,
                        key,
                        FieldScrapeStatus.PENDING,
                        "尚未整理到影视库，请先运行整理任务",
                    )

    media.last_scraped_at = utc_now()
    media.scrape_status = _aggregate_status(db, media)
    db.commit()
    db.refresh(media)
    return media


def deduped_scrape_fields(media: MediaItem) -> list[ScrapeFieldStatus]:
    return _dedupe_field_rows(list(media.scrape_fields))


def refresh_media_scrape_status(
    db: Session, media: MediaItem, *, persist: bool = True
) -> ScrapeStatus:
    """清理重复字段记录并重新计算整体刮削状态。"""
    _cleanup_duplicate_field_statuses(db, media)
    _skip_tv_only_fields_for_movie(db, media)
    db.flush()
    status = _aggregate_status(db, media)
    if persist and media.scrape_status != status:
        media.scrape_status = status
        db.commit()
        db.refresh(media)
    return status


def refresh_media_scrape_status_batch(db: Session, items: list[MediaItem]) -> None:
    """列表页批量刷新刮削状态，避免逐条 commit。"""
    if not items:
        return
    changed = False
    for media in items:
        _cleanup_duplicate_field_statuses(db, media)
        _skip_tv_only_fields_for_movie(db, media)
    db.flush()
    for media in items:
        status = _aggregate_status(db, media)
        if media.scrape_status != status:
            media.scrape_status = status
            changed = True
    if changed:
        db.commit()
        for media in items:
            db.refresh(media)


def _write_movie_library_metadata(
    db: Session,
    media: MediaItem,
    details: dict[str, Any],
    images: dict[str, Any],
    language: str,
    enabled: dict[str, bool],
    should_scrape: Callable[[str], bool],
    force: bool,
    library_pairs: list[tuple[SourceFile, Path]],
    client: TmdbClientSync | None = None,
    scrape_concurrency: int = 8,
) -> None:
    _, library_file = library_pairs[0]
    folder = resolve_movie_folder(library_file)
    library_file_str = str(library_file)
    nfo_enabled = any(
        enabled.get(k) and should_scrape(k)
        for k in ("basic", "overview", "cast", "crew", "genres", "external_ids")
    )
    if nfo_enabled:
        try:
            ok = write_movie_nfo_file(
                folder, library_file_str, details, media.tmdb_id, force=force
            )
            status = FieldScrapeStatus.OK if ok else FieldScrapeStatus.FAILED
            for key in ("basic", "overview", "cast", "crew", "genres", "external_ids"):
                if enabled.get(key) and should_scrape(key):
                    _set_field_status(db, media, key, status)
        except OSError as exc:
            for key in ("basic", "overview", "cast", "crew", "genres", "external_ids"):
                if enabled.get(key):
                    _set_field_status(db, media, key, FieldScrapeStatus.FAILED, str(exc))

    artwork_enabled = {
        k: enabled.get(k, False) and should_scrape(k)
        for k in ("poster", "backdrop", "logo")
    }
    if any(artwork_enabled.values()):
        try:
            results = write_movie_artwork(
                folder,
                details,
                images,
                language=language,
                force=force,
                enabled=artwork_enabled,
                http_client=client.http_client if client else None,
                max_workers=scrape_concurrency,
            )
            for key in ("poster", "backdrop", "logo"):
                if artwork_enabled.get(key):
                    _set_field_status(
                        db,
                        media,
                        key,
                        FieldScrapeStatus.OK if results.get(key) else FieldScrapeStatus.MISSING,
                    )
        except OSError as exc:
            for key in ("poster", "backdrop", "logo"):
                if artwork_enabled.get(key):
                    _set_field_status(db, media, key, FieldScrapeStatus.FAILED, str(exc))


@dataclass
class EpisodeScrapeResult:
    nfo_ok: bool | None = None
    still_job: ImageJob | None = None
    still_exists: bool | None = None
    still_missing: bool = False
    failed: bool = False


def _scrape_single_episode(
    client: TmdbClientSync,
    *,
    tmdb_id: int,
    season_num: int,
    ep_num: int,
    library_path: str,
    ep_data: dict[str, Any] | None,
    write_nfo: bool,
    write_still: bool,
    force: bool,
) -> EpisodeScrapeResult:
    """单集刮削（线程内执行，不写数据库）。"""
    result = EpisodeScrapeResult()
    data = ep_data

    if data is None and (write_nfo or write_still):
        try:
            data = client.get_episode(tmdb_id, season_num, ep_num)
        except Exception as exc:
            logger.warning(
                "Episode metadata failed S%02dE%02d: %s", season_num, ep_num, exc
            )
            result.failed = True
            return result

    if write_nfo:
        if data:
            result.nfo_ok = write_episode_nfo_only(
                library_path, data, season_num, ep_num, force=force
            )
        else:
            result.nfo_ok = False

    if write_still:
        if data:
            job = collect_episode_still_job(library_path, data, force=force)
            if job:
                result.still_job = job
            else:
                thumb_path = episode_thumb_path(library_path)
                if _should_write(thumb_path, force):
                    result.still_missing = True
                else:
                    result.still_exists = thumb_path.exists()
        else:
            result.still_missing = True

    return result


def _fetch_season_data(
    client: TmdbClientSync,
    tmdb_id: int,
    season_num: int,
) -> tuple[int, dict[str, Any] | None]:
    try:
        return season_num, client.get_season(tmdb_id, season_num)
    except Exception as exc:
        logger.warning("Failed to fetch season %s for tmdb=%s: %s", season_num, tmdb_id, exc)
        return season_num, None


def _collect_season_poster_job(
    season_folder: Path,
    poster_path: str | None,
    season_number: int,
    *,
    force: bool,
) -> ImageJob | None:
    dest = season_folder / f"season{season_number:02d}-poster.jpg"
    if not _should_write(dest, force):
        return None
    url = tmdb_image_url(poster_path, "w500")
    if not url:
        return None
    return url, dest


def _media_in_task_scope(media: MediaItem, source_root: str | None) -> bool:
    if not source_root:
        return True
    prefix = str(Path(source_root).resolve())
    if not prefix.endswith(os.sep):
        prefix += os.sep
    prefix_lower = prefix.lower()
    for sf in media.source_files:
        if not sf.source_path:
            continue
        try:
            resolved = str(Path(sf.source_path).resolve()).lower()
        except OSError:
            resolved = sf.source_path.lower()
        if resolved.startswith(prefix_lower):
            return True
    return False


def _write_tv_library_metadata(
    db: Session,
    media: MediaItem,
    client: TmdbClientSync,
    details: dict[str, Any],
    images: dict[str, Any],
    enabled: dict[str, bool],
    should_scrape: Callable[[str], bool],
    force: bool,
    library_root: str,
    library_pairs: list[tuple[SourceFile, Path]],
    *,
    scrape_concurrency: int,
) -> None:
    show_folder = resolve_show_folder(media, library_root)
    if not show_folder:
        return

    http_client = client.http_client

    nfo_enabled = any(
        enabled.get(k) and should_scrape(k)
        for k in ("basic", "overview", "cast", "crew", "genres", "external_ids")
    )
    if nfo_enabled:
        try:
            ok = write_tvshow_nfo_file(show_folder, details, media.tmdb_id, force=force)
            status = FieldScrapeStatus.OK if ok else FieldScrapeStatus.FAILED
            for key in ("basic", "overview", "cast", "crew", "genres", "external_ids"):
                if enabled.get(key) and should_scrape(key):
                    _set_field_status(db, media, key, status)
        except OSError as exc:
            for key in ("basic", "overview", "cast", "crew", "genres", "external_ids"):
                if enabled.get(key):
                    _set_field_status(db, media, key, FieldScrapeStatus.FAILED, str(exc))

    artwork_enabled = {
        k: enabled.get(k, False) and should_scrape(k)
        for k in ("poster", "backdrop", "logo")
    }
    if any(artwork_enabled.values()):
        try:
            results = write_show_artwork(
                show_folder,
                details,
                images,
                language=client.language,
                force=force,
                enabled=artwork_enabled,
                http_client=http_client,
                max_workers=scrape_concurrency,
            )
            for key in ("poster", "backdrop", "logo"):
                if artwork_enabled.get(key):
                    _set_field_status(
                        db,
                        media,
                        key,
                        FieldScrapeStatus.OK if results.get(key) else FieldScrapeStatus.MISSING,
                    )
        except OSError as exc:
            for key in ("poster", "backdrop", "logo"):
                if artwork_enabled.get(key):
                    _set_field_status(db, media, key, FieldScrapeStatus.FAILED, str(exc))

    seasons_needed: dict[int, Path] = {}
    for sf, library_file in library_pairs:
        season_num = sf.parsed_season or 1
        seasons_needed[season_num] = library_file.parent

    need_season_api = any(
        (enabled.get("season_poster") and should_scrape("season_poster"))
        or (enabled.get("episode_overview") and should_scrape("episode_overview"))
        or (enabled.get("episode_still") and should_scrape("episode_still"))
        for _ in seasons_needed
    )
    season_data_map: dict[int, dict[str, Any]] = {}
    if need_season_api and seasons_needed:
        season_numbers = sorted(seasons_needed)
        if len(season_numbers) == 1:
            num, data = _fetch_season_data(client, media.tmdb_id, season_numbers[0])
            if data:
                season_data_map[num] = data
        else:
            workers = min(scrape_concurrency, len(season_numbers))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [
                    pool.submit(_fetch_season_data, client, media.tmdb_id, num)
                    for num in season_numbers
                ]
                for future in as_completed(futures):
                    num, data = future.result()
                    if data:
                        season_data_map[num] = data

    image_jobs: list[ImageJob] = []
    season_poster_dests: dict[int, Path] = {}
    still_dests: list[Path] = []

    write_episode_nfo = enabled.get("episode_overview") and should_scrape("episode_overview")
    write_episode_still = enabled.get("episode_still") and should_scrape("episode_still")
    write_season_poster = enabled.get("season_poster") and should_scrape("season_poster")

    episode_nfo_ok = True
    episode_still_ok = True
    episode_nfo_any = False
    episode_still_any = False
    season_poster_ok = True
    season_poster_any = False

    for season_num in sorted(seasons_needed):
        season_folder = seasons_needed[season_num]
        season_data = season_data_map.get(season_num)
        episodes_by_num = client.episodes_by_number(season_data) if season_data else {}

        if write_season_poster and season_data:
            season_poster_any = True
            try:
                write_season_nfo_file(season_folder, season_data, season_num, force=force)
                job = _collect_season_poster_job(
                    season_folder,
                    season_data.get("poster_path"),
                    season_num,
                    force=force,
                )
                if job:
                    image_jobs.append(job)
                    season_poster_dests[season_num] = job[1]
                else:
                    dest = season_folder / f"season{season_num:02d}-poster.jpg"
                    if _should_write(dest, force):
                        season_poster_ok = False
            except Exception as exc:
                season_poster_ok = False
                _set_field_status(
                    db, media, "season_poster", FieldScrapeStatus.FAILED, str(exc)
                )

        season_episodes = [
            (sf, library_file)
            for sf, library_file in library_pairs
            if (sf.parsed_season or 1) == season_num
        ]

        if season_episodes and (write_episode_nfo or write_episode_still):
            workers = min(scrape_concurrency, len(season_episodes))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(
                        _scrape_single_episode,
                        client,
                        tmdb_id=media.tmdb_id,
                        season_num=season_num,
                        ep_num=sf.parsed_episode or 1,
                        library_path=str(library_file),
                        ep_data=episodes_by_num.get(sf.parsed_episode or 1),
                        write_nfo=write_episode_nfo,
                        write_still=write_episode_still,
                        force=force,
                    ): (sf, library_file)
                    for sf, library_file in season_episodes
                }
                for future in as_completed(futures):
                    ep_result = future.result()
                    if write_episode_nfo:
                        episode_nfo_any = True
                        if ep_result.failed or ep_result.nfo_ok is False:
                            episode_nfo_ok = False
                    if write_episode_still:
                        episode_still_any = True
                        if ep_result.failed or ep_result.still_missing:
                            episode_still_ok = False
                        elif ep_result.still_job:
                            image_jobs.append(ep_result.still_job)
                            still_dests.append(ep_result.still_job[1])
                        elif ep_result.still_exists is False:
                            episode_still_ok = False

    if image_jobs:
        download_results = download_images_parallel(
            image_jobs,
            client=http_client,
            max_workers=scrape_concurrency,
        )
        if write_season_poster and season_poster_any:
            for season_num, dest in season_poster_dests.items():
                season_poster_ok = season_poster_ok and download_results.get(dest, False)
            _set_field_status(
                db,
                media,
                "season_poster",
                FieldScrapeStatus.OK if season_poster_ok else FieldScrapeStatus.MISSING,
            )
        if write_episode_still and episode_still_any and still_dests:
            for dest in still_dests:
                episode_still_ok = episode_still_ok and download_results.get(dest, False)

    if episode_nfo_any:
        _set_field_status(
            db,
            media,
            "episode_overview",
            FieldScrapeStatus.OK if episode_nfo_ok else FieldScrapeStatus.MISSING,
        )
    if episode_still_any:
        _set_field_status(
            db,
            media,
            "episode_still",
            FieldScrapeStatus.OK if episode_still_ok else FieldScrapeStatus.MISSING,
        )


def scrape_pending_media(
    db: Session,
    task,
    *,
    force: bool = False,
) -> dict[str, int]:
    enabled = resolve_scrape_options(
        db,
        task_options=task.scrape_options,
        use_global=task.use_global_scrape_config,
    )

    stats = {"scraped": 0, "skipped": 0, "failed": 0, "needs_manual": 0, "out_of_scope": 0}
    query = db.query(MediaItem).filter(MediaItem.tmdb_id.isnot(None))

    if not force:
        query = query.filter(
            MediaItem.scrape_status.in_(
                [
                    ScrapeStatus.PENDING,
                    ScrapeStatus.PARTIAL,
                    ScrapeStatus.FAILED,
                ]
            )
        )

    library_root = task.library_path
    source_root = getattr(task, "source_path", None)
    scrape_concurrency = get_tmdb_config(db).scrape_concurrency
    with TmdbClientSync.from_db(db) as client:
        for media in query.all():
            if not _media_in_task_scope(media, source_root):
                stats["out_of_scope"] += 1
                continue
            before = media.scrape_status
            scrape_media_item(
                db,
                media,
                enabled_fields=enabled,
                force=force,
                client=client,
                library_root=library_root,
                scrape_concurrency=scrape_concurrency,
            )
            db.refresh(media)
            if media.scrape_status == ScrapeStatus.COMPLETE:
                stats["scraped"] += 1
            elif media.scrape_status == ScrapeStatus.NEEDS_MANUAL_MATCH:
                stats["needs_manual"] += 1
            elif media.scrape_status == before and media.scrape_status == ScrapeStatus.COMPLETE:
                stats["skipped"] += 1
            elif media.scrape_status == ScrapeStatus.FAILED:
                stats["failed"] += 1
            else:
                stats["scraped"] += 1

    return stats
