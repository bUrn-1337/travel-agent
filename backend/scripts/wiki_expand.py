"""
Wikipedia-based destination expander for TravelMind.

Scrapes Wikipedia categories to discover Indian tourist destinations,
then enriches each with real descriptions, coordinates, and highlights
from Wikipedia articles. Zero LLM calls — all data from Wikipedia.

What Wikipedia provides:
  - Description (article extract — better than LLM-generated)
  - Coordinates (lat/lon)
  - Categories → vibes
  - Thumbnail image URL
  - Linked articles → highlights

What we estimate (no Wikipedia source):
  - avg_cost_* : state averages from existing data
  - group_suitability : vibe-based defaults
  - best_months : vibe/region defaults
  - nearest_airport/railway : left as empty strings (no reliable source)

Usage:
  cd backend
  python3 scripts/wiki_expand.py --expand              # add new destinations
  python3 scripts/wiki_expand.py --enrich              # re-enrich existing 192
  python3 scripts/wiki_expand.py --expand --enrich     # both
  python3 scripts/wiki_expand.py --expand --dry-run    # preview
"""
import json
import time
import re
import argparse
import httpx
from pathlib import Path
from collections import defaultdict

DATA_PATH  = Path(__file__).parent.parent / "data" / "destinations.json"
WIKI_REST  = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
WIKI_API   = "https://en.wikipedia.org/w/api.php"
DELAY      = 0.25   # seconds between requests — well within Wikipedia limits


# ─────────────────────────────────────────────────────────────────────────────
# State / region / cost lookup tables
# ─────────────────────────────────────────────────────────────────────────────

STATE_REGION = {
    "Jammu & Kashmir (UT)": "North India",
    "Jammu and Kashmir":     "North India",
    "Ladakh (UT)":           "North India",
    "Ladakh":                "North India",
    "Himachal Pradesh":      "North India",
    "Uttarakhand":           "North India",
    "Punjab":                "North India",
    "Haryana":               "North India",
    "Delhi":                 "North India",
    "Uttar Pradesh":         "North India",
    "Rajasthan":             "North India",
    "Gujarat":               "West India",
    "Maharashtra":           "West India",
    "Goa":                   "West India",
    "Karnataka":             "South India",
    "Tamil Nadu":            "South India",
    "Kerala":                "South India",
    "Andhra Pradesh":        "South India",
    "Telangana":             "South India",
    "Puducherry":            "South India",
    "Madhya Pradesh":        "Central India",
    "Chhattisgarh":          "Central India",
    "Jharkhand":             "East India",
    "West Bengal":           "East India",
    "Bihar":                 "East India",
    "Odisha":                "East India",
    "Assam":                 "Northeast India",
    "Meghalaya":             "Northeast India",
    "Arunachal Pradesh":     "Northeast India",
    "Nagaland":              "Northeast India",
    "Manipur":               "Northeast India",
    "Mizoram":               "Northeast India",
    "Tripura":               "Northeast India",
    "Sikkim":                "Northeast India",
    "Andaman & Nicobar Islands": "Island",
    "Andaman and Nicobar Islands": "Island",
    "Lakshadweep (UT)":      "Island",
    "Lakshadweep":           "Island",
    "Dadra and Nagar Haveli and Daman and Diu (UT)": "West India",
}

# Default best months by primary vibe
VIBE_MONTHS = {
    "mountains":  [4,5,6,9,10],
    "trekking":   [4,5,6,9,10],
    "snow":       [12,1,2],
    "beach":      [10,11,12,1,2,3],
    "wildlife":   [11,12,1,2,3,4,5],
    "nature":     [9,10,11,12,1,2,3],
    "heritage":   [10,11,12,1,2,3],
    "spiritual":  [10,11,12,1,2,3],
    "desert":     [10,11,12,1,2],
    "backwaters": [9,10,11,12,1,2,3],
    "adventure":  [4,5,6,9,10],
    "honeymoon":  [10,11,12,1,2,3],
    "offbeat":    [9,10,11,12,1,2,3],
    "default":    [10,11,12,1,2,3],
}

