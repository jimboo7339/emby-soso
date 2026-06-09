from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import guessit

# 常规视频 + Emby/Jellyfin 常用的 STRM 指针文件
MEDIA_EXTENSIONS = {
    ".mkv",
    ".mp4",
    ".avi",
    ".mov",
    ".wmv",
    ".flv",
    ".m4v",
    ".ts",
    ".m2ts",
    ".webm",
    ".iso",
    ".strm",
}

# 兼容旧引用
VIDEO_EXTENSIONS = MEDIA_EXTENSIONS


@dataclass
class ParsedMedia:
    title: str | None
    year: int | None
    season: int | None
    episode: int | None
    media_type: str  # movie | tv | unknown
    episode_title: str | None
    raw: dict
    is_strm: bool = False
    strm_target: str | None = None


def is_strm_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() == ".strm"


def is_media_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in MEDIA_EXTENSIONS


def is_video_file(path: Path) -> bool:
    return is_media_file(path)


def read_strm_target(path: Path) -> str | None:
    """读取 STRM 文件首行（通常为远程媒体 URL 或本地路径）。"""
    try:
        line = path.read_text(encoding="utf-8", errors="ignore").strip().splitlines()[0].strip()
        return line or None
    except OSError:
        return None


def _basename_from_strm_target(target: str) -> str:
    cleaned = target.replace("\\", "/").split("?")[0].split("#")[0]
    name = Path(cleaned).name
    return name or cleaned


def _guessit_name_for_path(path: Path) -> str:
    """guessit 对 .strm 扩展名识别较弱，借用 .mkv 辅助解析文件名。"""
    if path.suffix.lower() == ".strm":
        return f"{path.stem}.mkv"
    return path.name


_SXXEXX_RE = re.compile(r"(?<![A-Z0-9])S(\d{1,2})E(\d{1,2})(?![A-Z0-9])", re.I)


def extract_season_episode_from_text(text: str | None) -> tuple[int | None, int | None]:
    """从文本中提取 SxxExx（剧集识别最可靠信号）。"""
    if not text:
        return None, None
    match = _SXXEXX_RE.search(text)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def apply_sxxexx_override(parsed: ParsedMedia, *texts: str | None) -> ParsedMedia:
    """文件名/URL 中的 SxxExx 优先于 guessit 的季集解析。"""
    for text in texts:
        season, episode = extract_season_episode_from_text(text)
        if season is not None and episode is not None:
            parsed.season = season
            parsed.episode = episode
            parsed.media_type = "tv"
            break
    return parsed


_TRAILING_YEAR_RE = re.compile(r"^(?P<title>.+?)[\s._-]+(?P<year>\d{4})$")


def _normalize_movie_fields(title: str | None, year: int | None) -> tuple[str | None, int | None]:
    """guessit 有时把年份留在 title 里（如「误杀 xxx 2019」），拆出来便于匹配。"""
    if not title:
        return title, year
    cleaned = title.strip()
    if year is not None:
        return cleaned, year
    match = _TRAILING_YEAR_RE.match(cleaned)
    if not match:
        return cleaned, year
    return match.group("title").strip(), int(match.group("year"))


def _coerce_int(value: Any) -> int | None:
    """guessit 有时会把 season/episode 解析为 list，统一转为 int。"""
    if value is None:
        return None
    if isinstance(value, list):
        if not value:
            return None
        value = value[0]
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)
        try:
            return int(float(stripped))
        except ValueError:
            return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _data_to_parsed(data: dict[str, Any], *, is_strm: bool = False, strm_target: str | None = None) -> ParsedMedia:
    title = data.get("title")
    if title:
        title = str(title).strip()

    year = _coerce_int(data.get("year"))
    season = _coerce_int(data.get("season"))
    episode = _coerce_int(data.get("episode"))

    guess_type = str(data.get("type", "")).lower()
    if season is not None or episode is not None or guess_type in {"episode", "tv"}:
        media_type = "tv"
    elif guess_type == "movie" or title:
        media_type = "movie"
    else:
        media_type = "unknown"

    if media_type == "movie":
        title, year = _normalize_movie_fields(title, year)

    episode_title = data.get("episode_title")
    if episode_title:
        episode_title = str(episode_title).strip()

    return ParsedMedia(
        title=title,
        year=year,
        season=season,
        episode=episode,
        media_type=media_type,
        episode_title=episode_title,
        raw=data,
        is_strm=is_strm,
        strm_target=strm_target,
    )


def _parse_guessit(name: str) -> ParsedMedia:
    return _data_to_parsed(dict(guessit.guessit(name)))


def _merge_parsed(primary: ParsedMedia, secondary: ParsedMedia) -> ParsedMedia:
    """文件名解析优先，缺失字段用 STRM 内 URL 路径补全。"""
    merged_raw = {**secondary.raw, **primary.raw}
    return ParsedMedia(
        title=primary.title or secondary.title,
        year=primary.year if primary.year is not None else secondary.year,
        season=primary.season if primary.season is not None else secondary.season,
        episode=primary.episode if primary.episode is not None else secondary.episode,
        media_type=(
            primary.media_type
            if primary.media_type != "unknown"
            else secondary.media_type
        ),
        episode_title=primary.episode_title or secondary.episode_title,
        raw=merged_raw,
        is_strm=primary.is_strm,
        strm_target=primary.strm_target,
    )


def _is_weak_strm_filename(path: Path, title: str | None) -> bool:
    if not title:
        return True
    stem = path.stem.lower()
    if title.lower() == stem:
        return True
    if title.lower() in {"movie", "video", "index", "play", "media", "stream"}:
        return True
    return len(title) < 2


