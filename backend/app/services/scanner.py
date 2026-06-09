from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import (
    FileStatus,
    MatchStatus,
    MediaItem,
    MediaType,
    ScrapeStatus,
    SourceFile,
)
from app.services.parser import is_media_file, parse_filename
from app.services.series_identity import (
    build_tv_identity,
    cleanup_orphan_movie_media,
    cleanup_orphan_tv_media,
    consolidate_by_series_scope,
    consolidate_movie_media_by_tmdb,
    consolidate_tv_media_by_identity,
    consolidate_tv_media_by_tmdb,
    find_matching_movie_media,
    find_matching_tv_media,
    resolve_tv_season,
)

logger = logging.getLogger(__name__)


def _get_or_create_media_item(
    db: Session,
    *,
    title: str,
    parsed,
) -> MediaItem | None:
    if not title:
        return None

    media_type = MediaType.TV if parsed.media_type == "tv" else MediaType.MOVIE
    if parsed.media_type == "unknown":
        return None

    if media_type == MediaType.MOVIE:
        existing = find_matching_movie_media(db, title, parsed.year)
        if existing:
            return existing

    query = db.query(MediaItem).filter(MediaItem.media_type == media_type)
    if media_type == MediaType.MOVIE and parsed.year:
        query = query.filter(
            MediaItem.title == title,
            MediaItem.year == parsed.year,
        )
    else:
        query = query.filter(MediaItem.title == title)

    media = query.first()
    if media:
        return media

    media = MediaItem(
        media_type=media_type,
        title=title,
        year=parsed.year if media_type == MediaType.MOVIE else None,
        scrape_status=ScrapeStatus.PENDING,
        match_status=MatchStatus.UNMATCHED,
    )
    db.add(media)
    db.flush()
    return media


def _heal_orphan_source_file(db: Session, source_file: SourceFile) -> None:
    """重置媒体后 source_files 可能仍指向已删 MediaItem，需清掉再重新关联。"""
    if not source_file.media_item_id:
        return
    if db.get(MediaItem, source_file.media_item_id) is None:
        source_file.media_item_id = None
        source_file.library_path = None
        source_file.link_type = None
        source_file.file_status = FileStatus.DISCOVERED
        source_file.error_message = None


def _resolve_tv_media(
    db: Session,
    full_path: Path,
    source_root: Path,
    parsed,
) -> tuple[MediaItem | None, int | None]:
    identity = build_tv_identity(full_path, source_root, parsed)
    if not identity:
        return None, parsed.season

    media = find_matching_tv_media(
        db,
        identity,
        full_path=full_path,
        source_root=source_root,
    )
    if not media:
        media = _get_or_create_media_item(db, title=identity.primary_title, parsed=parsed)

    return media, resolve_tv_season(parsed, identity)


def scan_directory(db: Session, source_root: str) -> dict[str, int | bool | str]:
    root = Path(source_root)
    stats: dict[str, int | bool | str] = {
        "discovered": 0,
        "updated": 0,
        "skipped": 0,
        "errors": 0,
        "path_missing": False,
        "identity_merged": 0,
        "scope_consensus": 0,
    }

    if not root.exists():
        logger.warning("Source path does not exist: %s", source_root)
        stats["path_missing"] = True
        stats["path"] = source_root
        return stats

    for dirpath, _, filenames in os.walk(root):
        for filename in filenames:
            full_path = Path(dirpath) / filename
            if not is_media_file(full_path):
                continue

            try:
                stat = full_path.stat()
                mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
                parsed = parse_filename(full_path)
                rel_path = str(full_path.resolve())

                existing = (
                    db.query(SourceFile).filter(SourceFile.source_path == rel_path).first()
                )

                resolved_season = parsed.season
                media: MediaItem | None = None

                if existing and existing.media_item_id:
                    linked = db.get(MediaItem, existing.media_item_id)
                    if linked:
                        media = linked

                if parsed.media_type == "tv":
                    media, resolved_season = _resolve_tv_media(db, full_path, root, parsed)
                elif parsed.title:
                    if not media or media.media_type != MediaType.MOVIE:
                        media = find_matching_movie_media(db, parsed.title, parsed.year)
                    if not media:
                        media = _get_or_create_media_item(db, title=parsed.title, parsed=parsed)

                if existing:
                    _heal_orphan_source_file(db, existing)
                    changed = (
                        existing.file_size != stat.st_size
                        or existing.file_mtime != mtime
                    )
                    existing.parsed_title = parsed.title
                    existing.parsed_year = parsed.year
                    existing.parsed_season = resolved_season
                    existing.parsed_episode = parsed.episode
                    existing.file_size = stat.st_size
                    existing.file_mtime = mtime
                    if changed:
                        stats["updated"] += 1
                    else:
                        stats["skipped"] += 1
                    source_file = existing
                else:
                    source_file = SourceFile(
                        source_path=rel_path,
                        parsed_title=parsed.title,
                        parsed_year=parsed.year,
                        parsed_season=resolved_season,
                        parsed_episode=parsed.episode,
                        file_size=stat.st_size,
                        file_mtime=mtime,
                        file_status=FileStatus.DISCOVERED,
                    )
                    db.add(source_file)
                    stats["discovered"] += 1

                if media and source_file.media_item_id != media.id:
                    source_file.media_item_id = media.id
                elif not media and source_file.media_item_id:
                    source_file.media_item_id = None

            except OSError as exc:
                logger.exception("Failed to scan %s", full_path)
                stats["errors"] += 1
                db.add(
                    SourceFile(
                        source_path=str(full_path.resolve()),
                        file_status=FileStatus.ERROR,
                        error_message=str(exc),
                    )
                )

    scope_stats = consolidate_by_series_scope(db, source_root)
    stats["scope_consensus"] = scope_stats.get("reassigned", 0)

    identity_stats = consolidate_tv_media_by_identity(db)
    stats["identity_merged"] = identity_stats.get("merged", 0)

    tmdb_stats = consolidate_tv_media_by_tmdb(db)
    stats["tmdb_merged"] = tmdb_stats.get("merged", 0)

    movie_tmdb_stats = consolidate_movie_media_by_tmdb(db)
    stats["movie_tmdb_merged"] = movie_tmdb_stats.get("merged", 0)

    db.flush()
    orphan_stats = cleanup_orphan_tv_media(db)
    stats["orphans_removed"] = orphan_stats.get("removed", 0)

    movie_orphan_stats = cleanup_orphan_movie_media(db)
    stats["movie_orphans_removed"] = movie_orphan_stats.get("removed", 0)

    db.commit()
    return stats
