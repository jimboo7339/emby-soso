from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.redis import ping_redis
from app.core.scheduler import scheduler
from app.schemas import HealthResponse

router = APIRouter(tags=["health"])
settings = get_settings()


@router.get("/health", response_model=HealthResponse)
def health_check(db: Session = Depends(get_db)) -> HealthResponse:
    db_ok = False
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    if settings.redis_active:
        redis_status = "connected" if ping_redis() else "error"
        mode = "redis-enhanced"
    else:
        redis_status = "disabled"
        mode = "standalone"

    return HealthResponse(
        status="ok" if db_ok else "degraded",
        database="connected" if db_ok else "error",
        redis=redis_status,
        scheduler=scheduler.running,
        mode=mode,
    )
