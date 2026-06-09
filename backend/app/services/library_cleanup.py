from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import FileStatus, MatchHistory, MediaItem, MediaType, ScrapeFieldStatus, SourceFile, Task
from app.services.library_paths import (
    all_library_roots,
    content_folder_from_library_file,
    is_outside_source_paths,
    iter_library_files,
    prune_empty_library_dirs,
    resolve_deletion_target,
    resolve_library_root_for_media,
    resolve_movie_folder,
    resolve_show_folder,
    safe_unlink_library_entry,
    show_folder_for_file,
)
from app.services.organizer import build_tv_series_folder_name, organize_media_items
from app.services.path_utils import (
    is_under_root,
    normalize_path,
    paths_equal,
    safe_rmtree_library_folder,
)
from app.services.series_identity import (
    _path_under_scope,
    _scope_path_prefix,
    series_scope_directory,
)

logger = logging.getLogger(__name__)


def _collect_scope_prefixes_for_media(db: Session, media: MediaItem) -> set[str]:
    prefixes: set[str] = set()
    task_roots = [t.source_path for t in db.query(Task).filter(Task.source_path.isnot(None)).all()]
    for sf in media.source_files:
        if not sf.source_path:
            continue
        path = Path(sf.source_path)
        for root_str in task_roots:
            root = Path(root_str)
            try:
                path.resolve().relative_to(root.resolve())
            except ValueError:
                continue
            scope = series_scope_directory(path, root)
            if scope is not None:
                prefixes.add(_scope_path_prefix(scope))
            break
    return prefixes


def _related_tv_media_ids(db: Session, media: MediaItem) -> set[str]:
    if media.media_type != MediaType.TV:
        return {media.id}
    prefixes = _collect_scope_prefixes_for_media(db, media)
    if not prefixes:
        return {media.id}
    ids: set[str] = set()
    for sf in db.query(SourceFile).filter(SourceFile.media_item_id.isnot(None)).all():
        if not sf.source_path or not sf.media_item_id:
            continue
        for prefix in prefixes:
            if _path_under_scope(sf.source_path, prefix):
                ids.add(sf.media_item_id)
                break
    return ids or {media.id}


def _reset_source_file_library_state(source_file: SourceFile) -> None:
    source_file.library_path = None
    source_file.link_type = None
    source_file.file_status = FileStatus.DISCOVERED
    source_file.error_message = None


def remove_source_file_from_library(
    db: Session,
    source_file: SourceFile,
    media: MediaItem,
    *,
    library_root: str,
) -> bool:
    """移除单集/单文件的库链接，保留源文件，状态重置为 discovered。"""
    lib_target = resolve_deletion_target(source_file, media, library_root)
    removed = False

    if lib_target:
        try:
            safe_unlink_library_entry(
                lib_target,
                source_file.source_path,
                source_file.link_type,
            )
            removed = True
        except PermissionError as exc:
            logger.error("Unsafe library delete blocked: %s", exc)
            raise
        except OSError as exc:
            logger.exception("Failed to remove library file: %s", lib_target)
            raise exc
    elif source_file.library_path:
        logger.warning(
            "No safe library target for %s (stored=%s), only clearing DB state",
            source_file.id,
            source_file.library_path,
        )

    _reset_source_file_library_state(source_file)
    db.flush()
    return removed


def remove_media_from_library(
    db: Session,
    media: MediaItem,
    *,
    library_root: str | None = None,
) -> dict[str, int]:
    """移除整部媒体在影视库中的所有整理链接，保留源文件。"""
    library_root = library_root or resolve_library_root_for_media(db, media)
    stats = {"removed": 0, "skipped": 0, "errors": 0}
    library_dirs: set[Path] = set()

    for source_file in list(media.source_files):
        lib_target = resolve_deletion_target(source_file, media, library_root)
        if not lib_target and not source_file.library_path:
            stats["skipped"] += 1
            continue

        if lib_target:
            library_dirs.add(lib_target.parent)

        try:
            if remove_source_file_from_library(
                db, source_file, media, library_root=library_root
            ):
                stats["removed"] += 1
            else:
                stats["skipped"] += 1
        except (OSError, PermissionError):
            stats["errors"] += 1

    for folder in sorted(library_dirs, key=lambda p: len(p.parts), reverse=True):
        prune_empty_library_dirs(folder, library_root)

    db.commit()
    return stats


def remove_media_file_from_library(
    db: Session,
    media_id: str,
    source_file_id: str,
    *,
    library_root: str | None = None,
) -> dict[str, int]:
    source_file = (
        db.query(SourceFile)
        .filter(SourceFile.id == source_file_id, SourceFile.media_item_id == media_id)
        .first()
    )
    if not source_file:
        raise LookupError("Source file not found")

    media = source_file.media_item
    if not media:
        raise LookupError("Media item not found")

    library_root = library_root or resolve_library_root_for_media(db, media)
    lib_target = resolve_deletion_target(source_file, media, library_root)

    try:
        removed = remove_source_file_from_library(
            db, source_file, media, library_root=library_root
        )
    except (OSError, PermissionError):
        db.rollback()
        raise

    if lib_target:
        prune_empty_library_dirs(lib_target.parent, library_root)

    db.commit()
    return {"removed": 1 if removed else 0, "skipped": 0 if removed else 1, "errors": 0}


