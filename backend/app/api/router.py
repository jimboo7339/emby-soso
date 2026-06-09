import threading
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.core.database import get_db
from app.core.scheduler import reload_task_schedules
from app.models import (
    MediaItem,
    ScrapeStatus,
    SourceFile,
    Task,
    TaskRun,
)
from app.schemas import (
    ManualMatchRequest,
    MatchContextResponse,
    MediaDetailResponse,
    MediaItemSummary,
    MediaListResponse,
    LibraryCleanupResponse,
    MediaResetResponse,
    OrganizeResponse,
    EpisodeDetailResponse,
    ScrapeFieldStatusItem,
    SourceFileItem,
    TaskCreate,
    TaskResponse,
    TaskRunResponse,
    TaskUpdate,
    TmdbSearchResult,
)
from app.services.library_cleanup import (
    remove_media_file_from_library,
    remove_media_from_library,
    reorganize_media,
    reset_media_item,
)
from app.services.matcher import apply_manual_match
from app.services.scrape_config import resolve_scrape_options, TV_ONLY_SCRAPE_FIELDS
from app.services.scraper import (
    deduped_scrape_fields,
    refresh_media_scrape_status,
    refresh_media_scrape_status_batch,
    scrape_media_item,
)
from app.services.series_identity import gather_tmdb_search_queries
from app.services.task_runner import has_active_task_run, recover_stale_task_runs, run_task, run_task_safe
from app.services.tmdb_client import TmdbClient
from app.services.parser import read_strm_target
from app.services.library_paths import (
    effective_library_file_path,
    resolve_library_root_for_media,
)
from app.services.nfo_writer import (
    episode_nfo_path,
    episode_thumb_path,
    read_episode_nfo,
    read_episode_title,
)

router = APIRouter(tags=["resources"])


def _source_file_item(
    sf: SourceFile, media: MediaItem, library_root: str
) -> SourceFileItem:
    path = Path(sf.source_path)
    is_strm = path.suffix.lower() == ".strm"
    lib_file = effective_library_file_path(sf, media, library_root)
    lib_path_str = str(lib_file) if lib_file else None
    nfo_path = episode_nfo_path(lib_path_str) if lib_path_str else None
    thumb_path = episode_thumb_path(lib_path_str) if lib_path_str else None
    return SourceFileItem(
        id=sf.id,
        source_path=sf.source_path,
        library_path=lib_path_str or sf.library_path,
        link_type=sf.link_type.value if sf.link_type else None,
        file_status=sf.file_status.value,
        parsed_title=sf.parsed_title,
        parsed_season=sf.parsed_season,
        parsed_episode=sf.parsed_episode,
        error_message=sf.error_message,
        is_strm=is_strm,
        strm_target=read_strm_target(path) if is_strm else None,
        episode_title=read_episode_title(lib_path_str),
        has_nfo=bool(nfo_path and nfo_path.exists()),
        has_thumb=bool(thumb_path and thumb_path.exists()),
    )


@router.get("/tasks", response_model=list[TaskResponse])
def list_tasks(db: Session = Depends(get_db)) -> list[Task]:
    return db.query(Task).order_by(Task.created_at.desc()).all()


@router.post("/tasks", response_model=TaskResponse)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)) -> Task:
    task = Task(
        name=payload.name,
        source_path=payload.source_path,
        library_path=payload.library_path,
        cron_expr=payload.cron_expr,
        task_type=payload.task_type,
        enabled=payload.enabled,
        use_global_scrape_config=payload.use_global_scrape_config,
        scrape_options=(
            payload.scrape_options.model_dump() if payload.scrape_options else None
        ),
        config=payload.config,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    reload_task_schedules()
    return task


@router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: str, db: Session = Depends(get_db)) -> Task:
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.put("/tasks/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: str, payload: TaskUpdate, db: Session = Depends(get_db)
) -> Task:
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    data = payload.model_dump(exclude_unset=True)
    scrape_options = data.pop("scrape_options", None)
    if scrape_options is not None:
        task.scrape_options = scrape_options

    for key, value in data.items():
        setattr(task, key, value)

    db.commit()
    db.refresh(task)
    reload_task_schedules()
    return task


