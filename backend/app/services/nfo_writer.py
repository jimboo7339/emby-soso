from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import httpx

from app.models import MediaItem, MediaType, SourceFile
from app.services.tmdb_images import pick_image

logger = logging.getLogger(__name__)

TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"
ImageJob = tuple[str, Path]
DEFAULT_IMAGE_WORKERS = 8


def _escape(text: str | None) -> str:
    if not text:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _sub(parent: ET.Element, tag: str, text: str | None = None) -> ET.Element:
    node = ET.SubElement(parent, tag)
    if text is not None and text != "":
        node.text = str(text)
    return node


def _write_xml(root: ET.Element, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(root)
    if hasattr(ET, "indent"):
        ET.indent(tree, space="  ")
    tree.write(path, encoding="UTF-8", xml_declaration=True)


def _download_image(
    url: str,
    dest: Path,
    *,
    client: httpx.Client | None = None,
) -> bool:
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if client is not None:
            response = client.get(url)
            response.raise_for_status()
            dest.write_bytes(response.content)
            return True
        with httpx.Client(timeout=60.0, follow_redirects=True) as own_client:
            response = own_client.get(url)
            response.raise_for_status()
            dest.write_bytes(response.content)
        return True
    except Exception:
        logger.exception("Failed to download image: %s -> %s", url, dest)
        return False


def download_images_parallel(
    jobs: list[ImageJob],
    *,
    client: httpx.Client | None = None,
    max_workers: int = DEFAULT_IMAGE_WORKERS,
) -> dict[Path, bool]:
    """并发下载图片，复用同一 httpx 连接。"""
    if not jobs:
        return {}

    unique_jobs: list[ImageJob] = []
    seen: set[Path] = set()
    for url, dest in jobs:
        if dest in seen:
            continue
        seen.add(dest)
        unique_jobs.append((url, dest))

    results: dict[Path, bool] = {}
    if len(unique_jobs) == 1:
        url, dest = unique_jobs[0]
        results[dest] = _download_image(url, dest, client=client)
        return results

    own_client: httpx.Client | None = None
    active = client
    if active is None:
        own_client = httpx.Client(timeout=60.0, follow_redirects=True)
        active = own_client

    try:
        workers = min(max_workers, len(unique_jobs))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_download_image, url, dest, client=active): dest
                for url, dest in unique_jobs
            }
            for future in as_completed(futures):
                dest = futures[future]
                try:
                    results[dest] = future.result()
                except Exception:
                    logger.exception("Image download task failed: %s", dest)
                    results[dest] = False
    finally:
        if own_client is not None:
            own_client.close()

    return results


def tmdb_image_url(path: str | None, size: str = "original") -> str | None:
    if not path:
        return None
    if path.startswith("http"):
        return path
    return f"{TMDB_IMAGE_BASE}/{size}{path}"


def _should_write(path: Path, force: bool) -> bool:
    return force or not path.exists()


def show_folder_from_library_path(library_path: str) -> Path | None:
    path = Path(library_path)
    parent = path.parent
    if parent.name.lower().startswith("season"):
        return parent.parent
    return parent


def season_folder_from_library_path(library_path: str) -> Path:
    return Path(library_path).parent


def episode_nfo_path(library_path: str) -> Path:
    path = Path(library_path)
    return path.with_suffix(".nfo")


def episode_thumb_path(library_path: str) -> Path:
    path = Path(library_path)
    return path.parent / f"{path.stem}-thumb.jpg"


def movie_nfo_path(library_path: str) -> Path:
    return Path(library_path).with_suffix(".nfo")


def build_tvshow_nfo(details: dict[str, Any], tmdb_id: int) -> ET.Element:
    root = ET.Element("tvshow")
    _sub(root, "title", details.get("name"))
    _sub(root, "originaltitle", details.get("original_name"))
    _sub(root, "plot", details.get("overview"))
    date = details.get("first_air_date") or ""
    if len(date) >= 4:
        _sub(root, "year", date[:4])
    _sub(root, "premiered", date or None)
    _sub(root, "status", details.get("status"))
    if details.get("vote_average") is not None:
        _sub(root, "rating", str(details.get("vote_average")))

    uid = ET.SubElement(root, "uniqueid", {"type": "tmdb", "default": "true"})
    uid.text = str(tmdb_id)
    ext = details.get("external_ids") or {}
    if ext.get("imdb_id"):
        imdb = ET.SubElement(root, "uniqueid", {"type": "imdb"})
        imdb.text = ext["imdb_id"]
    if ext.get("tvdb_id"):
        tvdb = ET.SubElement(root, "uniqueid", {"type": "tvdb"})
        tvdb.text = str(ext["tvdb_id"])

    for genre in details.get("genres") or []:
        _sub(root, "genre", genre.get("name"))

    credits = details.get("credits") or {}
    for idx, actor in enumerate((credits.get("cast") or [])[:20]):
        actor_node = ET.SubElement(root, "actor")
        _sub(actor_node, "name", actor.get("name"))
        _sub(actor_node, "role", actor.get("character"))
        _sub(actor_node, "order", str(idx))
        if actor.get("profile_path"):
            _sub(actor_node, "thumb", tmdb_image_url(actor["profile_path"], "w185"))

    return root


