from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import LinkType, MediaItem, SourceFile, Task
from app.services.path_utils import (
    is_under_root,
    normalize_path,
    paths_equal,
    prune_empty_library_dirs,
    safe_unlink_library_entry,
    validate_library_target,
)

logger = logging.getLogger(__name__)

__all__ = [
    "effective_library_file_path",
    "iter_library_files",
    "resolve_deletion_target",
    "resolve_library_root_for_media",
    "all_library_roots",
    "is_outside_source_paths",
    "content_folder_from_library_file",
    "resolve_movie_folder",
    "resolve_show_folder",
    "show_folder_for_file",
    "prune_empty_library_dirs",
    "safe_unlink_library_entry",
    "validate_library_target",
    "is_under_root",
    "paths_equal",
]


def _target_path_for_source(source_file, library_root, media):
    from app.services.organizer import _target_path_for_source as fn

    return fn(source_file, library_root, media)


def resolve_library_root_for_media(db: Session, media: MediaItem) -> str:
    for sf in media.source_files:
        source = normalize_path(sf.source_path)
        tasks = db.query(Task).order_by(Task.updated_at.desc()).all()
        for task in tasks:
            task_source = normalize_path(task.source_path)
            if source == task_source or is_under_root(source, task_source):
                return task.library_path
    return get_settings().data_library_root


def all_library_roots(db: Session, media: MediaItem | None = None) -> list[Path]:
    roots: set[str] = {get_settings().data_library_root}
    for task in db.query(Task).all():
        if task.library_path:
            roots.add(task.library_path)
    if media:
        roots.add(resolve_library_root_for_media(db, media))
    return [normalize_path(r) for r in roots if r]


def is_outside_source_paths(path: str | Path, protected_roots: list[Path]) -> bool:
    target = normalize_path(path)
    for prot in protected_roots:
        prot_norm = normalize_path(prot)
        if is_under_root(target, prot_norm) or paths_equal(target, prot_norm):
            return False
    return True


def content_folder_from_library_file(library_file: Path, media_type) -> Path:
    from app.models import MediaType

    lib = normalize_path(library_file)
    if media_type == MediaType.MOVIE:
        return lib.parent
    return show_folder_for_file(lib)


def effective_library_file_path(
    source_file: SourceFile,
    media: MediaItem,
    library_root: str,
) -> Path | None:
    computed = _target_path_for_source(source_file, library_root, media)
    if not computed:
        return None

    if source_file.library_path:
        stored = Path(source_file.library_path)
        if is_under_root(stored, library_root):
            return stored.absolute()
        logger.warning(
            "SourceFile %s library_path 不在影视库内 (%s)，改用计算路径 %s",
            source_file.id,
            source_file.library_path,
            computed,
        )

    return computed.absolute()


def show_folder_for_file(library_file: Path) -> Path:
    parent = library_file.parent
    if parent.name.lower().startswith("season"):
        return parent.parent
    return parent


def resolve_show_folder(media: MediaItem, library_root: str) -> Path | None:
    for sf in media.source_files:
        target = effective_library_file_path(sf, media, library_root)
        if target:
            return show_folder_for_file(target)
    return None


def resolve_movie_folder(library_file: Path) -> Path:
    return library_file.parent


def resolve_deletion_target(
    source_file: SourceFile,
    media: MediaItem,
    library_root: str,
) -> Path | None:
    """解析可安全删除的库内链接路径（必须在 library_root 下且不能是源路径）。"""
    source = normalize_path(source_file.source_path)
    lib_root = normalize_path(library_root)

    candidates: list[Path] = []
    if source_file.library_path:
        candidates.append(normalize_path(source_file.library_path))
    computed = effective_library_file_path(source_file, media, library_root)
    if computed:
        candidates.append(normalize_path(computed))

    seen: set[str] = set()
    for lib in candidates:
        key = str(lib)
        if key in seen:
            continue
        seen.add(key)

        if not is_under_root(lib, lib_root):
            logger.warning(
                "Skip delete: path not under library root: %s (root=%s)",
                lib,
                lib_root,
            )
            continue
        if paths_equal(lib, source):
            logger.error("Skip delete: library path equals source path: %s", lib)
            continue
        if lib.exists() or lib.is_symlink():
            return lib

    return None


def iter_library_files(
    media: MediaItem, library_root: str
) -> list[tuple[SourceFile, Path]]:
    pairs: list[tuple[SourceFile, Path]] = []
    for sf in media.source_files:
        target = effective_library_file_path(sf, media, library_root)
        if target:
            pairs.append((sf, target))
    return pairs