@router.delete("/tasks/{task_id}")
def delete_task(task_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(task)
    db.commit()
    reload_task_schedules()
    return {"status": "deleted"}


@router.post("/tasks/{task_id}/run")
def run_task_now(task_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if has_active_task_run(db, task_id):
        raise HTTPException(status_code=409, detail="该任务正在运行中，请稍后再试")
    threading.Thread(target=run_task_safe, args=(task_id,), daemon=True).start()
    return {"status": "started", "task_id": task_id}


@router.post("/tasks/{task_id}/run/sync", response_model=TaskRunResponse)
def run_task_sync(task_id: str, db: Session = Depends(get_db)) -> TaskRun:
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if has_active_task_run(db, task_id):
        raise HTTPException(status_code=409, detail="该任务正在运行中，请稍后再试")
    return run_task(task_id)


@router.get("/tasks/{task_id}/runs", response_model=list[TaskRunResponse])
def list_task_runs(task_id: str, db: Session = Depends(get_db)) -> list[TaskRun]:
    return (
        db.query(TaskRun)
        .filter(TaskRun.task_id == task_id)
        .order_by(TaskRun.created_at.desc())
        .limit(20)
        .all()
    )


def _extract_genres(media: MediaItem) -> list[str]:
    genres: list[str] = []
    metadata = media.metadata_json or {}
    for entry in metadata.get("genres") or []:
        if isinstance(entry, dict):
            name = entry.get("name")
            if name:
                genres.append(str(name))
        elif isinstance(entry, str):
            genres.append(entry)
    return genres


def _media_item_summary(media: MediaItem) -> MediaItemSummary:
    return MediaItemSummary(
        id=media.id,
        media_type=media.media_type.value,
        title=media.title,
        year=media.year,
        poster_path=media.poster_path,
        backdrop_path=media.backdrop_path,
        overview=media.overview,
        genres=_extract_genres(media),
        scrape_status=media.scrape_status.value,
        match_status=media.match_status.value,
        tmdb_id=media.tmdb_id,
    )


@router.get("/media", response_model=MediaListResponse)
def list_media(
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    scrape_status: str | None = None,
    media_type: str | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
) -> MediaListResponse:
    query = db.query(MediaItem)
    if scrape_status:
        query = query.filter(MediaItem.scrape_status == scrape_status)
    if media_type:
        query = query.filter(MediaItem.media_type == media_type)
    if q:
        pattern = f"%{q.lower()}%"
        query = query.filter(
            func.lower(MediaItem.title).like(pattern)
            | func.lower(func.coalesce(MediaItem.original_title, "")).like(pattern)
        )

    total = query.count()
    items = (
        query.order_by(MediaItem.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    refresh_media_scrape_status_batch(db, items)

    return MediaListResponse(
        items=[_media_item_summary(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


def _build_media_detail(media: MediaItem, db: Session) -> MediaDetailResponse:
    library_root = resolve_library_root_for_media(db, media)
    refresh_media_scrape_status(db, media)
    fields = deduped_scrape_fields(media)
    if media.media_type.value == "movie":
        fields = [f for f in fields if f.field_key not in TV_ONLY_SCRAPE_FIELDS]
    return MediaDetailResponse(
        id=media.id,
        media_type=media.media_type.value,
        title=media.title,
        original_title=media.original_title,
        year=media.year,
        overview=media.overview,
        poster_path=media.poster_path,
        backdrop_path=media.backdrop_path,
        logo_path=media.logo_path,
        tmdb_id=media.tmdb_id,
        scrape_status=media.scrape_status.value,
        match_status=media.match_status.value,
        match_confidence=media.match_confidence,
        metadata_json=media.metadata_json or {},
        scrape_fields=[
            ScrapeFieldStatusItem(
                field_key=f.field_key,
                status=f.status.value,
                error_message=f.error_message,
            )
            for f in fields
        ],
        source_files=[_source_file_item(sf, media, library_root) for sf in media.source_files],
        last_scraped_at=media.last_scraped_at,
        created_at=media.created_at,
        updated_at=media.updated_at,
    )


@router.get("/media/{media_id}", response_model=MediaDetailResponse)
def get_media(media_id: str, db: Session = Depends(get_db)) -> MediaDetailResponse:
    media = (
        db.query(MediaItem)
        .options(
            joinedload(MediaItem.scrape_fields),
            joinedload(MediaItem.source_files),
        )
        .filter(MediaItem.id == media_id)
        .first()
    )
    if not media:
        raise HTTPException(status_code=404, detail="Media item not found")
    return _build_media_detail(media, db)


@router.get("/media/{media_id}/match-context", response_model=MatchContextResponse)
def get_match_context(
    media_id: str, db: Session = Depends(get_db)
) -> MatchContextResponse:
    media = (
        db.query(MediaItem)
        .options(joinedload(MediaItem.source_files))
        .filter(MediaItem.id == media_id)
        .first()
    )
    if not media:
        raise HTTPException(status_code=404, detail="Media item not found")

    reason = None
    if media.scrape_status == ScrapeStatus.NEEDS_MANUAL_MATCH:
        if not media.tmdb_id:
            reason = "自动匹配失败或未找到 TMDB 结果"
        else:
            reason = "需要人工确认匹配"
    elif not media.tmdb_id:
        reason = "尚未匹配 TMDB"

    suggested = media.title
    queries = gather_tmdb_search_queries(media)
    if queries:
        suggested = queries[0]
    elif not suggested and media.source_files:
        suggested = media.source_files[0].parsed_title or ""

    library_root = resolve_library_root_for_media(db, media)

    return MatchContextResponse(
        media_id=media.id,
        title=media.title,
        year=media.year,
        media_type=media.media_type.value,
        scrape_status=media.scrape_status.value,
        match_confidence=media.match_confidence,
        source_files=[
            _source_file_item(sf, media, library_root) for sf in media.source_files
        ],
        suggested_query=suggested or "",
        failure_reason=reason,
    )


@router.get(
    "/media/{media_id}/files/{source_file_id}/episode",
    response_model=EpisodeDetailResponse,
)
def get_episode_detail(
    media_id: str,
    source_file_id: str,
    db: Session = Depends(get_db),
) -> EpisodeDetailResponse:
    sf = (
        db.query(SourceFile)
        .filter(SourceFile.id == source_file_id, SourceFile.media_item_id == media_id)
        .first()
    )
    if not sf:
        raise HTTPException(status_code=404, detail="Source file not found")

    media = db.get(MediaItem, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media item not found")

    library_root = resolve_library_root_for_media(db, media)
    lib_file = effective_library_file_path(sf, media, library_root)
    lib_path_str = str(lib_file) if lib_file else None

    nfo = read_episode_nfo(lib_path_str)
    path = Path(sf.source_path)
    is_strm = path.suffix.lower() == ".strm"
    thumb_path = episode_thumb_path(lib_path_str) if lib_path_str else None
    has_thumb = bool(thumb_path and thumb_path.exists())
    nfo_path = episode_nfo_path(lib_path_str) if lib_path_str else None

    return EpisodeDetailResponse(
        source_file_id=sf.id,
        season_number=sf.parsed_season or 1,
        episode_number=sf.parsed_episode or 1,
        title=nfo.get("title") or sf.parsed_title,
        overview=nfo.get("overview"),
        air_date=nfo.get("air_date"),
        has_nfo=bool(nfo_path and nfo_path.exists()),
        has_thumb=has_thumb,
        thumb_url=f"/api/v1/media/{media_id}/files/{source_file_id}/thumb"
        if has_thumb
        else None,
        source_path=sf.source_path,
        library_path=lib_path_str or sf.library_path,
        file_status=sf.file_status.value,
        is_strm=is_strm,
        strm_target=read_strm_target(path) if is_strm else None,
    )


@router.get("/media/{media_id}/files/{source_file_id}/thumb")
def get_episode_thumb(
    media_id: str,
    source_file_id: str,
    db: Session = Depends(get_db),
) -> FileResponse:
    sf = (
        db.query(SourceFile)
        .filter(SourceFile.id == source_file_id, SourceFile.media_item_id == media_id)
        .first()
    )
    if not sf or not sf.media_item_id:
        raise HTTPException(status_code=404, detail="Thumb not found")

    media = db.get(MediaItem, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Thumb not found")

    library_root = resolve_library_root_for_media(db, media)
    lib_file = effective_library_file_path(sf, media, library_root)
    if not lib_file:
        raise HTTPException(status_code=404, detail="Thumb not found")

    thumb = episode_thumb_path(str(lib_file))
    if not thumb.exists():
        raise HTTPException(status_code=404, detail="Thumb not found")
    return FileResponse(thumb, media_type="image/jpeg")


@router.post("/media/{media_id}/scrape", response_model=MediaDetailResponse)
def scrape_media(
    media_id: str,
    force: bool = Query(False),
    db: Session = Depends(get_db),
) -> MediaDetailResponse:
    media = db.get(MediaItem, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media item not found")

    enabled = resolve_scrape_options(db, use_global=True)
    library_root = resolve_library_root_for_media(db, media)
    scrape_media_item(
        db,
        media,
        enabled_fields=enabled,
        force=force,
        library_root=library_root,
    )
    db.refresh(media)
    media = (
        db.query(MediaItem)
        .options(
            joinedload(MediaItem.scrape_fields),
            joinedload(MediaItem.source_files),
        )
        .filter(MediaItem.id == media_id)
        .first()
    )
    return _build_media_detail(media, db)


@router.delete("/media/{media_id}/library", response_model=LibraryCleanupResponse)
def delete_media_library(
    media_id: str, db: Session = Depends(get_db)
) -> LibraryCleanupResponse:
    media = (
        db.query(MediaItem)
        .options(joinedload(MediaItem.source_files))
        .filter(MediaItem.id == media_id)
        .first()
    )
    if not media:
        raise HTTPException(status_code=404, detail="Media item not found")

    library_root = resolve_library_root_for_media(db, media)
    try:
        stats = remove_media_from_library(db, media, library_root=library_root)
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if stats["errors"]:
        raise HTTPException(
            status_code=500,
            detail=f"部分库内文件删除失败（{stats['errors']} 个）",
        )
    return LibraryCleanupResponse(**stats)


@router.delete("/media/{media_id}", response_model=MediaResetResponse)
def reset_media(
    media_id: str, db: Session = Depends(get_db)
) -> MediaResetResponse:
    media = (
        db.query(MediaItem)
        .options(joinedload(MediaItem.source_files))
        .filter(MediaItem.id == media_id)
        .first()
    )
    if not media:
        raise HTTPException(status_code=404, detail="Media item not found")

    library_root = resolve_library_root_for_media(db, media)
    try:
        result = reset_media_item(db, media, library_root=library_root)
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return MediaResetResponse(
        library_folders_removed=int(result["library_folders_removed"]),
        media_deleted=bool(result["media_deleted"]),
        removed_paths=list(result.get("removed_paths") or []),
        related_media_reset=int(result.get("related_media_reset") or 1),
    )


@router.delete(
    "/media/{media_id}/library/files/{source_file_id}",
    response_model=LibraryCleanupResponse,
)
def delete_source_file_library(
    media_id: str,
    source_file_id: str,
    db: Session = Depends(get_db),
) -> LibraryCleanupResponse:
    media = (
        db.query(MediaItem)
        .options(joinedload(MediaItem.source_files))
        .filter(MediaItem.id == media_id)
        .first()
    )
    if not media:
        raise HTTPException(status_code=404, detail="Media item not found")

    library_root = resolve_library_root_for_media(db, media)
    try:
        stats = remove_media_file_from_library(
            db, media_id, source_file_id, library_root=library_root
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Source file not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return LibraryCleanupResponse(**stats)


@router.post("/media/{media_id}/reorganize", response_model=MediaDetailResponse)
def reorganize_media_item(
    media_id: str, db: Session = Depends(get_db)
) -> MediaDetailResponse:
    media = db.get(MediaItem, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media item not found")
    if not media.tmdb_id:
        raise HTTPException(
            status_code=400, detail="需要先匹配 TMDB 才能重新整理到影视库"
        )

    library_root = get_settings().data_library_root
    reorganize_media(db, media_id, library_root)

    media = (
        db.query(MediaItem)
        .options(
            joinedload(MediaItem.scrape_fields),
            joinedload(MediaItem.source_files),
        )
        .filter(MediaItem.id == media_id)
        .first()
    )
    return _build_media_detail(media, db)


@router.get("/tmdb/search", response_model=list[TmdbSearchResult])
async def tmdb_search(
    q: str = Query(..., min_length=1),
    media_type: str = Query("multi"),
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
) -> list[TmdbSearchResult]:
    client = TmdbClient.from_db(db)
    results = await client.search(q, media_type=media_type, page=page)
    mapped: list[TmdbSearchResult] = []

    for item in results:
        item_type = item.get("media_type") or media_type
        if item_type not in {"movie", "tv"}:
            continue

        title = item.get("title") or item.get("name") or ""
        original = item.get("original_title") or item.get("original_name")
        date = item.get("release_date") or item.get("first_air_date") or ""
        year = int(date[:4]) if len(date) >= 4 and date[:4].isdigit() else None

        mapped.append(
            TmdbSearchResult(
                tmdb_id=item.get("id"),
                media_type=item_type,
                title=title,
                original_title=original,
                year=year,
                overview=item.get("overview"),
                poster_path=item.get("poster_path"),
                vote_average=item.get("vote_average"),
            )
        )

    return mapped


@router.post("/media/{media_id}/manual-match", response_model=MediaDetailResponse)
def manual_match(
    media_id: str,
    payload: ManualMatchRequest,
    db: Session = Depends(get_db),
) -> MediaDetailResponse:
    media = db.get(MediaItem, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media item not found")

    apply_manual_match(
        db,
        media,
        tmdb_id=payload.tmdb_id,
        tmdb_type=payload.tmdb_type,
        note=payload.note,
    )
    db.commit()

    if payload.scrape_immediately:
        enabled = resolve_scrape_options(
            db,
            override=payload.scrape_options,
            use_global=True,
        )
        scrape_media_item(
            db,
            media,
            enabled_fields=enabled,
            force=True,
            library_root=resolve_library_root_for_media(db, media),
        )

    media = (
        db.query(MediaItem)
        .options(
            joinedload(MediaItem.scrape_fields),
            joinedload(MediaItem.source_files),
        )
        .filter(MediaItem.id == media_id)
        .first()
    )
    return _build_media_detail(media, db)
