from __future__ import annotations

import logging
from types import TracebackType
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.redis import cache_get, cache_set
from app.services.tmdb_images import include_image_languages
from app.services.tmdb_settings import get_tmdb_config

logger = logging.getLogger(__name__)


class TmdbClientSync:
    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.themoviedb.org/3",
        language: str = "zh-CN",
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.language = language
        self._http_client = http_client
        self._owns_client = http_client is None

    @classmethod
    def from_db(cls, db: Session) -> TmdbClientSync:
        cfg = get_tmdb_config(db)
        return cls(api_key=cfg.api_key, base_url=cfg.base_url, language=cfg.language)

    @property
    def http_client(self) -> httpx.Client:
        if self._http_client is None:
            self._http_client = httpx.Client(timeout=30.0, follow_redirects=True)
            self._owns_client = True
        return self._http_client

    def close(self) -> None:
        if self._owns_client and self._http_client is not None:
            self._http_client.close()
            self._http_client = None

    def __enter__(self) -> TmdbClientSync:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def _params(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"api_key": self.api_key, "language": self.language}
        if extra:
            params.update(extra)
        return params

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        cache_key = f"tmdb:{self.base_url}:{path}:{params}"
        cached = cache_get(cache_key)
        if cached:
            return cached

        url = f"{self.base_url}/{path.lstrip('/')}"
        response = self.http_client.get(url, params=self._params(params))
        response.raise_for_status()
        data = response.json()
        cache_set(cache_key, data, ttl_seconds=3600)
        return data

    def search_sync(
        self, query: str, media_type: str = "multi", page: int = 1
    ) -> list[dict[str, Any]]:
        if not self.api_key:
            return []
        endpoint = "search/multi"
        if media_type == "movie":
            endpoint = "search/movie"
        elif media_type == "tv":
            endpoint = "search/tv"
        data = self._get(endpoint, {"query": query, "page": page})
        return data.get("results", [])

    def get_details(self, media_type: str, tmdb_id: int) -> dict[str, Any]:
        append = "credits,external_ids,keywords,videos,images"
        return self._get(
            f"{media_type}/{tmdb_id}",
            {
                "append_to_response": append,
                "include_image_language": include_image_languages(self.language),
            },
        )

    def get_episode(self, tv_id: int, season: int, episode: int) -> dict[str, Any]:
        return self._get(f"tv/{tv_id}/season/{season}/episode/{episode}")

    def get_season(self, tv_id: int, season: int) -> dict[str, Any]:
        return self._get(f"tv/{tv_id}/season/{season}")

    def episodes_by_number(self, season_data: dict[str, Any]) -> dict[int, dict[str, Any]]:
        out: dict[int, dict[str, Any]] = {}
        for ep in season_data.get("episodes") or []:
            num = ep.get("episode_number")
            if num is not None:
                out[int(num)] = ep
        return out


class TmdbClient:
    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.themoviedb.org/3",
        language: str = "zh-CN",
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.language = language
        self._sync = TmdbClientSync(api_key, base_url, language)

    @classmethod
    def from_db(cls, db: Session) -> TmdbClient:
        cfg = get_tmdb_config(db)
        return cls(api_key=cfg.api_key, base_url=cfg.base_url, language=cfg.language)

    def _params(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"api_key": self.api_key, "language": self.language}
        if extra:
            params.update(extra)
        return params

    def search_sync(
        self, query: str, media_type: str = "multi", page: int = 1
    ) -> list[dict[str, Any]]:
        return self._sync.search_sync(query, media_type=media_type, page=page)

    async def search(
        self, query: str, media_type: str = "multi", page: int = 1
    ) -> list[dict[str, Any]]:
        if not self.api_key:
            return []

        endpoint = "search/multi"
        if media_type == "movie":
            endpoint = "search/movie"
        elif media_type == "tv":
            endpoint = "search/tv"

        cache_key = f"tmdb:async:{self.base_url}:{endpoint}:{query}:{media_type}:{page}"
        cached = cache_get(cache_key)
        if cached:
            return cached

        url = f"{self.base_url}/{endpoint}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                url, params=self._params({"query": query, "page": page})
            )
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            cache_set(cache_key, results, ttl_seconds=3600)
            return results

    async def get_details(self, media_type: str, tmdb_id: int) -> dict[str, Any]:
        return self._sync.get_details(media_type, tmdb_id)

    def get_details_sync(self, media_type: str, tmdb_id: int) -> dict[str, Any]:
        return self._sync.get_details(media_type, tmdb_id)
