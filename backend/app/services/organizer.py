from __future__ import annotations

import logging
import os
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import FileStatus, LinkType, MediaItem, MediaType, SourceFile
from app.services.path_utils import (
    is_under_root,
    paths_equal,
    safe_unlink_library_entry,
    validate_library_target,
)
from app.services.parser import sanitize_filename

logger = logging.getLogger(__name__)


def _same_filesystem(path_a: Path, path_b: Path) -> bool:
    try:
        return os.stat(path_a).st_dev == os.stat(path_b).st_dev
    except OSError:
        return False


def _choose_link_type(source: Path, target: Path, preferred: str) -> LinkType:
    if preferred == "symlink":
        return LinkType.SYMLINK
    if preferred == "hardlink":
        return LinkType.HARDLINK
    return LinkType.HARDLINK if _same_filesystem(source, target) else LinkType.SYMLINK


def _create_link(source: Path, target: Path, link_type: LinkType) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        if paths_equal(target, source):
            raise ValueError(f"Cannot replace source path with link: {target}")
        safe_unlink_library_entry(target, source, link_type)

    if link_type == LinkType.HARDLINK:
        os.link(source, target)
    else:
        os.symlink(source, target)


def _resolve_tv_year(media: MediaItem, source_file: SourceFile) -> int | None:
    """剧集库目录统一用 TMDB 首播年，不用单集文件名里的年份（避免同剧拆多个库文件夹）。"""
    _ = source_file
    return media.year


def build_tv_series_folder_name(
    title: str, year: int | None, tmdb_id: int | None
) -> str:
    """剧集目录：剧集名(年份) {tmdb_id}"""
    safe_title = sanitize_filename(title)
    if year and tmdb_id:
        return f"{safe_title}({year}) {tmdb_id}"
    if year:
        return f"{safe_title}({year})"
    if tmdb_id:
        return f"{safe_title} {tmdb_id}"
    return safe_title


def build_tv_episode_filename(
    title: str, year: int | None, season: int, episode: int, ext: str
) -> str:
    """单集文件：剧集名(年份) - S01E01 - 第01集.strm"""
    safe_title = sanitize_filename(title)
    label = f"{safe_title}({year})" if year else safe_title
    return f"{label} - S{season:02d}E{episode:02d} - 第{episode:02d}集{ext}"


def build_library_path(
    source_file: SourceFile,
    library_root: str,
    *,
    display_title: str | None = None,
    year: int | None = None,
    media_type: MediaType | None = None,
    tmdb_id: int | None = None,
) -> Path | None:
    source = Path(source_file.source_path)
    title = sanitize_filename(display_title or source_file.parsed_title or source.stem)
    ext = source.suffix
    root = Path(library_root)

    if media_type == MediaType.TV or (
        source_file.parsed_season is not None or source_file.parsed_episode is not None
    ):
        season = source_file.parsed_season or 1
        episode = source_file.parsed_episode or 1
        tv_year = year or source_file.parsed_year
        series_folder = build_tv_series_folder_name(title, tv_year, tmdb_id)
        folder = root / "TV Shows" / series_folder / f"Season {season:02d}"
        filename = build_tv_episode_filename(title, tv_year, season, episode, ext)
        return folder / filename

    movie_year = year or source_file.parsed_year
    folder_name = f"{title} ({movie_year})" if movie_year else title
    folder = root / "Movies" / folder_name
    return folder / f"{folder_name}{ext}"


def _target_path_for_source(
    source_file: SourceFile, library_root: str, media: MediaItem
) -> Path | None:
    return build_library_path(
        source_file,
        library_root,
        display_title=media.title,
        year=_resolve_tv_year(media, source_file) if media.media_type == MediaType.TV else media.year,
        media_type=media.media_type,
        tmdb_id=media.tmdb_id,
    )


def organize_file(
    db: Session,
    source_file: SourceFile,
    library_root: str,
    link_preference: str = "auto",
    *,
    force: bool = False,
) -> bool:
    if not source_file.media_item_id or not source_file.media_item:
        return False

    media = source_file.media_item
    target = _target_path_for_source(source_file, library_root, media)
    if not target:
        source_file.file_status = FileStatus.ERROR
        source_file.error_message = "Cannot determine library path"
        return False

    source = Path(source_file.source_path)
    if not source.exists():
        source_file.file_status = FileStatus.ERROR
        source_file.error_message = "Source file missing"
        return False

    try:
        validate_library_target(target, source, library_root)
    except ValueError as exc:
        source_file.file_status = FileStatus.ERROR
        source_file.error_message = str(exc)
        logger.error("Invalid library target for %s: %s", source, exc)
        return False

    if not force and source_file.library_path:
        current = Path(source_file.library_path)
        if current == target and (current.exists() or current.is_symlink()):
            return True

    try:
        if source_file.library_path:
            old = Path(source_file.library_path)
            if old.exists() or old.is_symlink():
                if is_under_root(old, library_root) and not paths_equal(old, source):
                    try:
                        safe_unlink_library_entry(
                            old, source, source_file.link_type
                        )
                    except PermissionError as exc:
                        logger.warning("Skipped unsafe old link removal: %s", exc)
                    except OSError:
                        logger.warning("Failed to remove old library link: %s", old)
                else:
                    logger.warning(
                        "Skipped old library path outside library or equals source: %s",
                        old,
                    )

        link_type = _choose_link_type(source, target, link_preference)
        _create_link(source, target, link_type)
        source_file.library_path = str(target.absolute())
        source_file.link_type = link_type
        source_file.file_status = FileStatus.LINKED
        source_file.error_message = None
        db.flush()
        return True
    except OSError as exc:
        logger.exception("Link failed: %s -> %s", source, target)
        source_file.file_status = FileStatus.ERROR
        source_file.error_message = str(exc)
        return False


def organize_media_items(
    db: Session,
    library_root: str,
    *,
    link_preference: str = "auto",
    media_item_ids: list[str] | None = None,
    force_reorganize: bool = False,
) -> dict[str, int]:
    stats = {"linked": 0, "failed": 0, "skipped": 0}

    query = db.query(SourceFile).filter(SourceFile.media_item_id.isnot(None))
    if media_item_ids:
        query = query.filter(SourceFile.media_item_id.in_(media_item_ids))

    for source_file in query.all():
        media = source_file.media_item
        if not media:
            stats["failed"] += 1
            continue

        target = _target_path_for_source(source_file, library_root, media)
        if not target:
            stats["failed"] += 1
            continue

        needs_update = True
        if source_file.library_path:
            try:
                needs_update = Path(source_file.library_path).absolute() != target.absolute()
            except OSError:
                needs_update = True

        if not force_reorganize and not needs_update:
            current = Path(source_file.library_path)
            if current.exists() or current.is_symlink():
                stats["skipped"] += 1
                continue

        if organize_file(
            db,
            source_file,
            library_root,
            link_preference,
            force=force_reorganize or needs_update,
        ):
            stats["linked"] += 1
        else:
            stats["failed"] += 1

    db.commit()
    return stats