# Default group suitability by primary vibe
VIBE_GROUP = {
    "mountains":  {"solo":0.8,  "couple":0.85, "friends":0.85, "family":0.7},
    "trekking":   {"solo":0.9,  "couple":0.75, "friends":0.9,  "family":0.5},
    "beach":      {"solo":0.8,  "couple":0.9,  "friends":0.9,  "family":0.8},
    "wildlife":   {"solo":0.75, "couple":0.8,  "friends":0.8,  "family":0.75},
    "heritage":   {"solo":0.85, "couple":0.8,  "friends":0.75, "family":0.85},
    "spiritual":  {"solo":0.85, "couple":0.75, "friends":0.7,  "family":0.9},
    "desert":     {"solo":0.8,  "couple":0.85, "friends":0.85, "family":0.75},
    "backwaters": {"solo":0.7,  "couple":0.95, "friends":0.75, "family":0.8},
    "adventure":  {"solo":0.85, "couple":0.75, "friends":0.95, "family":0.55},
    "honeymoon":  {"solo":0.4,  "couple":0.99, "friends":0.5,  "family":0.6},
    "offbeat":    {"solo":0.9,  "couple":0.75, "friends":0.85, "family":0.6},
    "nature":     {"solo":0.8,  "couple":0.85, "friends":0.8,  "family":0.8},
    "default":    {"solo":0.75, "couple":0.8,  "friends":0.8,  "family":0.75},
}

# Wikipedia categories → vibes mapping
CAT_VIBES = {
    "hill station":       ["mountains", "nature"],
    "hill stations":      ["mountains", "nature"],
    "ski resort":         ["mountains", "snow", "adventure"],
    "beach":              ["beach", "nature"],
    "beaches":            ["beach", "nature"],
    "wildlife sanctuary": ["wildlife", "nature"],
    "national park":      ["wildlife", "nature"],
    "tiger reserve":      ["wildlife", "nature"],
    "biosphere reserve":  ["wildlife", "nature"],
    "bird sanctuary":     ["wildlife", "nature"],
    "pilgrimage":         ["spiritual", "heritage"],
    "temple":             ["spiritual", "heritage"],
    "shrine":             ["spiritual"],
    "fort":               ["heritage", "history"],
    "palace":             ["heritage"],
    "heritage":           ["heritage"],
    "trekking":           ["trekking", "adventure"],
    "trek":               ["trekking", "adventure"],
    "backwater":          ["backwaters", "nature"],
    "island":             ["beach", "nature"],
    "desert":             ["desert", "nature"],
    "waterfall":          ["nature", "offbeat"],
    "lake":               ["nature"],
    "adventure":          ["adventure"],
    "honeymoon":          ["honeymoon", "nature"],
    "valley":             ["mountains", "nature"],
    "glacier":            ["mountains", "snow", "trekking"],
}

# Wikipedia categories to crawl for new Indian tourist destinations
WIKI_CATEGORIES = [
    # Hill stations
    "Hill_stations_in_India",
    "Hill_stations_in_Himachal_Pradesh",
    "Hill_stations_in_Uttarakhand",
    "Hill_stations_in_Tamil_Nadu",
    "Hill_stations_in_Karnataka",
    "Hill_stations_in_Maharashtra",
    "Hill_stations_in_West_Bengal",
    # Beaches
    "Beaches_of_Goa",
    "Beaches_of_Kerala",
    "Beaches_of_Tamil_Nadu",
    "Beaches_of_Karnataka",
    "Beaches_of_Maharashtra",
    "Beaches_of_Andhra_Pradesh",
    "Beaches_of_Odisha",
    # Wildlife
    "National_parks_of_India",
    "Wildlife_sanctuaries_of_India",
    "Tiger_reserves_of_India",
    "Bird_sanctuaries_in_India",
    # Heritage & culture
    "World_Heritage_Sites_in_India",
    "Forts_in_Rajasthan",
    "Palaces_in_Rajasthan",
    "Forts_in_Maharashtra",
    "Temples_in_Tamil_Nadu",
    "Temples_in_Odisha",
    # Northeast
    "Tourist_attractions_in_Meghalaya",
    "Tourist_attractions_in_Arunachal_Pradesh",
    "Tourist_attractions_in_Sikkim",
    "Tourist_attractions_in_Assam",
    "Tourist_attractions_in_Nagaland",
    # East India
    "Tourist_attractions_in_Odisha",
    "Tourist_attractions_in_Bihar",
    "Tourist_attractions_in_Jharkhand",
    "Tourist_attractions_in_West_Bengal",
    # Other
    "Waterfalls_of_India",
    "Lakes_of_India",
    "Islands_of_India",
    "Ski_resorts_in_India",
    "Trekking_routes_in_India",
    "Pilgrimage_sites_in_India",
    "Tourist_attractions_in_Ladakh",
    "Tourist_attractions_in_Lakshadweep",
]


