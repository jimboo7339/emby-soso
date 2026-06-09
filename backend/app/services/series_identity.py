from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import (
    MatchHistory,
    MatchStatus,
    MediaItem,
    MediaType,
    ScrapeFieldStatus,
    Season,
    SourceFile,
)
from app.services.parser import (
    ParsedMedia,
    extract_season_episode_from_text,
    infer_tv_series_context,
    is_season_only_folder_name,
    parse_season_from_folder_name,
    series_directory_for_path,
    strip_season_label,
)

logger = logging.getLogger(__name__)

_YEAR_RE = re.compile(r"\(\d{4}\)|(?:\s|[_-])\d{4}$")
_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]+[\u4e00-\u9fff0-9]*")
_MOVIE_FOLDER_SKIP = {
    "movies",
    "movie",
    "film",
    "films",
    "video",
    "videos",
    "media",
    "source",
    "中国版",
    "国语版",
    "粤语版",
}
_LATIN_TITLE_RE = re.compile(r"[A-Za-z][A-Za-z0-9\s:''\-]*")
_SPINOFF_RE = re.compile(r"(?i)\s+presents\s+")


@dataclass
class TvIdentity:
    """单集文件对应的剧集识别信息（不依赖单一父目录）。"""

    primary_title: str
    title_candidates: list[str] = field(default_factory=list)
    series_key: str = ""
    latin_core: str | None = None
    season: int | None = None


def extract_latin_core(title: str | None) -> str | None:
    if not title:
        return None
    parts = [p.strip() for p in _LATIN_TITLE_RE.findall(title) if p.strip()]
    if not parts:
        return None
    core = max(parts, key=len).lower()
    core = re.sub(r"\s+", " ", core).strip()
    return core if len(core) >= 3 else None


