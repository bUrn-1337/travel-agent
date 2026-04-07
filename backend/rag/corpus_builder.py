"""
Corpus builder: creates rich text documents per destination.

Sources (in order of preference):
  1. Wikipedia extract via MediaWiki API (no API key, free)
  2. Curated description from destinations.json

Each destination → one multi-section markdown document → handed to chunker.
"""
import time
import logging
import httpx
from urllib.parse import quote

logger = logging.getLogger(__name__)

MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

WIKI_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
WIKI_SEARCH_URL  = (
    "https://en.wikipedia.org/w/api.php"
    "?action=query&list=search&srsearch={q}&srlimit=1&format=json"
)
WIKI_EXTRACT_URL = (
    "https://en.wikipedia.org/w/api.php"
    "?action=query&titles={title}&prop=extracts"
    "&exintro=1&explaintext=1&format=json"
)


def _wiki_extract(dest_name: str, state: str, timeout: int = 8) -> str | None:
    """
    Fetch the Wikipedia intro section for a destination.
    Tries  "<name>, <state>" then just "<name>".
    Returns plain text or None on failure.
    """
    candidates = [f"{dest_name}, {state}", dest_name, f"{dest_name} India"]
    for query in candidates:
        try:
            # 1. Search for the best-matching article title
            search_url = WIKI_SEARCH_URL.format(q=quote(query))
            r = httpx.get(search_url, timeout=timeout,
                          headers={"User-Agent": "TravelAgent/1.0"})
            r.raise_for_status()
            results = r.json().get("query", {}).get("search", [])
            if not results:
                continue
            page_title = results[0]["title"]

            # 2. Fetch the extract
            extract_url = WIKI_EXTRACT_URL.format(title=quote(page_title))
            r2 = httpx.get(extract_url, timeout=timeout,
                           headers={"User-Agent": "TravelAgent/1.0"})
            r2.raise_for_status()
            pages = r2.json().get("query", {}).get("pages", {})
            for page in pages.values():
                text = page.get("extract", "").strip()
                if text and len(text) > 100:
                    # Trim to ~1200 chars to avoid bloated chunks
                    return text[:1500]
        except Exception as e:
            logger.debug(f"Wikipedia fetch failed for '{query}': {e}")
        time.sleep(0.3)   # polite rate-limiting
    return None


def _itinerary_template(dest: dict, days: int) -> str:
    """Generate a simple template itinerary from highlights."""
    highlights = dest.get("highlights", [])
    if not highlights:
        return ""
    lines = [f"## Sample {days}-Day Itinerary"]
    per_day = max(1, len(highlights) // days)
    for d in range(days):
        start = d * per_day
        end   = start + per_day if d < days - 1 else len(highlights)
        day_hl = highlights[start:end]
        if not day_hl:
            day_hl = highlights[-per_day:]
        lines.append(f"Day {d + 1}: {' | '.join(day_hl)}")
    return "\n".join(lines)


def build_document(dest: dict, fetch_wikipedia: bool = True) -> str:
    """
    Build a rich multi-section markdown document for one destination.
    This is what gets chunked and embedded into the vector store.
    """
    name    = dest["name"]
    state   = dest["state"]
    region  = dest["region"]
    vibes   = dest.get("vibes", [])
    min_d   = dest.get("min_days", 2)
    max_d   = dest.get("max_days", 7)

    sections: list[str] = []

    # ── Header ──────────────────────────────────────────────────────────────
    sections.append(
        f"# {name}\n"
        f"Location: {state}, {region}, India\n"
        f"Travel style: {', '.join(vibes)}\n"
        f"Recommended duration: {min_d}–{max_d} days"
    )

    # ── Overview ────────────────────────────────────────────────────────────
    wiki_text = _wiki_extract(name, state) if fetch_wikipedia else None
    overview  = wiki_text or dest.get("description", "")
    sections.append(f"## Overview\n{overview}")

    # ── Highlights & Attractions ─────────────────────────────────────────────
    highlights = dest.get("highlights", [])
    if highlights:
        hl_text = "\n".join(f"- {h}" for h in highlights)
        sections.append(f"## Highlights & Attractions\n{hl_text}")

    # ── Food & Cuisine ──────────────────────────────────────────────────────
    food = dest.get("food_specialties", [])
    if food:
        sections.append(
            f"## Food & Cuisine\n"
            f"Must-try local specialties: {', '.join(food)}.\n"
            f"The local food culture in {name} reflects the flavours of {state}."
        )

    # ── Getting There & Around ───────────────────────────────────────────────
    sections.append(
        f"## Getting There & Local Transport\n"
        f"Nearest Airport: {dest.get('nearest_airport', 'Check regional options')}\n"
        f"Nearest Railway Station: {dest.get('nearest_railway', 'N/A')}\n"
        f"Nearest Major City: {dest.get('nearest_major_city', 'N/A')}\n"
        f"Distance from Delhi: ~{dest.get('distance_from_delhi_km', 'N/A')} km\n"
        f"Local transport: auto-rickshaws, taxis, and local buses are common options."
    )

    # ── Accommodation ────────────────────────────────────────────────────────
    acc = dest.get("accommodation", [])
    budget_range = dest.get("budget_range", "medium")
    sections.append(
        f"## Where to Stay (Accommodation)\n"
        f"Available accommodation types: {', '.join(acc)}.\n"
        f"Budget range: {budget_range}.\n"
        f"Daily cost estimate:\n"
        f"  - Budget traveller: ₹{dest.get('avg_cost_budget', 0):,}/day\n"
        f"  - Mid-range: ₹{dest.get('avg_cost_mid', 0):,}/day\n"
        f"  - Luxury: ₹{dest.get('avg_cost_luxury', 0):,}/day"
    )

    # ── Best Time & Season ───────────────────────────────────────────────────
    best_months_str = ", ".join(
        MONTHS[m] for m in dest.get("best_months", []) if 1 <= m <= 12
    )
    sections.append(
        f"## Best Time to Visit\n"
        f"Best months: {best_months_str}.\n"
        f"Visiting during these months ensures the best weather and accessibility."
    )

    # ── Who Should Visit ─────────────────────────────────────────────────────
    suitability = dest.get("group_suitability", {})
    suit_lines  = "\n".join(
        f"  - {g.title()}: {'⭐' * round(v * 5)} ({v * 10:.0f}/10)"
        for g, v in suitability.items()
    )
    sections.append(f"## Who Should Visit\n{suit_lines}")

    # ── Itinerary Templates ───────────────────────────────────────────────────
    # Generate templates for min days and a mid-range option
    durations = sorted({min_d, min(min_d + 2, max_d), max_d})
    for dur in durations[:2]:
        tmpl = _itinerary_template(dest, dur)
        if tmpl:
            sections.append(tmpl)

    return "\n\n".join(sections)