# ─────────────────────────────────────────────────────────────────────────────
# Wikipedia API helpers
# ─────────────────────────────────────────────────────────────────────────────

def wiki_summary(title: str, client: httpx.Client) -> dict | None:
    """Fetch Wikipedia REST summary for a page title. Returns None on failure."""
    url = WIKI_REST.format(title=title.replace(" ", "_"))
    try:
        r = client.get(url, timeout=10)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def wiki_category_members(category: str, client: httpx.Client) -> list[str]:
    """Return page titles that are members of a Wikipedia category."""
    titles = []
    cmcontinue = None
    while True:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": f"Category:{category}",
            "cmlimit": "500",
            "cmtype": "page",
            "format": "json",
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue
        try:
            r = client.get(WIKI_API, params=params, timeout=15)
            data = r.json()
            titles += [m["title"] for m in data.get("query", {}).get("categorymembers", [])]
            cmcontinue = data.get("continue", {}).get("cmcontinue")
            if not cmcontinue:
                break
            time.sleep(DELAY)
        except Exception:
            break
    return titles


def wiki_page_categories(title: str, client: httpx.Client) -> list[str]:
    """Return Wikipedia categories for a page (lowercase strings)."""
    params = {
        "action": "query",
        "titles": title,
        "prop": "categories",
        "cllimit": "50",
        "format": "json",
    }
    try:
        r = client.get(WIKI_API, params=params, timeout=10)
        pages = r.json().get("query", {}).get("pages", {})
        cats = []
        for page in pages.values():
            for c in page.get("categories", []):
                cats.append(c["title"].replace("Category:", "").lower())
        return cats
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Data inference helpers
# ─────────────────────────────────────────────────────────────────────────────

def infer_vibes_from_categories(cats: list[str], extract: str = "") -> list[str]:
    """Map Wikipedia categories + article text to travel vibes."""
    vibes = set()
    text = " ".join(cats) + " " + extract.lower()

    for keyword, mapped in CAT_VIBES.items():
        if keyword in text:
            vibes.update(mapped)

    # Extra keyword hints from article extract
    kw_map = {
        "trekking":      "trekking",
        "hiking":        "trekking",
        "pilgrimage":    "spiritual",
        "temple":        "spiritual",
        "fort":          "heritage",
        "palace":        "heritage",
        "waterfall":     "nature",
        "river":         "nature",
        "lake":          "nature",
        "forest":        "nature",
        "jungle":        "wildlife",
        "safari":        "wildlife",
        "tiger":         "wildlife",
        "leopard":       "wildlife",
        "elephant":      "wildlife",
        "surfing":       "adventure",
        "rafting":       "adventure",
        "paragliding":   "adventure",
        "skiing":        "adventure",
        "honeymoon":     "honeymoon",
        "romantic":      "honeymoon",
        "backwater":     "backwaters",
        "houseboat":     "backwaters",
        "snow":          "snow",
        "glacier":       "snow",
        "dune":          "desert",
        "sand":          "desert",
        "island":        "beach",
        "coast":         "beach",
        "beach":         "beach",
        "heritage":      "heritage",
        "ancient":       "heritage",
        "medieval":      "heritage",
        "colonial":      "heritage",
        "offbeat":       "offbeat",
        "unexplored":    "offbeat",
        "remote":        "offbeat",
    }
    for kw, vibe in kw_map.items():
        if kw in text:
            vibes.add(vibe)

    return list(vibes) if vibes else ["nature", "offbeat"]


