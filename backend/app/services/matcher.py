from __future__ import annotations

import logging
from difflib import SequenceMatcher
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.models import (
    MatchHistory,
    MatchStatus,
    MediaItem,
    MediaType,
    ScrapeStatus,
)
from app.services.scrape_config import get_global_scrape_config
from app.services.series_identity import (
    consolidate_movie_media_by_tmdb,
    consolidate_tv_media_by_tmdb,
    gather_tmdb_search_queries,
)
from app.services.tmdb_client import TmdbClient

logger = logging.getLogger(__name__)


def _normalize(text: str) -> str:
    return "".join(ch.lower() for ch in text if ch.isalnum() or ch.isspace()).strip()


def _title_score(query: str, candidate: str) -> float:
    if not query or not candidate:
        return 0.0
    return SequenceMatcher(None, _normalize(query), _normalize(candidate)).ratio()


def _year_score(expected: int | None, candidate_year: int | None) -> float:
    if expected is None or candidate_year is None:
        return 0.5
    diff = abs(expected - candidate_year)
    if diff == 0:
        return 1.0
    if diff == 1:
        return 0.7
    return 0.0


def _extract_year(item: dict[str, Any]) -> int | None:
    date = item.get("release_date") or item.get("first_air_date") or ""
    if len(date) >= 4 and date[:4].isdigit():
        return int(date[:4])
    return None


def score_candidate(
    media: MediaItem,
    item: dict[str, Any],
    media_type: str,
    *,
    query: str | None = None,
) -> float:
    search_title = query or media.title
    item_title = item.get("title") or item.get("name") or ""
    original = item.get("original_title") or item.get("original_name") or ""

    title_scores = [
        _title_score(search_title, item_title),
        _title_score(search_title, original),
        _title_score(media.title, item_title),
        _title_score(media.title, original),
    ]
    year_score = _year_score(media.year, _extract_year(item))
    popularity = min(float(item.get("popularity") or 0) / 100.0, 0.1)

    return max(title_scores) * 0.7 + year_score * 0.25 + popularity


def _episode_validation_bonus(
    client: TmdbClient, tmdb_id: int, media: MediaItem
) -> float:
    """抽样验证 TMDB 上是否存在源文件中的季集，降低误匹配。"""
    samples: list[tuple[int, int]] = []
    for sf in media.source_files:
        if sf.parsed_season is None or sf.parsed_episode is None:
            continue
        pair = (sf.parsed_season, sf.parsed_episode)
        if pair not in samples:
            samples.append(pair)
        if len(samples) >= 4:
            break

    if not samples:
        return 0.0

    hits = 0
    for season, episode in samples:
        try:
            client._sync.get_episode(tmdb_id, season, episode)
            hits += 1
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            continue

    return (hits / len(samples)) * 0.2


def _search_tv_results(client: TmdbClient, media: MediaItem) -> list[dict[str, Any]]:
    seen: dict[int, dict[str, Any]] = {}
    for query in gather_tmdb_search_queries(media):
        for item in client.search_sync(query, media_type="tv"):
            tmdb_id = item.get("id")
            if tmdb_id is None:
                continue
            tid = int(tmdb_id)
            if tid not in seen:
                seen[tid] = item
    return list(seen.values())


def _search_movie_results(client: TmdbClient, media: MediaItem) -> list[dict[str, Any]]:
    seen: dict[int, dict[str, Any]] = {}
    for query in gather_tmdb_search_queries(media):
        for item in client.search_sync(query, media_type="movie"):
            tmdb_id = item.get("id")
            if tmdb_id is None:
                continue
            tid = int(tmdb_id)
            if tid not in seen:
                seen[tid] = item
    return list(seen.values())


def _pick_best(
    media: MediaItem,
    results: list[dict[str, Any]],
    media_type: str,
    *,
    client: TmdbClient | None = None,
) -> tuple[dict[str, Any] | None, float]:
    best_item: dict[str, Any] | None = None
    best_score = 0.0
    queries = gather_tmdb_search_queries(media)

    for item in results:
        item_type = item.get("media_type") or media_type
        if item_type != media_type:
            continue

        local_best = 0.0
        for query in queries:
            local_best = max(local_best, score_candidate(media, item, media_type, query=query))

        if media_type == "tv" and client and item.get("id"):
            local_best += _episode_validation_bonus(client, int(item["id"]), media)

        if local_best > best_score:
            best_score = local_best
            best_item = item
    return best_item, best_score


