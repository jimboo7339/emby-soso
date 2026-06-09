from __future__ import annotations

from typing import Any


def image_language_base(language: str) -> str | None:
    """TMDB 图片 iso_639_1 只有语言码（如 zh），不含地区（zh-CN）。"""
    lang = (language or "").strip()
    if not lang:
        return None
    base = lang.split("-", 1)[0].lower()
    return base or None


def image_language_prefs(language: str) -> tuple[str | None, ...]:
    """按优先级返回 TMDB 图片语言匹配顺序。"""
    base = image_language_base(language)
    prefs: list[str | None] = []
    for code in (base, "en", None):
        if code not in prefs:
            prefs.append(code)
    return tuple(prefs)


def include_image_languages(language: str) -> str:
    """构建 TMDB include_image_language 参数。"""
    lang = (language or "").strip()
    base = image_language_base(language)
    parts: list[str] = []
    for code in (lang, base, "en", "null"):
        if code and code not in parts:
            parts.append(code)
    return ",".join(parts)


def pick_image(images: dict[str, Any], kind: str, language: str) -> str | None:
    items = images.get(kind) or []
    if not items:
        return None

    for lang in image_language_prefs(language):
        matched = [
            item
            for item in items
            if (lang is None and item.get("iso_639_1") is None)
            or item.get("iso_639_1") == lang
        ]
        if not matched:
            continue
        best = max(matched, key=lambda x: x.get("vote_average") or 0)
        path = best.get("file_path")
        if path:
            return path

    return items[0].get("file_path")