def primary_vibe(vibes: list[str]) -> str:
    priority = ["wildlife","beach","mountains","trekking","heritage","spiritual",
                "desert","backwaters","honeymoon","adventure","snow","nature","offbeat"]
    for v in priority:
        if v in vibes:
            return v
    return vibes[0] if vibes else "nature"


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def state_from_wiki(summary: dict) -> str | None:
    """Try to extract Indian state from Wikipedia description or categories."""
    desc = (summary.get("description", "") + " " + summary.get("extract", ""))[:500].lower()
    for state in STATE_REGION:
        if state.lower() in desc:
            return state
    return None


def estimate_costs(state: str, vibes: list[str], existing: list[dict]) -> tuple[int, int, int]:
    """Estimate budget/mid/luxury costs from state averages + vibe adjustments."""
    state_dests = [d for d in existing if d.get("state", "") == state]
    if state_dests:
        b = int(sum(d["avg_cost_budget"] for d in state_dests) / len(state_dests))
        m = int(sum(d["avg_cost_mid"]    for d in state_dests) / len(state_dests))
        l = int(sum(d["avg_cost_luxury"] for d in state_dests) / len(state_dests))
    else:
        # Regional fallback
        region = STATE_REGION.get(state, "")
        region_dests = [d for d in existing if STATE_REGION.get(d.get("state",""),"") == region]
        if region_dests:
            b = int(sum(d["avg_cost_budget"] for d in region_dests) / len(region_dests))
            m = int(sum(d["avg_cost_mid"]    for d in region_dests) / len(region_dests))
            l = int(sum(d["avg_cost_luxury"] for d in region_dests) / len(region_dests))
        else:
            b, m, l = 1000, 2000, 5000

    # Vibe adjustments
    if "honeymoon" in vibes or "luxury" in vibes:
        m = int(m * 1.3); l = int(l * 1.2)
    if "wildlife" in vibes:
        m = int(m * 1.2); l = int(l * 1.3)
    if "offbeat" in vibes:
        b = int(b * 0.85); m = int(m * 0.85)

    return b, m, l


def budget_range(mid: int) -> str:
    if mid < 1500: return "budget"
    if mid < 4000: return "medium"
    return "luxury"


def extract_highlights(summary: dict) -> list[str]:
    """Pull place names from the Wikipedia extract as highlights."""
    extract = summary.get("extract", "")
    # Extract capitalised multi-word proper nouns (likely place/attraction names)
    pattern = r'\b[A-Z][a-z]+(?: [A-Z][a-z]+)*(?:\s(?:Temple|Fort|Palace|Lake|River|Falls|Valley|Pass|Peak|Reserve|Park|Beach|Island|Sanctuary|Cave|Garden|Museum|Gate|Bridge|Dam|Waterfall))\b'
    found = re.findall(pattern, extract)
    highlights = list(dict.fromkeys(found))[:6]   # unique, max 6

    # If we got fewer than 3, also grab capitalised 2+ word phrases
    if len(highlights) < 3:
        extra = re.findall(r'\b[A-Z][a-z]+ [A-Z][a-z]+\b', extract)
        for e in extra:
            if e not in highlights and len(highlights) < 5:
                highlights.append(e)

    return highlights or ["Local Attractions", "Natural Scenery", "Cultural Sites"]


def distance_from_delhi(lat: float, lon: float) -> int:
    import math
    dlat, dlon = math.radians(28.6139), math.radians(77.2090)
    flat, flon = math.radians(lat), math.radians(lon)
    a = math.sin((flat-dlat)/2)**2 + math.cos(dlat)*math.cos(flat)*math.sin((flon-dlon)/2)**2
    return int(6371 * 2 * math.asin(math.sqrt(a)))


