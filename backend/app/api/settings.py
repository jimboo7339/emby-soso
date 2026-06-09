from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.schemas import SystemSettingsResponse, SystemSettingsUpdate
from app.services.app_settings import get_app_display_name, save_app_display_name
from app.services.scrape_config import get_global_scrape_config, save_global_scrape_config
from app.services.tmdb_settings import get_tmdb_config, mask_api_key, save_tmdb_config

router = APIRouter(prefix="/settings", tags=["settings"])
env_settings = get_settings()


def _build_settings_response(db: Session) -> SystemSettingsResponse:
    scrape_config = get_global_scrape_config(db)
    tmdb = get_tmdb_config(db)
    return SystemSettingsResponse(
        scrape_config=scrape_config,
        app_display_name=get_app_display_name(db),
        tmdb_api_key_set=bool(tmdb.api_key),
        tmdb_api_key_masked=mask_api_key(tmdb.api_key),
        tmdb_base_url=tmdb.base_url,
        tmdb_language=tmdb.language,
        tmdb_scrape_concurrency=tmdb.scrape_concurrency,
        tmdb_config_source=tmdb.source,
        data_source_root=env_settings.data_source_root,
        data_library_root=env_settings.data_library_root,
    )


@router.get("", response_model=SystemSettingsResponse)
def get_settings_api(db: Session = Depends(get_db)) -> SystemSettingsResponse:
    return _build_settings_response(db)


@router.put("", response_model=SystemSettingsResponse)
def update_settings_api(
    payload: SystemSettingsUpdate,
    db: Session = Depends(get_db),
) -> SystemSettingsResponse:
    if payload.scrape_config:
        save_global_scrape_config(db, payload.scrape_config)

    if payload.app_display_name is not None:
        save_app_display_name(db, payload.app_display_name)

    if (
        payload.tmdb_api_key is not None
        or payload.tmdb_base_url is not None
        or payload.tmdb_language is not None
        or payload.tmdb_scrape_concurrency is not None
    ):
        save_tmdb_config(
            db,
            api_key=payload.tmdb_api_key,
            base_url=payload.tmdb_base_url,
            language=payload.tmdb_language,
            scrape_concurrency=payload.tmdb_scrape_concurrency,
        )

    return _build_settings_response(db)
