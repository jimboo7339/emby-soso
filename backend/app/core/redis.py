from __future__ import annotations

import json
import logging
from typing import Any

import redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_redis_client: redis.Redis | None = None
_memory_cache: dict[str, str] = {}


def get_redis_client() -> redis.Redis | None:
    global _redis_client
    if not settings.redis_active:
        return None
    if _redis_client is None:
        _redis_client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
    return _redis_client


def cache_get(key: str) -> Any | None:
    client = get_redis_client()
    if client:
        raw = client.get(key)
        return json.loads(raw) if raw else None
    raw = _memory_cache.get(key)
    return json.loads(raw) if raw else None


def cache_set(key: str, value: Any, ttl_seconds: int = 3600) -> None:
    payload = json.dumps(value, ensure_ascii=False)
    client = get_redis_client()
    if client:
        client.setex(key, ttl_seconds, payload)
        return
    _memory_cache[key] = payload


def cache_delete(key: str) -> None:
    client = get_redis_client()
    if client:
        client.delete(key)
        return
    _memory_cache.pop(key, None)


def ping_redis() -> bool:
    client = get_redis_client()
    if not client:
        return False
    try:
        return bool(client.ping())
    except redis.RedisError:
        logger.exception("Redis ping failed")
        return False
