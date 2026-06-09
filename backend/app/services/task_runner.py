from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import (
    MediaItem,
    ScrapeStatus,
    Task,
    TaskRun,
    TaskRunStatus,
    TaskType,
)
from app.services.matcher import auto_match_pending, backfill_matched_tv_metadata
from app.services.organizer import organize_media_items
from app.services.scanner import scan_directory
from app.services.scraper import scrape_pending_media
from app.services.series_identity import (
    cleanup_orphan_movie_media,
    cleanup_orphan_tv_media,
    consolidate_by_series_scope,
    consolidate_movie_media_by_tmdb,
    consolidate_tv_media_by_tmdb,
)

logger = logging.getLogger(__name__)


def recover_stale_task_runs() -> int:
    """服务重启后，后台线程已消失但数据库仍可能停留在 running。"""
    db = SessionLocal()
    try:
        stale = (
            db.query(TaskRun)
            .filter(
                TaskRun.status == TaskRunStatus.RUNNING,
                TaskRun.finished_at.is_(None),
            )
            .all()
        )
        now = datetime.now(timezone.utc)
        for run in stale:
            run.status = TaskRunStatus.FAILED
            suffix = "服务重启导致任务中断，请重新运行"
            run.message = f"{run.message}; {suffix}" if run.message else suffix
            run.finished_at = now
        if stale:
            db.commit()
        return len(stale)
    finally:
        db.close()


def has_active_task_run(db: Session, task_id: str) -> bool:
    return (
        db.query(TaskRun)
        .filter(TaskRun.task_id == task_id, TaskRun.status == TaskRunStatus.RUNNING)
        .first()
        is not None
    )


def _append_progress(db: Session, run: TaskRun, messages: list[str], step: str) -> None:
    messages.append(step)
    run.message = "; ".join(messages)
    db.commit()


def run_task(task_id: str) -> TaskRun:
    db = SessionLocal()
    run = TaskRun(task_id=task_id, status=TaskRunStatus.RUNNING)
    db.add(run)
    db.commit()
    db.refresh(run)

    run.started_at = datetime.now(timezone.utc)
    run.message = "任务已启动…"
    db.commit()

    try:
        task = db.get(Task, task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")

        messages: list[str] = []
        link_preference = (task.config or {}).get("link_type", "auto")

        if task.task_type in {
            TaskType.SCAN_ONLY,
            TaskType.ORGANIZE_ONLY,
            TaskType.SCRAPE_INCREMENTAL,
            TaskType.SCRAPE_FULL,
        }:
            _append_progress(db, run, messages, "正在扫描源目录…")
            scan_stats = scan_directory(db, task.source_path)
            _append_progress(db, run, messages, f"scan: {scan_stats}")
            if scan_stats.get("path_missing"):
                raise FileNotFoundError(
                    f"源目录不存在: {task.source_path}。"
                    f"请填写本机实际路径（当前环境源目录根: 见系统设置）"
                )

        if task.task_type in {
            TaskType.ORGANIZE_ONLY,
            TaskType.SCRAPE_INCREMENTAL,
            TaskType.SCRAPE_FULL,
        }:
            _append_progress(db, run, messages, "正在匹配与归组…")
            match_stats = auto_match_pending(db)
            _append_progress(db, run, messages, f"match: {match_stats}")

            scope_stats = consolidate_by_series_scope(db, task.source_path)
            if scope_stats.get("reassigned"):
                _append_progress(db, run, messages, f"scope: {scope_stats}")

            merge_stats = consolidate_tv_media_by_tmdb(db)
            movie_merge_stats = consolidate_movie_media_by_tmdb(db)
            merged_total = merge_stats.get("merged", 0) + movie_merge_stats.get("merged", 0)
            if merged_total:
                _append_progress(
                    db,
                    run,
                    messages,
                    f"tmdb_merge: {{'merged': {merged_total}}}",
                )

            cleanup_stats = cleanup_orphan_tv_media(db)
            movie_cleanup_stats = cleanup_orphan_movie_media(db)
            removed_total = cleanup_stats.get("removed", 0) + movie_cleanup_stats.get(
                "removed", 0
            )
            if removed_total:
                _append_progress(
                    db,
                    run,
                    messages,
                    f"cleanup: {{'removed': {removed_total}}}",
                )

            meta_stats = backfill_matched_tv_metadata(db)
            if meta_stats.get("year_filled"):
                _append_progress(db, run, messages, f"metadata: {meta_stats}")

            db.commit()

            matched_ids = [
                m.id
                for m in db.query(MediaItem)
                .filter(MediaItem.tmdb_id.isnot(None))
                .all()
                if m.source_files
            ]
            _append_progress(db, run, messages, "正在整理到影视库…")
            org_stats = organize_media_items(
                db,
                task.library_path,
                link_preference=link_preference,
                media_item_ids=matched_ids or None,
            )
            _append_progress(db, run, messages, f"organize: {org_stats}")

        if task.task_type in {TaskType.SCRAPE_INCREMENTAL, TaskType.SCRAPE_FULL}:
            force = task.task_type == TaskType.SCRAPE_FULL
            _append_progress(db, run, messages, "正在刮削元数据…")
            scrape_stats = scrape_pending_media(db, task, force=force)
            _append_progress(db, run, messages, f"scrape: {scrape_stats}")

        run.status = TaskRunStatus.SUCCESS
        run.message = "; ".join(messages)
    except Exception as exc:
        logger.exception("Task run failed: %s", task_id)
        run.status = TaskRunStatus.FAILED
        run.message = str(exc)
    finally:
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(run)
        run_id = run.id
        db.close()

    db2 = SessionLocal()
    result = db2.get(TaskRun, run_id)
    db2.close()
    return result


def run_task_safe(task_id: str) -> None:
    try:
        run_task(task_id)
    except Exception:
        logger.exception("Unhandled task error: %s", task_id)