def build_season_nfo(season_data: dict[str, Any], season_number: int) -> ET.Element:
    root = ET.Element("season")
    _sub(root, "seasonnumber", str(season_number))
    _sub(root, "title", season_data.get("name"))
    _sub(root, "plot", season_data.get("overview"))
    if season_data.get("id"):
        uid = ET.SubElement(root, "uniqueid", {"type": "tmdb", "default": "true"})
        uid.text = str(season_data["id"])
    return root


def build_episode_nfo(ep_data: dict[str, Any], season: int, episode: int) -> ET.Element:
    root = ET.Element("episodedetails")
    _sub(root, "title", ep_data.get("name"))
    _sub(root, "season", str(season))
    _sub(root, "episode", str(episode))
    _sub(root, "plot", ep_data.get("overview"))
    _sub(root, "aired", ep_data.get("air_date"))
    if ep_data.get("id"):
        uid = ET.SubElement(root, "uniqueid", {"type": "tmdb", "default": "true"})
        uid.text = str(ep_data["id"])
    if ep_data.get("runtime"):
        _sub(root, "runtime", str(ep_data["runtime"]))
    return root


def build_movie_nfo(details: dict[str, Any], tmdb_id: int) -> ET.Element:
    root = ET.Element("movie")
    _sub(root, "title", details.get("title"))
    _sub(root, "originaltitle", details.get("original_title"))
    _sub(root, "plot", details.get("overview"))
    date = details.get("release_date") or ""
    if len(date) >= 4:
        _sub(root, "year", date[:4])
    _sub(root, "premiered", date or None)
    if details.get("runtime"):
        _sub(root, "runtime", str(details["runtime"]))
    if details.get("vote_average") is not None:
        _sub(root, "rating", str(details.get("vote_average")))

    uid = ET.SubElement(root, "uniqueid", {"type": "tmdb", "default": "true"})
    uid.text = str(tmdb_id)
    ext = details.get("external_ids") or {}
    if ext.get("imdb_id"):
        imdb = ET.SubElement(root, "uniqueid", {"type": "imdb"})
        imdb.text = ext["imdb_id"]

    for genre in details.get("genres") or []:
        _sub(root, "genre", genre.get("name"))

    credits = details.get("credits") or {}
    for idx, actor in enumerate((credits.get("cast") or [])[:20]):
        actor_node = ET.SubElement(root, "actor")
        _sub(actor_node, "name", actor.get("name"))
        _sub(actor_node, "role", actor.get("character"))
        _sub(actor_node, "order", str(idx))
        if actor.get("profile_path"):
            _sub(actor_node, "thumb", tmdb_image_url(actor["profile_path"], "w185"))

    return root


def write_show_artwork(
    show_folder: Path,
    details: dict[str, Any],
    images: dict[str, Any],
    *,
    language: str,
    force: bool,
    enabled: dict[str, bool],
    http_client: httpx.Client | None = None,
    max_workers: int = DEFAULT_IMAGE_WORKERS,
) -> dict[str, bool]:
    results: dict[str, bool] = {}
    jobs: list[ImageJob] = []
    job_keys: dict[Path, str] = {}

    def queue_image(key: str, filename: str, path: str | None, size: str) -> None:
        if not enabled.get(key):
            return
        dest = show_folder / filename
        if not _should_write(dest, force):
            results[key] = True
            return
        url = tmdb_image_url(path, size)
        if not url:
            results[key] = False
            return
        jobs.append((url, dest))
        job_keys[dest] = key

    poster = details.get("poster_path") or pick_image(images, "posters", language)
    backdrop = details.get("backdrop_path") or pick_image(images, "backdrops", language)
    logo = pick_image(images, "logos", language)

    queue_image("poster", "poster.jpg", poster, "w500")
    queue_image("backdrop", "fanart.jpg", backdrop, "w1280")
    queue_image("logo", "clearlogo.png", logo, "w500")
    if enabled.get("backdrop") and backdrop:
        banner_dest = show_folder / "banner.jpg"
        if _should_write(banner_dest, force):
            url = tmdb_image_url(backdrop, "w780")
            if url:
                jobs.append((url, banner_dest))
                job_keys[banner_dest] = "banner"
            else:
                results["banner"] = False
        else:
            results["banner"] = True

    download_results = download_images_parallel(
        jobs, client=http_client, max_workers=max_workers
    )
    for dest, key in job_keys.items():
        results[key] = download_results.get(dest, False)

    return results