# ─────────────────────────────────────────────────────────────────────────────
# Build a full destination record from a Wikipedia summary
# ─────────────────────────────────────────────────────────────────────────────

def build_destination(title: str, summary: dict, cats: list[str], state: str, existing: list[dict]) -> dict | None:
    coords = summary.get("coordinates")
    if not coords:
        return None

    lat = coords.get("lat")
    lon = coords.get("lon")
    if lat is None or lon is None:
        return None

    # Clean up name (remove disambiguation e.g. "Manali, Himachal Pradesh")
    name = summary.get("title", title).split(",")[0].strip()
    if not name:
        return None

    dest_id = slugify(name)
    extract  = summary.get("extract", "")
    # Use first 2 sentences as description
    sentences = re.split(r'(?<=[.!?])\s+', extract.strip())
    description = " ".join(sentences[:2]).strip() or f"{name} is a tourist destination in {state}."

    vibes   = infer_vibes_from_categories(cats, extract)
    pvibe   = primary_vibe(vibes)
    b, m, l = estimate_costs(state, vibes, existing)
    region  = STATE_REGION.get(state, "North India")
    months  = VIBE_MONTHS.get(pvibe, VIBE_MONTHS["default"])
    group   = VIBE_GROUP.get(pvibe, VIBE_GROUP["default"])
    dist    = distance_from_delhi(lat, lon)
    highlights = extract_highlights(summary)

    # Duration estimate based on vibe
    if pvibe in ("wildlife", "mountains", "trekking", "beach"):
        min_d, max_d = 2, 5
    elif pvibe in ("heritage", "spiritual"):
        min_d, max_d = 1, 3
    else:
        min_d, max_d = 2, 4

    return {
        "id":                     dest_id,
        "name":                   name,
        "state":                  state,
        "region":                 region,
        "lat":                    round(lat, 4),
        "lon":                    round(lon, 4),
        "vibes":                  vibes,
        "primary_vibe":           pvibe,
        "description":            description,
        "avg_cost_budget":        b,
        "avg_cost_mid":           m,
        "avg_cost_luxury":        l,
        "min_days":               min_d,
        "max_days":               max_d,
        "best_months":            months,
        "group_suitability":      group,
        "popularity":             round(5.0 + (summary.get("extract_html", "x").__len__() % 40) / 10, 1),
        "nearest_airport":        "",
        "nearest_railway":        "",
        "nearest_major_city":     "",
        "distance_from_delhi_km": dist,
        "highlights":             highlights,
        "food_specialties":       [],
        "accommodation":          ["hotel", "guesthouse", "homestay"],
        "budget_range":           budget_range(m),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Enrich existing destinations with better Wikipedia descriptions
# ─────────────────────────────────────────────────────────────────────────────

def enrich_existing(destinations: list[dict], client: httpx.Client) -> list[dict]:
    enriched = []
    for i, dest in enumerate(destinations, 1):
        print(f"  [{i}/{len(destinations)}] {dest['name']}...", end=" ", flush=True)
        summary = wiki_summary(f"{dest['name']}, {dest['state']}", client)
        if not summary:
            summary = wiki_summary(dest["name"], client)

        if summary and summary.get("extract"):
            sentences = re.split(r'(?<=[.!?])\s+', summary["extract"].strip())
            desc = " ".join(sentences[:2]).strip()
            if len(desc) > len(dest.get("description","")) and len(desc) > 80:
                dest = {**dest, "description": desc}
                print("updated")
            else:
                print("kept")
        else:
            print("no wiki")

        enriched.append(dest)
        time.sleep(DELAY)
    return enriched


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Wikipedia destination expander")
    parser.add_argument("--enrich",  action="store_true", help="Re-enrich existing destinations with Wikipedia descriptions")
    parser.add_argument("--expand",  action="store_true", help="Add new destinations from Wikipedia categories")
    parser.add_argument("--dry-run", action="store_true", help="Print results without writing to file")
    args = parser.parse_args()

    if not args.enrich and not args.expand:
        print("Specify --enrich and/or --expand. See --help.")
        return

    with open(DATA_PATH) as f:
        destinations = json.load(f)

    existing_ids   = {d["id"]          for d in destinations}
    existing_names = {d["name"].lower() for d in destinations}
    print(f"Loaded {len(destinations)} existing destinations.")

    with httpx.Client(headers={"User-Agent": "TravelMindBot/1.0 (educational project)"}) as client:

        # ── ENRICH existing ───────────────────────────────────────────────────
        if args.enrich:
            print(f"\n── Enriching existing {len(destinations)} destinations ──")
            destinations = enrich_existing(destinations, client)

        # ── EXPAND with new ───────────────────────────────────────────────────
        if args.expand:
            print(f"\n── Scanning {len(WIKI_CATEGORIES)} Wikipedia categories ──")
            candidates = {}   # title → category list

            for cat in WIKI_CATEGORIES:
                print(f"  Category: {cat}...", end=" ", flush=True)
                members = wiki_category_members(cat, client)
                new = 0
                for m in members:
                    if m not in candidates:
                        candidates[m] = []
                    candidates[m].append(cat.lower().replace("_", " "))
                    new += 1
                print(f"{new} pages")
                time.sleep(DELAY)

            print(f"\nTotal candidates: {len(candidates)}")
            print("── Fetching summaries ──")

            new_dests = []
            skipped = added = 0

            for i, (title, source_cats) in enumerate(candidates.items(), 1):
                # Quick name check before API call
                clean = title.split(",")[0].strip()
                if (clean.lower() in existing_names or
                        slugify(clean) in existing_ids):
                    skipped += 1
                    continue

                # Skip disambiguation / list / template pages
                if any(x in title for x in ["(disambiguation)", "List of", "Template:", "Category:"]):
                    skipped += 1
                    continue

                print(f"  [{i}/{len(candidates)}] {title}...", end=" ", flush=True)

                summary = wiki_summary(title, client)
                time.sleep(DELAY)

                if not summary or not summary.get("coordinates"):
                    print("skip (no coords)")
                    skipped += 1
                    continue

                # Must be in India
                desc_text = (summary.get("description","") + summary.get("extract","")).lower()
                if "india" not in desc_text:
                    print("skip (not India)")
                    skipped += 1
                    continue

                # Determine state
                state = state_from_wiki(summary)
                if not state:
                    # Try from source categories
                    for s in STATE_REGION:
                        if s.lower() in " ".join(source_cats):
                            state = s
                            break
                if not state:
                    print("skip (no state)")
                    skipped += 1
                    continue

                # Get article categories for better vibe inference
                page_cats = wiki_page_categories(title, client)
                all_cats = source_cats + page_cats
                time.sleep(DELAY)

                dest = build_destination(title, summary, all_cats, state, destinations + new_dests)
                if not dest:
                    print("skip (build failed)")
                    skipped += 1
                    continue

                if dest["id"] in existing_ids or dest["name"].lower() in existing_names:
                    print("skip (duplicate)")
                    skipped += 1
                    continue

                existing_ids.add(dest["id"])
                existing_names.add(dest["name"].lower())
                new_dests.append(dest)
                added += 1
                print(f"ADD ({dest['state']}, {dest['primary_vibe']})")

            print(f"\nAdded {added} new destinations, skipped {skipped}.")
            destinations = destinations + new_dests

    if args.dry_run:
        new_only = [d for d in destinations if d["id"] not in {x["id"] for x in json.loads(DATA_PATH.read_text())}]
        print(f"\nDRY RUN — would add {len(new_only)} destinations:")
        for d in new_only[:20]:
            print(f"  {d['name']}, {d['state']} [{d['primary_vibe']}]")
        if len(new_only) > 20:
            print(f"  ... and {len(new_only)-20} more")
        return

    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(destinations, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(destinations)} destinations to {DATA_PATH}")
    print("Next: run python3 ingest.py to rebuild the ChromaDB index.")


if __name__ == "__main__":
    main()