def parse_filename(path: str | Path) -> ParsedMedia:
    path = Path(path)
    parsed = _parse_guessit(_guessit_name_for_path(path))
    parsed.is_strm = is_strm_file(path)
    url_name: str | None = None

    if parsed.is_strm:
        strm_target = read_strm_target(path)
        parsed.strm_target = strm_target
        if strm_target:
            url_name = _basename_from_strm_target(strm_target)
            if url_name and url_name != path.name:
                from_url = _parse_guessit(url_name)
                if _is_weak_strm_filename(path, parsed.title):
                    parsed = _merge_parsed(from_url, parsed)
                else:
                    parsed = _merge_parsed(parsed, from_url)
                parsed.is_strm = True
                parsed.strm_target = strm_target

    apply_sxxexx_override(parsed, path.name, path.stem, url_name)
    return parsed


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]', "", name)
    return cleaned.strip() or "Unknown"


_SEASON_FOLDER_RE = re.compile(r"^(?:season[\s._-]*)?0*(\d{1,2})$", re.I)
_SEASON_SHORT_RE = re.compile(r"^s0*(\d{1,2})$", re.I)
_SEASON_CN_RE = re.compile(r"第([零一二三四五六七八九十\d]+)季")
_CN_NUM = {
    "零": 0,
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def _chinese_digit(token: str) -> int | None:
    if token.isdigit():
        return int(token)
    if token == "十":
        return 10
    if len(token) == 2 and token[0] == "十" and token[1] in _CN_NUM:
        return 10 + _CN_NUM[token[1]]
    if len(token) == 2 and token[0] in _CN_NUM and token[1] == "十":
        return _CN_NUM[token[0]] * 10
    if len(token) == 3 and token[1] == "十":
        tens = _CN_NUM.get(token[0])
        ones = _CN_NUM.get(token[2])
        if tens is not None and ones is not None:
            return tens * 10 + ones
    if token in _CN_NUM:
        return _CN_NUM[token]
    return None


def parse_season_from_folder_name(name: str) -> int | None:
    text = name.strip()
    m = _SEASON_SHORT_RE.match(text)
    if m:
        return int(m.group(1))
    m = _SEASON_FOLDER_RE.match(text)
    if m:
        return int(m.group(1))
    m = _SEASON_CN_RE.search(text)
    if m:
        return _chinese_digit(m.group(1))
    return None


def is_season_only_folder_name(name: str) -> bool:
    text = name.strip()
    if _SEASON_SHORT_RE.match(text):
        return True
    if _SEASON_FOLDER_RE.match(text):
        return True
    return False


def strip_season_label(name: str) -> str:
    cleaned = _SEASON_CN_RE.sub("", name)
    cleaned = re.sub(r"(?i)\bseason[\s._-]*\d+\b", "", cleaned)
    cleaned = re.sub(r"(?i)\bs\d{1,2}\b", "", cleaned)
    return cleaned.strip(" .-_")


def _normalize_title_key(text: str) -> str:
    return re.sub(r"[\s\-_.]+", "", text.lower())


def titles_share_series_name(a: str, b: str) -> bool:
    left = _normalize_title_key(a)
    right = _normalize_title_key(b)
    if not left or not right:
        return False
    if left == right or left in right or right in left:
        return True
    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    return len(shorter) >= 2 and longer.startswith(shorter)


@dataclass
class TvSeriesContext:
    series_title: str | None
    season_hint: int | None


def infer_tv_series_context(
    full_path: Path, source_root: Path, parsed: ParsedMedia
) -> TvSeriesContext:
    """从目录结构推断剧集名与季号，多季子目录归入同一剧集。"""
    if parsed.media_type != "tv":
        return TvSeriesContext(parsed.title, parsed.season)

    try:
        rel = full_path.parent.resolve().relative_to(source_root.resolve())
    except ValueError:
        return TvSeriesContext(parsed.title, parsed.season)

    parts = rel.parts
    if not parts:
        return TvSeriesContext(parsed.title, parsed.season)

    parent = parts[-1]
    season_in_folder = parse_season_from_folder_name(parent)

    if is_season_only_folder_name(parent) and len(parts) >= 2:
        return TvSeriesContext(parts[-2], season_in_folder)

    if season_in_folder is not None and "第" in parent and "季" in parent:
        base = strip_season_label(parent)
        if len(parts) >= 2 and titles_share_series_name(parts[-2], base):
            return TvSeriesContext(parts[-2], season_in_folder)
        if base:
            return TvSeriesContext(base, season_in_folder)

    return TvSeriesContext(parent, parsed.season)


def resolve_tv_grouping(
    full_path: Path, source_root: Path, parsed: ParsedMedia
) -> tuple[str | None, int | None]:
    ctx = infer_tv_series_context(full_path, source_root, parsed)
    title = ctx.series_title or parsed.title
    if parsed.season is not None:
        season = parsed.season
    else:
        season = ctx.season_hint
    return title, season


def series_directory_for_path(full_path: Path, source_root: Path) -> Path | None:
    """返回源目录中该剧集对应的根文件夹（多季共享同一目录）。"""
    try:
        rel = full_path.parent.resolve().relative_to(source_root.resolve())
    except ValueError:
        return None

    parts = rel.parts
    if not parts:
        return None

    parent = parts[-1]
    season_in_folder = parse_season_from_folder_name(parent)
    if is_season_only_folder_name(parent) or (
        season_in_folder is not None and "第" in parent and "季" in parent
    ):
        series_parts = parts[:-1]
    else:
        series_parts = parts

    if not series_parts:
        return None
    return source_root.joinpath(*series_parts)
