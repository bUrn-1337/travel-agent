"""
Google Custom Search API integration.

Used ONLY for the top 2-3 destinations after ranking — not for all 50.
Fetches live web snippets that get added to the RAG context alongside
static ChromaDB chunks, giving the LLM current travel information.

Setup (one-time):
  1. Google Cloud Console → Enable "Custom Search API"
  2. Create API key → set env var GOOGLE_API_KEY
  3. programmablesearchengine.google.com → New engine → Search the entire web
     → copy the cx value → set env var GOOGLE_CSE_ID

Free tier: 100 queries/day. Each destination = 1 query.
"""
import os
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

CSE_URL = "https://www.googleapis.com/customsearch/v1"


def _is_configured() -> bool:
    return bool(os.getenv("GOOGLE_API_KEY")) and bool(os.getenv("GOOGLE_CSE_ID"))


def build_query(
    destination_name: str,
    state: str,
    vibes: list[str],
    days: int,
    group_type: str,
) -> str:
    """
    Build a targeted search query for a destination.
    Focused on practical travel info, not generic results.
    """
    vibe_str = " ".join(vibes[:2]) if vibes else "travel"
    return (
        f"{destination_name} {state} travel guide "
        f"{vibe_str} {days} days {group_type} tips 2025"
    )


def search_destination(
    destination_name: str,
    state: str,
    vibes: list[str],
    days: int,
    group_type: str,
    num_results: int = 5,
    timeout: int = 8,
) -> list[dict]:
    """
    Fetch live Google search results for a destination.

    Returns list of {title, snippet, link} dicts, or [] if:
      - API keys not configured
      - Rate limit hit
      - Any network/API error
    """
    if not _is_configured():
        logger.debug("Google Search not configured (GOOGLE_API_KEY / GOOGLE_CSE_ID not set)")
        return []

    query = build_query(destination_name, state, vibes, days, group_type)
    logger.info(f"Google Search: '{query}'")

    try:
        resp = httpx.get(
            CSE_URL,
            params={
                "key": os.getenv("GOOGLE_API_KEY"),
                "cx":  os.getenv("GOOGLE_CSE_ID"),
                "q":   query,
                "num": num_results,
                "lr":  "lang_en",
                "gl":  "in",   # India region bias
            },
            timeout=timeout,
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data  = resp.json()
        items = data.get("items", [])

        results = [
            {
                "title":   item.get("title", "").strip(),
                "snippet": item.get("snippet", "").strip().replace("\n", " "),
                "link":    item.get("link", ""),
            }
            for item in items
            if item.get("snippet")
        ]
        logger.info(f"  → {len(results)} results for {destination_name}")
        return results

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            logger.warning("Google Search rate limit hit (100/day free tier).")
        else:
            logger.warning(f"Google Search HTTP error: {e.response.status_code}")
        return []
    except Exception as e:
        logger.warning(f"Google Search failed for '{destination_name}': {e}")
        return []


def format_snippets_as_context(results: list[dict]) -> str:
    """
    Convert search results into a text block for the RAG prompt.
    Labelled separately so the LLM knows this is live web data.
    """
    if not results:
        return ""
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}")
        lines.append(f"   {r['snippet']}")
    return "\n".join(lines)