def write_movie_artwork(
    movie_folder: Path,
    details: dict[str, Any],
    images: dict[str, Any],
    *,
    language: str,
    force: bool,
    enabled: dict[str, bool],
    http_client: httpx.Client | None = None,
    max_workers: int = DEFAULT_IMAGE_WORKERS,
) -> dict[str, bool]:
    return write_show_artwork(
        movie_folder,
        details,
        images,
        language=language,
        force=force,
        enabled=enabled,
        http_client=http_client,
        max_workers=max_workers,
    )
def write_tvshow_nfo_file(
    show_folder: Path, details: dict[str, Any], tmdb_id: int, *, force: bool
) -> bool:
    dest = show_folder / "tvshow.nfo"
    if not _should_write(dest, force):
        return True
    show_folder.mkdir(parents=True, exist_ok=True)
    _write_xml(build_tvshow_nfo(details, tmdb_id), dest)
    return True


def write_movie_nfo_file(
    movie_folder: Path,
    library_path: str,
    details: dict[str, Any],
    tmdb_id: int,
    *,
    force: bool,
) -> bool:
    dest = movie_nfo_path(library_path)
    if not _should_write(dest, force):
        return True
    _write_xml(build_movie_nfo(details, tmdb_id), dest)
    return True


def write_season_nfo_file(
    season_folder: Path,
    season_data: dict[str, Any],
    season_number: int,
    *,
    force: bool,
) -> bool:
    dest = season_folder / "season.nfo"
    if not _should_write(dest, force):
        return True
    _write_xml(build_season_nfo(season_data, season_number), dest)
    return True


def write_season_poster(
    season_folder: Path,
    poster_path: str | None,
    season_number: int,
    *,
    force: bool,
    http_client: httpx.Client | None = None,
) -> bool:
    dest = season_folder / f"season{season_number:02d}-poster.jpg"
    if not _should_write(dest, force):
        return True
    url = tmdb_image_url(poster_path, "w500")
    if not url:
        return False
    return _download_image(url, dest, client=http_client)


def write_episode_nfo_only(
    library_path: str,
    ep_data: dict[str, Any],
    season: int,
    episode: int,
    *,
    force: bool,
) -> bool:
    nfo_path = episode_nfo_path(library_path)
    if _should_write(nfo_path, force):
        _write_xml(build_episode_nfo(ep_data, season, episode), nfo_path)
    return nfo_path.exists()


def collect_episode_still_job(
    library_path: str,
    ep_data: dict[str, Any],
    *,
    force: bool,
) -> ImageJob | None:
    thumb_path = episode_thumb_path(library_path)
    if not _should_write(thumb_path, force):
        return None
    url = tmdb_image_url(ep_data.get("still_path"), "w300")
    if not url:
        return None
    return url, thumb_path


def write_episode_metadata(
    library_path: str,
    ep_data: dict[str, Any],
    season: int,
    episode: int,
    *,
    force: bool,
    write_nfo: bool,
    write_still: bool,
    http_client: httpx.Client | None = None,
) -> dict[str, bool]:
    results = {"episode_nfo": False, "episode_still": False}
    if write_nfo:
        results["episode_nfo"] = write_episode_nfo_only(
            library_path, ep_data, season, episode, force=force
        )

    if write_still:
        thumb_path = episode_thumb_path(library_path)
        if not _should_write(thumb_path, force):
            results["episode_still"] = thumb_path.exists()
        else:
            job = collect_episode_still_job(library_path, ep_data, force=force)
            if job:
                url, dest = job
                results["episode_still"] = _download_image(url, dest, client=http_client)
            else:
                results["episode_still"] = False

    return results


def read_episode_nfo(library_path: str | None) -> dict[str, str | None]:
    if not library_path:
        return {}
    nfo_path = episode_nfo_path(library_path)
    if not nfo_path.exists():
        return {}
    try:
        tree = ET.parse(nfo_path)
        root = tree.getroot()
        tag = root.tag.lower()
        if tag not in {"episodedetails", "episode"}:
            return {}
        return {
            "title": _text(root, "title"),
            "overview": _text(root, "plot") or _text(root, "overview"),
            "air_date": _text(root, "aired") or _text(root, "premiered"),
        }
    except ET.ParseError:
        logger.warning("Invalid episode nfo: %s", nfo_path)
        return {}


def read_episode_title(library_path: str | None) -> str | None:
    return read_episode_nfo(library_path).get("title")


def _text(root: ET.Element, tag: str) -> str | None:
    node = root.find(tag)
    if node is not None and node.text:
        return node.text.strip()
    return None


def has_local_poster(media: MediaItem, library_root: str) -> str | None:
    """Return local poster path if exists in library folder."""
    from app.services.library_paths import resolve_show_folder

    folder = resolve_show_folder(media, library_root)
    if folder:
        poster = folder / "poster.jpg"
        if poster.exists():
            return str(poster)
    return None