def normalize_series_key(title: str | None) -> str:
    if not title:
        return ""
    text = title.strip().lower()
    text = _YEAR_RE.sub("", text)
    text = strip_season_label(text)
    text = _SPINOFF_RE.sub(" ", text)
    text = re.sub(r"[^\w\s\u4e00-\u9fff]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_title_candidates(title: str | None) -> list[str]:
    if not title or not title.strip():
        return []

    raw = title.strip()
    out: list[str] = []

    def add(value: str | None) -> None:
        if not value:
            return
        cleaned = value.strip()
        if cleaned and cleaned not in out:
            out.append(cleaned)

    add(raw)
    add(_YEAR_RE.sub("", raw).strip())
    add(strip_season_label(raw))

    spinoff = _SPINOFF_RE.split(raw, maxsplit=1)
    if len(spinoff) == 2:
        add(spinoff[0].strip())

    latin = extract_latin_core(raw)
    if latin:
        add(latin.title())

    for cjk in _CJK_RUN_RE.findall(raw):
        add(cjk)

    return out


def _movie_folder_candidates(source_path: str) -> list[str]:
    path = Path(source_path)
    out: list[str] = []
    for parent in list(path.parents)[:4]:
        name = parent.name.strip()
        if not name or len(name) < 2:
            continue
        lowered = name.lower()
        if lowered in _MOVIE_FOLDER_SKIP:
            continue
        if lowered.startswith("m0") and lowered[2:].isdigit():
            continue
        for candidate in extract_title_candidates(name):
            if candidate not in out:
                out.append(candidate)
    return out


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _pick_primary_title(candidates: list[str], parsed: ParsedMedia) -> str:
    if not candidates:
        return parsed.title or "Unknown"

    if parsed.season is not None and extract_latin_core(parsed.title):
        cleaned = strip_season_label(_YEAR_RE.sub("", parsed.title or "").strip())
        if cleaned:
            return cleaned

    for candidate in candidates:
        if extract_latin_core(candidate):
            return strip_season_label(_YEAR_RE.sub("", candidate).strip()) or candidate

    return strip_season_label(_YEAR_RE.sub("", candidates[0]).strip()) or candidates[0]


def build_tv_identity(
    full_path: os.PathLike[str] | str,
    source_root: os.PathLike[str] | str,
    parsed: ParsedMedia,
) -> TvIdentity | None:
    if parsed.media_type != "tv":
        return None

    from pathlib import Path

    path = Path(full_path)
    root = Path(source_root)
    ctx = infer_tv_series_context(path, root, parsed)

    candidates: list[str] = []
    if parsed.title:
        candidates.extend(extract_title_candidates(parsed.title))

    if ctx.series_title:
        candidates.extend(extract_title_candidates(ctx.series_title))

    parent_name = path.parent.name
    parent_season = parse_season_from_folder_name(parent_name)
    if parent_season is not None and not is_season_only_folder_name(parent_name):
        candidates.extend(extract_title_candidates(strip_season_label(parent_name)))
    elif not is_season_only_folder_name(parent_name):
        candidates.extend(extract_title_candidates(parent_name))

    candidates = _dedupe(candidates)

    scope = series_scope_directory(path, root)
    scope_title = scope.name if scope else None
    multi_season_layout = False
    if scope is not None:
        try:
            rel_parent = path.parent.resolve().relative_to(scope.resolve())
            multi_season_layout = len(rel_parent.parts) >= 1
        except ValueError:
            multi_season_layout = False

    # 多季子目录（如 黑袍纠察队/第一季、黑袍纠察队/S05）：统一用根文件夹名归组
    if scope_title and multi_season_layout:
        primary = scope_title
        candidates = _dedupe([scope_title, *candidates])
    else:
        primary = _pick_primary_title(candidates, parsed)
    latin_core = extract_latin_core(primary)
    if not latin_core:
        for candidate in candidates:
            latin_core = extract_latin_core(candidate)
            if latin_core:
                break

    season = parsed.season if parsed.season is not None else ctx.season_hint
    series_key = normalize_series_key(primary) or normalize_series_key(candidates[0] if candidates else "")

    return TvIdentity(
        primary_title=primary,
        title_candidates=candidates or [primary],
        series_key=series_key,
        latin_core=latin_core,
        season=season,
    )


def series_scope_directory(
    full_path: os.PathLike[str] | str,
    source_root: os.PathLike[str] | str,
) -> Path | None:
    """剧集归属范围：多季共享根目录；单季则为其所在文件夹。"""
    from pathlib import Path

    path = Path(full_path)
    root = Path(source_root)
    scoped = series_directory_for_path(path, root)
    if scoped is not None:
        return scoped
    return path.parent


def _scope_path_prefix(scope: Path) -> str:
    prefix = str(scope.resolve())
    if not prefix.endswith(os.sep):
        prefix += os.sep
    return prefix


def _path_under_scope(file_path: str, scope_prefix: str) -> bool:
    try:
        return str(Path(file_path).resolve()).lower().startswith(scope_prefix.lower())
    except OSError:
        return file_path.lower().startswith(scope_prefix.lower())


def find_consensus_media_for_scope(
    db: Session,
    scope_prefix: str,
    *,
    exclude_media_id: str | None = None,
) -> MediaItem | None:
    siblings = [
        sf
        for sf in db.query(SourceFile).all()
        if sf.source_path and _path_under_scope(sf.source_path, scope_prefix)
    ]
    if len(siblings) <= 1:
        return None

    groups: dict[str, list[SourceFile]] = {}
    for sf in siblings:
        if not sf.media_item_id or not sf.media_item:
            continue
        if exclude_media_id and sf.media_item_id == exclude_media_id:
            continue
        groups.setdefault(sf.media_item_id, []).append(sf)

    if not groups:
        return None

    def rank(item: tuple[str, list[SourceFile]]) -> tuple[int, int, int, float]:
        _, files = item
        media = files[0].media_item
        if not media:
            return (0, 0, 0, 0.0)
        seasons = len({sf.parsed_season for sf in files if sf.parsed_season is not None})
        has_tmdb = 1 if media.tmdb_id else 0
        matched = 1 if media.match_status in {MatchStatus.AUTO, MatchStatus.MANUAL} else 0
        return (len(files), seasons, has_tmdb, matched * 100 + (media.match_confidence or 0.0))

    best_id, best_files = max(groups.items(), key=rank)
    best_media = best_files[0].media_item
    if not best_media:
        return None

    # 同一剧集根目录下出现多个 MediaItem 时，强制合并到文件最多/季最全的一条
    if len(groups) > 1:
        return best_media

    total_assigned = sum(len(v) for v in groups.values())
    best_count = len(best_files)

    if best_count >= 2 and best_count >= total_assigned / 2:
        return best_media

    if best_media.tmdb_id and best_count >= 1 and total_assigned <= 3:
        return best_media

    return None


def find_sibling_consensus_media(
    db: Session,
    full_path: os.PathLike[str] | str,
    source_root: os.PathLike[str] | str,
    *,
    exclude_media_id: str | None = None,
) -> MediaItem | None:
    """
    同剧集目录下，已识别季/集占多数的 MediaItem 作为共识。
    若目录内已有 TMDB 匹配结果，误识别的单季应跟随共识。
    """
    from pathlib import Path

    scope = series_scope_directory(full_path, source_root)
    if scope is None:
        return None

    return find_consensus_media_for_scope(
        db,
        _scope_path_prefix(scope),
        exclude_media_id=exclude_media_id,
    )


def resolve_tv_season(parsed: ParsedMedia, identity: TvIdentity) -> int | None:
    """季号：文件名 SxxExx > guessit > 文件夹提示。"""
    if parsed.season is not None:
        return parsed.season
    return identity.season


def has_sxxexx_in_filename(full_path: os.PathLike[str] | str) -> bool:
    from pathlib import Path

    path = Path(full_path)
    season, episode = extract_season_episode_from_text(path.name)
    if season is not None and episode is not None:
        return True
    return extract_season_episode_from_text(path.stem) != (None, None)


def identity_matches_title(identity: TvIdentity, title: str | None) -> bool:
    if not title:
        return False

    other_key = normalize_series_key(title)
    if identity.series_key and other_key and identity.series_key == other_key:
        return True

    other_latin = extract_latin_core(title)
    if identity.latin_core and other_latin and identity.latin_core == other_latin:
        return True

    for candidate in identity.title_candidates:
        if normalize_series_key(candidate) == other_key:
            return True
        if SequenceMatcher(None, normalize_series_key(candidate), other_key).ratio() >= 0.88:
            return True

    if identity.latin_core and other_latin:
        if SequenceMatcher(None, identity.latin_core, other_latin).ratio() >= 0.9:
            return True

    return titles_equivalent(identity.primary_title, title)


def titles_equivalent(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    left = normalize_series_key(a)
    right = normalize_series_key(b)
    if not left or not right:
        return False
    if left == right or left in right or right in left:
        return True
    latin_a = extract_latin_core(a)
    latin_b = extract_latin_core(b)
    if latin_a and latin_b and latin_a == latin_b:
        return True
    return SequenceMatcher(None, left, right).ratio() >= 0.88


def gather_tmdb_search_queries(media: MediaItem, source_files: list[SourceFile] | None = None) -> list[str]:
    queries: list[str] = []
    files = source_files if source_files is not None else list(media.source_files)

    def add(value: str | None) -> None:
        if not value:
            return
        for candidate in extract_title_candidates(value):
            if candidate not in queries:
                queries.append(candidate)

    add(media.title)
    add(media.original_title)
    for sf in files:
        add(sf.parsed_title)
        if media.media_type == MediaType.MOVIE:
            for folder_title in _movie_folder_candidates(sf.source_path):
                add(folder_title)

    latin_first = [q for q in queries if extract_latin_core(q)]
    other = [q for q in queries if q not in latin_first]
    return _dedupe(latin_first + other)


def find_matching_tv_media(
    db: Session,
    identity: TvIdentity,
    *,
    full_path: os.PathLike[str] | str | None = None,
    source_root: os.PathLike[str] | str | None = None,
    exclude_media_id: str | None = None,
) -> MediaItem | None:
    if full_path is not None and source_root is not None:
        consensus = find_sibling_consensus_media(
            db,
            full_path,
            source_root,
            exclude_media_id=exclude_media_id,
        )
        if consensus is not None:
            return consensus

    tv_query = db.query(MediaItem).filter(MediaItem.media_type == MediaType.TV)
    if exclude_media_id:
        tv_query = tv_query.filter(MediaItem.id != exclude_media_id)

    for media in tv_query.all():
        if identity_matches_title(identity, media.title):
            return media
        if media.original_title and identity_matches_title(identity, media.original_title):
            return media

    linked = (
        db.query(SourceFile)
        .filter(SourceFile.media_item_id.isnot(None), SourceFile.parsed_title.isnot(None))
        .all()
    )
    for sf in linked:
        if not sf.parsed_title or not sf.media_item:
            continue
        if exclude_media_id and sf.media_item_id == exclude_media_id:
            continue
        if identity_matches_title(identity, sf.parsed_title):
            return sf.media_item

    if identity.latin_core:
        for media in tv_query.filter(MediaItem.tmdb_id.isnot(None)).all():
            if extract_latin_core(media.title) == identity.latin_core:
                return media
            if media.original_title and extract_latin_core(media.original_title) == identity.latin_core:
                return media

    return None


def _pick_canonical_media(items: list[MediaItem]) -> MediaItem:
    def rank(media: MediaItem) -> tuple[int, int, int, float, str]:
        file_count = len(media.source_files)
        has_year = 1 if media.year else 0
        manual = 1 if media.match_status == MatchStatus.MANUAL else 0
        confidence = media.match_confidence or 0.0
        return (file_count, has_year, manual, confidence, media.created_at.isoformat())

    return sorted(items, key=rank, reverse=True)[0]


def _merge_media_metadata(canonical: MediaItem, duplicate: MediaItem) -> None:
    if not canonical.year and duplicate.year:
        canonical.year = duplicate.year
    if not canonical.original_title and duplicate.original_title:
        canonical.original_title = duplicate.original_title
    if not canonical.tmdb_id and duplicate.tmdb_id:
        canonical.tmdb_id = duplicate.tmdb_id
    if canonical.match_status != MatchStatus.MANUAL and duplicate.match_status == MatchStatus.MANUAL:
        canonical.match_status = duplicate.match_status
        canonical.match_confidence = duplicate.match_confidence


def _repoint_media_children(db: Session, duplicate: MediaItem, canonical: MediaItem) -> None:
    db.query(SourceFile).filter(SourceFile.media_item_id == duplicate.id).update(
        {SourceFile.media_item_id: canonical.id}
    )
    db.query(MatchHistory).filter(MatchHistory.media_item_id == duplicate.id).update(
        {MatchHistory.media_item_id: canonical.id}
    )
    db.query(ScrapeFieldStatus).filter(ScrapeFieldStatus.media_item_id == duplicate.id).delete()
    db.query(Season).filter(Season.media_item_id == duplicate.id).delete()


def _consolidate_media_by_tmdb(db: Session, media_type: MediaType) -> dict[str, int]:
    """同一 TMDB ID 的条目合并为一个 MediaItem。"""
    stats = {"merged": 0, "groups": 0}

    matched = (
        db.query(MediaItem)
        .filter(MediaItem.media_type == media_type, MediaItem.tmdb_id.isnot(None))
        .all()
    )
    groups: dict[int, list[MediaItem]] = {}
    for media in matched:
        groups.setdefault(int(media.tmdb_id), []).append(media)

    for tmdb_id, items in groups.items():
        if len(items) < 2:
            continue
        stats["groups"] += 1
        canonical = _pick_canonical_media(items)
        for item in items:
            if item.id == canonical.id:
                continue
            _merge_media_metadata(canonical, item)
            _repoint_media_children(db, item, canonical)
            db.delete(item)
            stats["merged"] += 1
            logger.info(
                "Merged duplicate %s media tmdb_id=%s: %s -> %s",
                media_type.value,
                tmdb_id,
                item.title,
                canonical.title,
            )

    if stats["merged"]:
        db.flush()
    return stats


def consolidate_tv_media_by_tmdb(db: Session) -> dict[str, int]:
    """同一 TMDB 剧集 ID 的条目合并为一个 MediaItem（跨目录、跨季）。"""
    return _consolidate_media_by_tmdb(db, MediaType.TV)


def consolidate_movie_media_by_tmdb(db: Session) -> dict[str, int]:
    """同一 TMDB 电影 ID 的条目合并为一个 MediaItem。"""
    return _consolidate_media_by_tmdb(db, MediaType.MOVIE)


def find_matching_movie_media(
    db: Session,
    title: str | None,
    year: int | None = None,
    *,
    exclude_media_id: str | None = None,
) -> MediaItem | None:
    if not title:
        return None

    query = db.query(MediaItem).filter(MediaItem.media_type == MediaType.MOVIE)
    if exclude_media_id:
        query = query.filter(MediaItem.id != exclude_media_id)

    if year is not None:
        exact = query.filter(MediaItem.title == title, MediaItem.year == year).first()
        if exact:
            return exact

    exact = query.filter(MediaItem.title == title).first()
    if exact:
        return exact

    candidates = set(extract_title_candidates(title))
    for media in query.all():
        if year is not None and media.year is not None and media.year != year:
            continue
        if titles_equivalent(media.title, title):
            return media
        if media.original_title and titles_equivalent(media.original_title, title):
            return media
        for candidate in extract_title_candidates(media.title):
            if candidate in candidates:
                return media
        if media.original_title:
            for candidate in extract_title_candidates(media.original_title):
                if candidate in candidates:
                    return media
    return None


def _cleanup_orphan_media(db: Session, media_type: MediaType) -> dict[str, int]:
    stats = {"removed": 0}
    items = db.query(MediaItem).filter(MediaItem.media_type == media_type).all()
    for media in items:
        file_count = (
            db.query(SourceFile)
            .filter(SourceFile.media_item_id == media.id)
            .count()
        )
        if file_count > 0:
            continue
        db.query(MatchHistory).filter(MatchHistory.media_item_id == media.id).delete()
        db.query(ScrapeFieldStatus).filter(ScrapeFieldStatus.media_item_id == media.id).delete()
        if media_type == MediaType.TV:
            db.query(Season).filter(Season.media_item_id == media.id).delete()
        db.delete(media)
        stats["removed"] += 1
        logger.info(
            "Removed orphan %s media: %s (tmdb=%s)",
            media_type.value,
            media.title,
            media.tmdb_id,
        )
    if stats["removed"]:
        db.flush()
    return stats


def consolidate_tv_media_by_identity(db: Session) -> dict[str, int]:
    """未匹配条目按识别指纹合并，减少重复剧集。"""
    stats = {"merged": 0}

    unmatched = (
        db.query(MediaItem)
        .filter(
            MediaItem.media_type == MediaType.TV,
            MediaItem.tmdb_id.is_(None),
        )
        .order_by(MediaItem.created_at)
        .all()
    )

    canonical_by_key: dict[str, MediaItem] = {}
    for media in unmatched:
        keys = {normalize_series_key(media.title)}
        latin = extract_latin_core(media.title)
        if latin:
            keys.add(latin)
        for sf in media.source_files:
            keys.add(normalize_series_key(sf.parsed_title))
            sf_latin = extract_latin_core(sf.parsed_title)
            if sf_latin:
                keys.add(sf_latin)

        target: MediaItem | None = None
        for key in keys:
            if not key:
                continue
            if key in canonical_by_key:
                target = canonical_by_key[key]
                break

        if target is None:
            for key in keys:
                if key:
                    canonical_by_key[key] = media
            continue

        if target.id == media.id:
            continue

        _repoint_media_children(db, media, target)
        db.delete(media)
        stats["merged"] += 1
        for key in keys:
            if key:
                canonical_by_key[key] = target

    if stats["merged"]:
        db.flush()
    return stats


def consolidate_by_series_scope(db: Session, source_root: str) -> dict[str, int]:
    """扫描结束后：同剧集目录内所有含 SxxExx 的文件跟随目录共识 MediaItem。"""
    from pathlib import Path

    root = Path(source_root)
    stats = {"reassigned": 0, "scopes": 0}

    scopes: set[str] = set()
    for sf in db.query(SourceFile).filter(SourceFile.source_path.isnot(None)).all():
        scope = series_scope_directory(Path(sf.source_path), root)
        if scope is not None:
            scopes.add(_scope_path_prefix(scope))

    for prefix in scopes:
        consensus = find_consensus_media_for_scope(db, prefix)
        if consensus is None:
            continue

        scope_files = [
            sf
            for sf in db.query(SourceFile).all()
            if sf.source_path and _path_under_scope(sf.source_path, prefix)
        ]
        if len(scope_files) <= 1:
            continue

        changed = False
        for sf in scope_files:
            if not has_sxxexx_in_filename(sf.source_path):
                continue
            if sf.media_item_id != consensus.id:
                sf.media_item_id = consensus.id
                stats["reassigned"] += 1
                changed = True

        if changed:
            stats["scopes"] += 1
            logger.info(
                "Applied sibling consensus under %s -> %s (tmdb=%s)",
                prefix,
                consensus.title,
                consensus.tmdb_id,
            )

    if stats["reassigned"]:
        db.flush()
    return stats


def cleanup_orphan_tv_media(db: Session) -> dict[str, int]:
    """删除无源文件的重复/空剧集条目。"""
    return _cleanup_orphan_media(db, MediaType.TV)


def cleanup_orphan_movie_media(db: Session) -> dict[str, int]:
    """删除无源文件的空电影条目。"""
    return _cleanup_orphan_media(db, MediaType.MOVIE)