def reorganize_media(
    db: Session, media_id: str, library_root: str, *, link_preference: str = "auto"
) -> dict[str, int]:
    return organize_media_items(
        db,
        library_root,
        link_preference=link_preference,
        media_item_ids=[media_id],
        force_reorganize=True,
    )


def _protected_source_roots(db: Session) -> list[Path]:
    roots = {normalize_path(get_settings().data_source_root)}
    for task in db.query(Task).all():
        roots.add(normalize_path(task.source_path))
    return list(roots)


def _discover_library_folders_on_disk(
    media: MediaItem, library_roots: list[Path]
) -> set[Path]:
    """按 TMDB ID / 标题在影视库目录中查找可能遗漏的文件夹。"""
    found: set[Path] = set()

    for root in library_roots:
        if media.media_type == MediaType.TV and media.tmdb_id:
            tv_root = root / "TV Shows"
            if not tv_root.is_dir():
                continue
            suffix = f" {media.tmdb_id}"
            for entry in tv_root.iterdir():
                if entry.is_dir() and (
                    entry.name.endswith(suffix) or f" {media.tmdb_id}" in entry.name
                ):
                    found.add(normalize_path(entry))
        elif media.media_type == MediaType.MOVIE:
            movies_root = root / "Movies"
            if not movies_root.is_dir():
                continue
            title_key = (media.title or "").strip().lower()
            for entry in movies_root.iterdir():
                if entry.is_dir() and title_key and title_key in entry.name.lower():
                    found.add(normalize_path(entry))

        if media.media_type == MediaType.TV and media.title:
            expected = build_tv_series_folder_name(
                media.title,
                media.year,
                media.tmdb_id,
            )
            candidate = root / "TV Shows" / expected
            if candidate.is_dir():
                found.add(normalize_path(candidate))

    return found


def _collect_library_folders(
    media: MediaItem, db: Session, library_roots: list[Path]
) -> set[Path]:
    folders: set[Path] = set()
    protected = _protected_source_roots(db)

    for root in library_roots:
        root_str = str(root)
        show = resolve_show_folder(media, root_str)
        if show:
            folders.add(normalize_path(show))

        for _sf, library_file in iter_library_files(media, root_str):
            if media.media_type == MediaType.MOVIE:
                folders.add(normalize_path(resolve_movie_folder(library_file)))
            else:
                folders.add(normalize_path(show_folder_for_file(library_file)))

    for sf in media.source_files:
        if not sf.library_path:
            continue
        lib = normalize_path(sf.library_path)
        source = normalize_path(sf.source_path)
        if paths_equal(lib, source):
            continue
        if not is_outside_source_paths(lib, protected):
            continue
        folders.add(content_folder_from_library_file(lib, media.media_type))

    folders.update(_discover_library_folders_on_disk(media, library_roots))

    return {normalize_path(f) for f in folders if normalize_path(f).exists()}


def reset_media_item(
    db: Session,
    media: MediaItem,
    *,
    library_root: str | None = None,
) -> dict[str, int | bool | list[str]]:
    """
    完全重置媒体：删除影视库内该条目全部文件（含 NFO/图片/链接），
    并删除数据库记录。源目录文件保留，下次扫描会重新识别。

    剧集：同源目录下同一剧集根文件夹内的所有拆分条目一并重置。
    """
    related_ids = _related_tv_media_ids(db, media)
    targets = (
        db.query(MediaItem)
        .filter(MediaItem.id.in_(related_ids))
        .all()
        if len(related_ids) > 1
        else [media]
    )

    library_roots = all_library_roots(db, media)
    if library_root:
        library_roots.append(normalize_path(library_root))
    library_roots = list({str(p): normalize_path(p) for p in library_roots}.values())

    protected = _protected_source_roots(db)
    folders: set[Path] = set()
    had_library_refs = False
    for target in targets:
        folders.update(_collect_library_folders(target, db, library_roots))
        if any(sf.library_path for sf in target.source_files):
            had_library_refs = True

    folders_removed = 0
    removed_paths: list[str] = []
    for folder in sorted(folders, key=lambda p: len(p.parts), reverse=True):
        try:
            if safe_rmtree_library_folder(
                folder,
                allowed_library_roots=library_roots,
                protected_roots=protected,
            ):
                folders_removed += 1
                removed_paths.append(str(folder))
        except PermissionError:
            logger.exception("Blocked unsafe library folder delete: %s", folder)
            raise
        except OSError:
            logger.exception("Failed to remove library folder: %s", folder)
            raise

    if had_library_refs and folders_removed == 0 and not folders:
        logger.warning(
            "Reset media %s: had library_path in DB but no library folders resolved",
            media.id,
        )

    for target in targets:
        for sf in list(target.source_files):
            sf.media_item_id = None
            sf.library_path = None
            sf.link_type = None
            sf.file_status = FileStatus.DISCOVERED
            sf.error_message = None

        db.query(MatchHistory).filter(MatchHistory.media_item_id == target.id).delete()
        db.query(ScrapeFieldStatus).filter(ScrapeFieldStatus.media_item_id == target.id).delete()
        db.delete(target)

    db.commit()

    return {
        "library_folders_removed": folders_removed,
        "media_deleted": True,
        "removed_paths": removed_paths,
        "related_media_reset": len(targets),
    }
