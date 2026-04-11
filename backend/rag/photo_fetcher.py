"""
P5 — Destination photo fetcher.

Priority chain:
  1. Pexels API  (set PEXELS_API_KEY env var — free tier: 200 req/hour)
  2. Wikipedia pageimages API (free, no key)
  3. None (frontend falls back to gradient)

Results are cached in memory for the lifetime of the process.
"""
import os
import logging
import httpx

logger = logging.getLogger(__name__)

_CACHE: dict[str, list[str]] = {}   # dest_id → list of photo URLs (up to 15)

PEXELS_URL   = "https://api.pexels.com/v1/search"
WIKI_API_URL = "https://en.wikipedia.org/w/api.php"


def _fetch_pexels(query: str, api_key: str, count: int = 6) -> list[str]:
    try:
        resp = httpx.get(
            PEXELS_URL,
            headers={"Authorization": api_key},
            params={"query": query, "per_page": count, "orientation": "landscape"},
            timeout=6,
        )
        resp.raise_for_status()
        return [p["src"]["large"] for p in resp.json().get("photos", [])]
    except Exception as e:
        logger.debug(f"Pexels fetch failed for '{query}': {e}")
    return []


def _fetch_wikipedia(name: str) -> list[str]:
    try:
        resp = httpx.get(
            WIKI_API_URL,
            params={
                "action":      "query",
                "prop":        "pageimages",
                "format":      "json",
                "pithumbsize": 800,
                "titles":      name,
            },
            timeout=6,
        )
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
        for page in pages.values():
            thumb = page.get("thumbnail", {}).get("source")
            if thumb:
                return [thumb]
    except Exception as e:
        logger.debug(f"Wikipedia photo fetch failed for '{name}': {e}")
    return []


def get_photos(dest_id: str, dest_name: str, state: str, count: int = 6) -> list[str]:
    """Return a list of photo URLs for the destination, using cache.
    Always fetches 15 and caches all; callers slice as needed.
    """
    if dest_id in _CACHE:
        return _CACHE[dest_id]

    urls: list[str] = []
    pexels_key = os.getenv("PEXELS_API_KEY", "").strip()

    if pexels_key:
        urls = _fetch_pexels(f"{dest_name} {state} India travel", pexels_key, count=15)

    if not urls:
        urls = _fetch_wikipedia(dest_name)

    _CACHE[dest_id] = urls
    return urls


def get_photo_url(dest_id: str, dest_name: str, state: str) -> str | None:
    """Return the first photo URL (used for search response injection)."""
    photos = get_photos(dest_id, dest_name, state, count=6)
    return photos[0] if photos else None
