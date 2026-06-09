from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from app.models import LinkType

logger = logging.getLogger(__name__)


def normalize_path(path: str | Path) -> Path:
    return Path(path).absolute()


def is_under_root(path: str | Path, root: str | Path) -> bool:
    try:
        normalize_path(path).relative_to(normalize_path(root))
        return True
    except ValueError:
        return False


def paths_equal(a: str | Path, b: str | Path) -> bool:
    return normalize_path(a) == normalize_path(b)


def same_inode(a: str | Path, b: str | Path) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return paths_equal(a, b)


def safe_unlink_library_entry(
    lib_path: str | Path,
    source_path: str | Path,
    link_type: LinkType | None = None,
) -> None:
    """仅移除影视库侧的链接/条目，绝不删除源路径上的原始文件。"""
    lib = normalize_path(lib_path)
    source = normalize_path(source_path)

    if paths_equal(lib, source):
        raise PermissionError(
            f"拒绝删除：库路径与源路径相同 ({lib})，继续操作会删除原始文件"
        )

    if not lib.exists() and not lib.is_symlink():
        return

    if link_type == LinkType.SYMLINK or lib.is_symlink():
        lib.unlink()
        return

    if link_type == LinkType.HARDLINK:
        lib.unlink()
        return

    if same_inode(lib, source):
        lib.unlink()
        return

    lib.unlink()


def validate_library_target(
    target: Path,
    source: Path,
    library_root: str,
) -> None:
    target_abs = normalize_path(target)
    source_abs = normalize_path(source)
    lib_root = normalize_path(library_root)

    if paths_equal(target_abs, source_abs):
        raise ValueError(
            f"整理目标与源路径相同 ({target_abs})，请检查 library_path 配置"
        )
    if not is_under_root(target_abs, lib_root):
        raise ValueError(
            f"整理目标不在影视库内 ({target_abs})，library_root={lib_root}"
        )


def prune_empty_library_dirs(start: Path, library_root: str) -> None:
    lib_root = normalize_path(library_root)
    current = normalize_path(start)

    if not is_under_root(current, lib_root):
        logger.warning(
            "Skip prune: %s is not under library root %s",
            current,
            lib_root,
        )
        return

    while current != lib_root and current.exists() and current.is_dir():
        try:
            if any(current.iterdir()):
                break
            current.rmdir()
        except OSError:
            break
        current = current.parent


def safe_rmtree_library_folder(
    folder: str | Path,
    *,
    allowed_library_roots: list[Path] | None = None,
    protected_roots: list[Path] | None = None,
) -> bool:
    """删除影视库内整个媒体目录（含 NFO、图片、链接），不触碰源目录。"""
    target = normalize_path(folder)

    for prot in protected_roots or []:
        prot_norm = normalize_path(prot)
        if is_under_root(target, prot_norm) or paths_equal(target, prot_norm):
            raise PermissionError(f"拒绝删除：路径位于源目录内 ({target})")

    allowed = [normalize_path(r) for r in (allowed_library_roots or [])]
    if allowed:
        under_library = any(
            is_under_root(target, root) or paths_equal(target, root) for root in allowed
        )
        if not under_library:
            raise PermissionError(f"拒绝删除：路径不在任何影视库根目录下 ({target})")
    elif not _looks_like_library_content(target):
        raise PermissionError(f"拒绝删除：不像影视库内容路径 ({target})")

    if not target.exists():
        return False

    shutil.rmtree(target)
    return True


def _looks_like_library_content(path: Path) -> bool:
    parts = {p.lower() for p in path.parts}
    return "tv shows" in parts or "movies" in parts
