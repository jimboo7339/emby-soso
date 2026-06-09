from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import (
    FileStatus,
    MediaItem,
    ScrapeStatus,
    SourceFile,
    Task,
)
from app.schemas import DashboardStats

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
def dashboard_stats(db: Session = Depends(get_db)) -> DashboardStats:
    total_media = db.query(func.count(MediaItem.id)).scalar() or 0
    complete = (
        db.query(func.count(MediaItem.id))
        .filter(MediaItem.scrape_status == ScrapeStatus.COMPLETE)
        .scalar()
        or 0
    )
    partial = (
        db.query(func.count(MediaItem.id))
        .filter(MediaItem.scrape_status == ScrapeStatus.PARTIAL)
        .scalar()
        or 0
    )
    pending = (
        db.query(func.count(MediaItem.id))
        .filter(MediaItem.scrape_status == ScrapeStatus.PENDING)
        .scalar()
        or 0
    )
    failed = (
        db.query(func.count(MediaItem.id))
        .filter(MediaItem.scrape_status == ScrapeStatus.FAILED)
        .scalar()
        or 0
    )
    needs_manual = (
        db.query(func.count(MediaItem.id))
        .filter(MediaItem.scrape_status == ScrapeStatus.NEEDS_MANUAL_MATCH)
        .scalar()
        or 0
    )
    total_files = db.query(func.count(SourceFile.id)).scalar() or 0
    linked_files = (
        db.query(func.count(SourceFile.id))
        .filter(SourceFile.file_status == FileStatus.LINKED)
        .scalar()
        or 0
    )
    total_tasks = db.query(func.count(Task.id)).scalar() or 0
    enabled_tasks = (
        db.query(func.count(Task.id)).filter(Task.enabled.is_(True)).scalar() or 0
    )

    return DashboardStats(
        total_media=total_media,
        complete=complete,
        partial=partial,
        pending=pending,
        failed=failed,
        needs_manual_match=needs_manual,
        total_files=total_files,
        linked_files=linked_files,
        total_tasks=total_tasks,
        enabled_tasks=enabled_tasks,
    )
