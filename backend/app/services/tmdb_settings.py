from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import SystemSetting

TMDB_CONFIG_KEY = "tmdb_config"
DEFAULT_TMDB_BASE_URL = "https://api.themoviedb.org/3"
DEFAULT_SCRAPE_CONCURRENCY = 8
MIN_SCRAPE_CONCURRENCY = 1
MAX_SCRAPE_CONCURRENCY = 32


def normalize_scrape_concurrency(value: int | None) -> int:
    if value is None:
        return DEFAULT_SCRAPE_CONCURRENCY
    if isinstance(value, list):
        value = value[0] if value else None
    try:
        num = int(value)
    except (TypeError, ValueError):
        return DEFAULT_SCRAPE_CONCURRENCY
    return max(MIN_SCRAPE_CONCURRENCY, min(MAX_SCRAPE_CONCURRENCY, num))


def normalize_tmdb_base_url(base_url: str) -> str:
    """Ensure TMDB API v3 base URL ends with /3."""
    url = base_url.strip().rstrip("/")
    if not url:
        return DEFAULT_TMDB_BASE_URL
    if url.endswith("/3"):
        return url
    return f"{url}/3"


class TmdbRuntimeConfig(BaseModel):
    api_key: str = ""
    base_url: str = DEFAULT_TMDB_BASE_URL
    language: str = "zh-CN"
    scrape_concurrency: int = DEFAULT_SCRAPE_CONCURRENCY
    source: str = "env"  # env | db | mixed


def _load_db_values(db: Session) -> dict:
    row = db.query(SystemSetting).filter(SystemSetting.key == TMDB_CONFIG_KEY).first()
    if not row or not row.value:
        return {}
    return dict(row.value)


def get_tmdb_config(db: Session) -> TmdbRuntimeConfig:
    env = get_settings()
    db_vals = _load_db_values(db)

    api_key = db_vals.get("api_key") or env.tmdb_api_key or ""
    base_url = db_vals.get("base_url") or env.tmdb_base_url or DEFAULT_TMDB_BASE_URL
    language = db_vals.get("language") or env.tmdb_language or "zh-CN"
    scrape_concurrency = normalize_scrape_concurrency(db_vals.get("scrape_concurrency"))

    source = "db" if db_vals else "env"
    if db_vals and (env.tmdb_api_key or env.tmdb_base_url != DEFAULT_TMDB_BASE_URL):
        source = "mixed"

    return TmdbRuntimeConfig(
        api_key=api_key.strip(),
        base_url=normalize_tmdb_base_url(base_url),
        language=language,
        scrape_concurrency=scrape_concurrency,
        source=source,
    )


def save_tmdb_config(
    db: Session,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    language: str | None = None,
    scrape_concurrency: int | None = None,
) -> TmdbRuntimeConfig:
    row = db.query(SystemSetting).filter(SystemSetting.key == TMDB_CONFIG_KEY).first()
    payload = dict(row.value) if row and row.value else {}

    if api_key is not None:
        if api_key.strip():
            payload["api_key"] = api_key.strip()
        else:
            payload.pop("api_key", None)

    if base_url is not None:
        cleaned = normalize_tmdb_base_url(base_url.strip())
        if cleaned and cleaned != DEFAULT_TMDB_BASE_URL:
            payload["base_url"] = cleaned
        else:
            payload.pop("base_url", None)

    if language is not None:
        cleaned = language.strip()
        if cleaned:
            payload["language"] = cleaned
        else:
            payload.pop("language", None)

    if scrape_concurrency is not None:
        normalized = normalize_scrape_concurrency(scrape_concurrency)
        if normalized != DEFAULT_SCRAPE_CONCURRENCY:
            payload["scrape_concurrency"] = normalized
        else:
            payload.pop("scrape_concurrency", None)

    if payload:
        if row:
            row.value = payload
        else:
            row = SystemSetting(key=TMDB_CONFIG_KEY, value=payload)
            db.add(row)
    elif row:
        db.delete(row)

    db.commit()
    return get_tmdb_config(db)


def mask_api_key(api_key: str) -> str | None:
    if not api_key:
        return None
    if len(api_key) <= 4:
        return "****"
    return f"{'*' * min(len(api_key) - 4, 12)}{api_key[-4:]}"
