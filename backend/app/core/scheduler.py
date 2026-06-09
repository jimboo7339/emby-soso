from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import Task
from app.services.task_runner import run_task_safe

logger = logging.getLogger(__name__)
settings = get_settings()

scheduler = BackgroundScheduler()


def _parse_cron(cron_expr: str) -> CronTrigger:
    parts = cron_expr.split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression: {cron_expr}")
    minute, hour, day, month, day_of_week = parts
    return CronTrigger(
        minute=minute,
        hour=hour,
        day=day,
        month=month,
        day_of_week=day_of_week,
    )


def _schedule_task(task: Task) -> None:
    job_id = f"task_{task.id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    if not task.enabled:
        return

    try:
        trigger = _parse_cron(task.cron_expr)
    except ValueError:
        logger.exception("Invalid cron for task %s: %s", task.id, task.cron_expr)
        return

    scheduler.add_job(
        run_task_safe,
        trigger=trigger,
        id=job_id,
        args=[task.id],
        replace_existing=True,
    )
    logger.info("Scheduled task %s (%s)", task.name, task.cron_expr)


def reload_task_schedules() -> None:
    db = SessionLocal()
    try:
        tasks = db.query(Task).all()
        active_ids = {f"task_{t.id}" for t in tasks if t.enabled}
        for job in scheduler.get_jobs():
            if job.id.startswith("task_") and job.id not in active_ids:
                scheduler.remove_job(job.id)
        for task in tasks:
            _schedule_task(task)
    finally:
        db.close()


def start_scheduler() -> None:
    if not settings.scheduler_enabled:
        logger.info("Scheduler disabled")
        return

    scheduler.start()
    reload_task_schedules()
    logger.info("APScheduler started with %d jobs", len(scheduler.get_jobs()))


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped")