def auto_match_media(db: Session, media: MediaItem, client: TmdbClient | None = None) -> bool:
    config = get_global_scrape_config(db)
    if not config.match_options.auto_match_enabled:
        return False

    if media.tmdb_id and media.match_status in {MatchStatus.AUTO, MatchStatus.MANUAL}:
        return True

    if not media.title:
        media.scrape_status = ScrapeStatus.NEEDS_MANUAL_MATCH
        db.flush()
        return False

    client = client or TmdbClient.from_db(db)
    media_type = "movie" if media.media_type == MediaType.MOVIE else "tv"

    try:
        if media_type == "tv":
            results = _search_tv_results(client, media)
        else:
            results = _search_movie_results(client, media)
    except Exception:
        logger.exception("TMDB search failed for %s", media.title)
        media.scrape_status = ScrapeStatus.NEEDS_MANUAL_MATCH
        media.match_confidence = 0.0
        db.flush()
        return False

    if not results:
        media.scrape_status = ScrapeStatus.NEEDS_MANUAL_MATCH
        media.match_status = MatchStatus.UNMATCHED
        media.match_confidence = 0.0
        db.flush()
        return False

    best, score = _pick_best(media, results, media_type, client=client)
    threshold = config.match_options.confidence_threshold

    if not best or score < threshold:
        media.scrape_status = ScrapeStatus.NEEDS_MANUAL_MATCH
        media.match_status = MatchStatus.UNMATCHED
        media.match_confidence = score
        db.flush()
        return False

    media.tmdb_id = int(best["id"])
    media.match_status = MatchStatus.AUTO
    media.match_confidence = score
    media.scrape_status = ScrapeStatus.PENDING

    matched_year = _extract_year(best)
    if matched_year:
        media.year = matched_year
    matched_title = best.get("name") or best.get("title")
    if matched_title:
        media.title = str(matched_title).strip()
    original = best.get("original_name") or best.get("original_title")
    if original:
        media.original_title = str(original).strip()

    db.add(
        MatchHistory(
            media_item_id=media.id,
            tmdb_id=media.tmdb_id,
            tmdb_type=media_type,
            action="auto_match",
            note=f"confidence={score:.2f}",
        )
    )
    db.flush()
    return True


def consolidate_matched_tv(db: Session) -> dict[str, int]:
    return consolidate_tv_media_by_tmdb(db)


def backfill_matched_tv_metadata(db: Session) -> dict[str, int]:
    """已匹配但缺 metadata 的剧集在整理前从 TMDB 补全（尤其 year）。"""
    stats = {"year_filled": 0}
    client = TmdbClient.from_db(db)
    pending = (
        db.query(MediaItem)
        .filter(
            MediaItem.media_type == MediaType.TV,
            MediaItem.tmdb_id.isnot(None),
            MediaItem.year.is_(None),
        )
        .all()
    )
    for media in pending:
        try:
            detail = client.get_details_sync("tv", int(media.tmdb_id))
        except httpx.HTTPError:
            logger.exception("TMDB detail failed for TV %s (%s)", media.title, media.tmdb_id)
            continue
        date = detail.get("first_air_date") or ""
        if len(date) >= 4 and date[:4].isdigit():
            media.year = int(date[:4])
            stats["year_filled"] += 1
        name = detail.get("name")
        if name:
            media.title = str(name).strip()
        original = detail.get("original_name")
        if original:
            media.original_title = str(original).strip()
    if stats["year_filled"]:
        db.flush()
    return stats


def auto_match_pending(db: Session, media_item_ids: list[str] | None = None) -> dict[str, int]:
    stats = {"matched": 0, "needs_manual": 0, "skipped": 0}

    query = db.query(MediaItem).filter(
        MediaItem.tmdb_id.is_(None),
        MediaItem.title != "",
    )
    if media_item_ids:
        query = query.filter(MediaItem.id.in_(media_item_ids))

    client = TmdbClient.from_db(db)
    for media in query.all():
        # 仅跳过已有明确低置信度结果的；API 失败(confidence=0) 允许重试
        if (
            media.scrape_status == ScrapeStatus.NEEDS_MANUAL_MATCH
            and media.match_confidence
            and media.match_confidence > 0
        ):
            stats["skipped"] += 1
            continue
        if auto_match_media(db, media, client):
            stats["matched"] += 1
        else:
            stats["needs_manual"] += 1

    tv_merge_stats = consolidate_tv_media_by_tmdb(db)
    movie_merge_stats = consolidate_movie_media_by_tmdb(db)
    stats["merged"] = tv_merge_stats.get("merged", 0) + movie_merge_stats.get("merged", 0)

    db.commit()
    return stats


def apply_manual_match(
    db: Session,
    media: MediaItem,
    *,
    tmdb_id: int,
    tmdb_type: str,
    note: str | None = None,
    operator: str | None = None,
) -> None:
    from app.services.tmdb_client import TmdbClientSync

    media.tmdb_id = tmdb_id
    media.media_type = MediaType.MOVIE if tmdb_type == "movie" else MediaType.TV
    media.match_status = MatchStatus.MANUAL
    media.match_confidence = 1.0
    media.scrape_status = ScrapeStatus.PENDING

    try:
        details = TmdbClientSync.from_db(db).get_details(tmdb_type, tmdb_id)
        detail_title = details.get("name") or details.get("title")
        if detail_title:
            media.title = str(detail_title).strip()
        original = details.get("original_name") or details.get("original_title")
        if original:
            media.original_title = str(original).strip()
        detail_year = _extract_year(details)
        if detail_year:
            media.year = detail_year
    except Exception:
        logger.exception("Failed to fetch TMDB details for manual match %s", tmdb_id)

    from datetime import datetime, timezone

    media.manual_matched_at = datetime.now(timezone.utc)

    db.add(
        MatchHistory(
            media_item_id=media.id,
            tmdb_id=tmdb_id,
            tmdb_type=tmdb_type,
            action="manual_match",
            operator=operator,
            note=note,
        )
    )
    db.flush()
    if media.media_type == MediaType.TV:
        consolidate_tv_media_by_tmdb(db)
        db.flush()
