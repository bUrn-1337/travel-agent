"""
Enrich the new Wikipedia-sourced destinations with missing structured fields:
  - nearest_airport       → Wikivoyage "Get in > By plane" → Wikipedia fallback
  - nearest_railway       → Wikivoyage "Get in > By train" → Wikipedia fallback
  - nearest_major_city    → coordinate lookup (no HTTP needed)
  - food_specialties      → Wikivoyage "Eat" section → Wikipedia fallback
  - highlights            → Wikivoyage "See" section → Wikipedia fallback

Zero LLM calls — pure Wikivoyage/Wikipedia text + regex + coordinate maths.
Wikivoyage is tried first because it has cleaner, more structured travel data
(bullet-point "See", "Eat", "Get in" sections written specifically for travellers).

Usage:
  cd backend
  python3 scripts/wiki_enrich.py            # enrich all destinations with empty fields
  python3 scripts/wiki_enrich.py --all      # re-enrich all 521 (overwrite existing too)
  python3 scripts/wiki_enrich.py --dry-run  # preview first 20 without writing
"""

import json, re, math, time, argparse, httpx
from pathlib import Path

DATA_PATH       = Path(__file__).parent.parent / "data" / "destinations.json"
WIKI_API        = "https://en.wikipedia.org/w/api.php"
WIKIVOYAGE_API  = "https://en.wikivoyage.org/w/api.php"
DELAY           = 0.25   # seconds between requests (be polite to both wikis)


# ─────────────────────────────────────────────────────────────────────────────
# Major Indian cities — used for nearest_major_city coordinate lookup
# ─────────────────────────────────────────────────────────────────────────────

MAJOR_CITIES = [
    ("Mumbai",       19.0760,  72.8777),
    ("Delhi",        28.6139,  77.2090),
    ("Bengaluru",    12.9716,  77.5946),
    ("Hyderabad",    17.3850,  78.4867),
    ("Ahmedabad",    23.0225,  72.5714),
    ("Chennai",      13.0827,  80.2707),
    ("Kolkata",      22.5726,  88.3639),
    ("Pune",         18.5204,  73.8567),
    ("Jaipur",       26.9124,  75.7873),
    ("Lucknow",      26.8467,  80.9462),
    ("Kanpur",       26.4499,  80.3319),
    ("Nagpur",       21.1458,  79.0882),
    ("Indore",       22.7196,  75.8577),
    ("Thane",        19.2183,  72.9781),
    ("Bhopal",       23.2599,  77.4126),
    ("Visakhapatnam",17.6868,  83.2185),
    ("Patna",        25.5941,  85.1376),
    ("Vadodara",     22.3072,  73.1812),
    ("Ghaziabad",    28.6692,  77.4538),
    ("Ludhiana",     30.9010,  75.8573),
    ("Agra",         27.1767,  78.0081),
    ("Nashik",       19.9975,  73.7898),
    ("Faridabad",    28.4089,  77.3178),
    ("Meerut",       28.9845,  77.7064),
    ("Rajkot",       22.3039,  70.8022),
    ("Varanasi",     25.3176,  82.9739),
    ("Srinagar",     34.0837,  74.7973),
    ("Aurangabad",   19.8762,  75.3433),
    ("Dhanbad",      23.7957,  86.4304),
    ("Amritsar",     31.6340,  74.8723),
    ("Navi Mumbai",  19.0330,  73.0297),
    ("Allahabad",    25.4358,  81.8463),
    ("Ranchi",       23.3441,  85.3096),
    ("Howrah",       22.5958,  88.2636),
    ("Coimbatore",   11.0168,  76.9558),
    ("Jabalpur",     23.1815,  79.9864),
    ("Gwalior",      26.2183,  78.1828),
    ("Vijayawada",   16.5062,  80.6480),
    ("Jodhpur",      26.2389,  73.0243),
    ("Madurai",       9.9252,  78.1198),
    ("Raipur",       21.2514,  81.6296),
    ("Kota",         25.2138,  75.8648),
    ("Chandigarh",   30.7333,  76.7794),
    ("Guwahati",     26.1445,  91.7362),
    ("Solapur",      17.6805,  75.9064),
    ("Hubli-Dharwad",15.3647,  75.1240),
    ("Tiruchirappalli", 10.7905, 78.7047),
    ("Bareilly",     28.3670,  79.4304),
    ("Mysuru",       12.2958,  76.6394),
    ("Tiruppur",     11.1075,  77.3398),
    ("Gurgaon",      28.4595,  77.0266),
    ("Aligarh",      27.8974,  78.0880),
    ("Jalandhar",    31.3260,  75.5762),
    ("Bhubaneswar",  20.2961,  85.8245),
    ("Salem",        11.6643,  78.1460),
    ("Warangal",     17.9689,  79.5941),
    ("Thiruvananthapuram", 8.5241, 76.9366),
    ("Bhiwandi",     19.2813,  73.0631),
    ("Saharanpur",   29.9640,  77.5461),
    ("Guntur",       16.3067,  80.4365),
    ("Amravati",     20.9374,  77.7796),
    ("Bikaner",      28.0229,  73.3119),
    ("Noida",        28.5355,  77.3910),
    ("Jamshedpur",   22.8046,  86.2029),
    ("Bhilai",       21.2090,  81.3785),
    ("Cuttack",      20.4625,  85.8828),
    ("Kochi",         9.9312,  76.2673),
    ("Dehradun",     30.3165,  78.0322),
    ("Shimla",       31.1048,  77.1734),
    ("Imphal",       24.8170,  93.9368),
    ("Shillong",     25.5788,  91.8933),
    ("Aizawl",       23.7271,  92.7176),
    ("Kohima",       25.6701,  94.1077),
    ("Itanagar",     27.0844,  93.6053),
    ("Gangtok",      27.3389,  88.6065),
    ("Agartala",     23.8315,  91.2868),
    ("Dispur",       26.1433,  91.7898),
    ("Panaji",       15.4909,  73.8278),
    ("Port Blair",   11.6234,  92.7265),
    ("Jammu",        32.7266,  74.8570),
    ("Leh",          34.1526,  77.5771),
    ("Puducherry",   11.9416,  79.8083),
    ("Mangaluru",    12.9141,  74.8560),
    ("Udaipur",      24.5854,  73.7125),
    ("Ajmer",        26.4499,  74.6399),
    ("Siliguri",     26.7271,  88.3953),
    ("Durgapur",     23.5204,  87.3119),
    ("Asansol",      23.6833,  86.9667),
]


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    p = math.pi / 180
    a = (math.sin((lat2-lat1)*p/2)**2 +
         math.cos(lat1*p)*math.cos(lat2*p)*math.sin((lon2-lon1)*p/2)**2)
    return 2 * R * math.asin(math.sqrt(a))


def nearest_major_city(lat, lon):
    best_name, best_dist = None, float("inf")
    for name, clat, clon in MAJOR_CITIES:
        d = haversine_km(lat, lon, clat, clon)
        if d < best_dist:
            best_dist, best_name = d, name
    return best_name


# ─────────────────────────────────────────────────────────────────────────────
# MediaWiki full-text fetch (works for both Wikipedia and Wikivoyage)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_fulltext(api_url: str, title: str, client: httpx.Client) -> str | None:
    """Fetch a full article as plain text from any MediaWiki instance."""
    params = {
        "action": "query",
        "titles": title,
        "prop": "extracts",
        "explaintext": "1",
        "format": "json",
    }
    try:
        r = client.get(api_url, params=params, timeout=15)
        pages = r.json().get("query", {}).get("pages", {})
        for page in pages.values():
            if page.get("missing") is not None:
                return None
            text = page.get("extract", "")
            if text and len(text) > 100:
                return text
    except Exception:
        pass
    return None


def fetch_wikivoyage(name: str, state: str, client: httpx.Client) -> str | None:
    """Try Wikivoyage with a few title variants."""
    for title in [name, f"{name}, {state}", f"{name} (India)"]:
        text = fetch_fulltext(WIKIVOYAGE_API, title, client)
        if text:
            return text
        time.sleep(DELAY)
    return None


def fetch_wikipedia(name: str, state: str, client: httpx.Client) -> str | None:
    """Try Wikipedia with a few title variants."""
    for title in [f"{name}, {state}", name, f"{name} (India)"]:
        text = fetch_fulltext(WIKI_API, title, client)
        if text:
            return text
        time.sleep(DELAY)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Section parser
# ─────────────────────────────────────────────────────────────────────────────

def find_section(text: str, headings: list[str]) -> str:
    """
    Extract content of a named section from MediaWiki plain text.
    Handles both == Section == and === Subsection === levels.
    Stops at the next same-level or higher-level heading.
    """
    lines = text.split("\n")
    in_section = False
    section_lines = []
    section_level = 2  # default == level

    for line in lines:
        stripped = line.strip()
        # Detect heading: == ... == or === ... ===
        m = re.match(r'^(={2,4})\s*(.+?)\s*\1\s*$', stripped)
        if m:
            level   = len(m.group(1))
            heading = m.group(2).lower()
            if any(h.lower() in heading for h in headings):
                in_section   = True
                section_level = level
                section_lines = []
                continue
            elif in_section and level <= section_level:
                break  # same or higher level heading ends the section
        elif in_section:
            section_lines.append(line)

    return "\n".join(section_lines).strip()


# ─────────────────────────────────────────────────────────────────────────────
# Wikivoyage-aware extractors
# ─────────────────────────────────────────────────────────────────────────────

def extract_airport_from_wikivoyage(wv_text: str) -> str:
    """
    Wikivoyage 'Get in > By plane' has clean structured airport info:
      * The nearest airport is Kangra Airport (IATA: DHM), 15 km away.
      * Flights land at Shimla Airport (SLV), 23 km from the town.
    """
    # Grab the "By plane" subsection of "Get in"
    getin = find_section(wv_text, ["get in", "getting there", "by air", "by plane",
                                    "arrive", "arrival", "fly"])
    # Also try just the full "Get in" if By plane is empty
    if not getin:
        getin = find_section(wv_text, ["get in", "getting there"])
    text = getin if len(getin) > 30 else wv_text[:3000]

    patterns = [
        r'([A-Z][^.,\n]{3,50}?[Aa]irport)\s*\((?:IATA:\s*[A-Z]{3}[,\s]*)?(?:\d+)\s*km\)',
        r'([A-Z][^.,\n]{3,50}?[Aa]irport)[^.]*?(?:IATA:\s*[A-Z]{3})?[^.]*?(\d+)\s*km',
        r'(?:nearest|closest|nearest\s+major)\s+airport[^.]*?(?:is|:)?\s*([A-Z][^.,\n]{3,50}?[Aa]irport)[^.]*?(?:(\d+)\s*km)?',
        r'(?:fly|flight|flights?)\s+(?:to|into|via)\s+([A-Z][^.,\n]{3,50}?[Aa]irport)[^.]*?(?:(\d+)\s*km)?',
        r'([A-Z][^.,\n]{3,50}?[Aa]irport)\s*\((\d+)\s*km\)',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            name = m.group(1).strip().rstrip(",.")
            # Try to get distance (group 2 if it exists and is numeric)
            dist = ""
            if m.lastindex and m.lastindex >= 2:
                g2 = m.group(2)
                if g2 and g2.isdigit():
                    dist = g2
            if dist:
                return f"{name} ({dist} km)"
            return name
    return ""


def extract_railway_from_wikivoyage(wv_text: str) -> str:
    """
    Wikivoyage 'Get in > By train' has structured railway info:
      * The nearest railhead is Pathankot Junction, 90 km away.
    """
    bytrain = find_section(wv_text, ["by train", "by rail", "by railway",
                                      "by bus", "get in", "getting there"])
    text = bytrain if len(bytrain) > 30 else wv_text[:3000]

    patterns = [
        r'(?:nearest|closest)\s+(?:railway\s+station|railhead|train\s+station)[^.]*?(?:is|at|:)?\s*([A-Z][^.,\n]{3,50}?(?:Junction|Station|Railway)?)[^.]*?(?:(\d+)\s*km)?',
        r'([A-Z][^.,\n]{3,50}?(?:Junction|Railway\s+Station))\s*[,(]\s*(\d+)\s*km',
        r'(?:train|rail)\s+to\s+([A-Z][^.,\n]{3,50}?(?:Junction|Station))[^.]*?(?:(\d+)\s*km)?',
        r'(?:nearest|closest)\s+railhead[^.]*?\s+([A-Z][^.,\n]{3,50})[^.]*?(?:(\d+)\s*km)?',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            name = m.group(1).strip().rstrip(",.")
            dist = ""
            if m.lastindex and m.lastindex >= 2:
                g2 = m.group(2)
                if g2 and g2.isdigit():
                    dist = g2
            if dist:
                return f"{name} ({dist} km)"
            return name
    return ""


def extract_food_from_wikivoyage(wv_text: str, dest_name: str, state: str) -> list[str]:
    """
    Wikivoyage 'Eat' section has bullet-point dish names:
      * '''Chha Gosht''' - Mutton dish cooked with yoghurt.
      * '''Sidu''' - A type of steamed bread.
    Pattern extracts '''Name''' style entries first, then falls back to noun scan.
    """
    eat_section = find_section(wv_text, ["eat", "food", "cuisine", "dining",
                                          "restaurants", "gastronomy"])
    text = eat_section if len(eat_section) > 50 else ""

    food_items = []
    seen = set()

    # Wikivoyage bold format: '''Dish Name'''
    bold_items = re.findall(r"'{2,3}([^']{2,40})'{2,3}", text)
    for item in bold_items:
        item = item.strip()
        if item and item not in seen and not item[0].isdigit():
            seen.add(item)
            food_items.append(item)
        if len(food_items) >= 6:
            break

    if len(food_items) >= 3:
        return food_items[:5]

    # Fallback: capitalised nouns from eat section or full text
    search_text = text if len(text) > 50 else wv_text[:3000]
    STOP = {"The", "In", "It", "At", "Is", "And", "Or", "But", "From", "With",
            "This", "That", "These", "Their", "There", "They", "Also", "Has",
            "Are", "Was", "Were", "An", "A", "As", "By", "For", "Of", "To",
            state.split()[0] if state else "", dest_name.split()[0],
            "India", "Indian", "Local", "Traditional", "Famous", "Known",
            "Food", "Cuisine", "Dish", "Common", "See", "Also", "Get"}
    raw = re.findall(r'\b([A-Z][a-z]{2,}(?:\s+[A-Za-z]{2,}){0,2})\b', search_text)
    for item in raw:
        words = item.split()
        if (1 <= len(words) <= 3 and item not in seen
                and words[0] not in STOP and len(item) > 3
                and not item.isupper()):
            seen.add(item)
            food_items.append(item)
        if len(food_items) >= 6:
            break

    return food_items[:5]


def extract_highlights_from_wikivoyage(wv_text: str) -> list[str]:
    """
    Wikivoyage 'See' section has structured bullet points:
      * '''Triund''' - A beautiful meadow accessible by trekking.
      * '''McLeod Ganj''' - Residence of the Tibetan government-in-exile.
    Also checks 'Do' section for activity-based highlights.
    """
    see_section  = find_section(wv_text, ["see", "sights", "attractions",
                                           "points of interest", "sightseeing"])
    do_section   = find_section(wv_text, ["do", "activities", "things to do",
                                           "highlights"])
    combined = (see_section + "\n" + do_section).strip()
    text = combined if len(combined) > 50 else wv_text[:2000]

    highlights = []
    seen = set()

    # Wikivoyage bold: * '''Place Name''' - description
    bold_items = re.findall(r"'{2,3}([^']{3,60})'{2,3}", text)
    for item in bold_items:
        item = item.strip().rstrip(".")
        if item and item not in seen and item[0].isupper():
            seen.add(item)
            highlights.append(item)
        if len(highlights) >= 6:
            break

    if len(highlights) >= 3:
        return highlights[:5]

    # Fallback: short capitalised lines (like Wikipedia plain text)
    lines = [l.strip().lstrip("*-• ") for l in text.split("\n") if l.strip()]
    for line in lines:
        if 5 < len(line) < 60 and line[0].isupper() and line not in seen:
            if not any(skip in line.lower() for skip in
                       ["see also", "references", "external", "note:", "citation", "edit"]):
                seen.add(line)
                highlights.append(line)
        if len(highlights) >= 6:
            break

    return highlights[:5]


# ─────────────────────────────────────────────────────────────────────────────
# Wikipedia fallback extractors (plain prose — less structured)
# ─────────────────────────────────────────────────────────────────────────────

def extract_airport_wiki(text: str) -> str:
    patterns = [
        r'(?:nearest|closest)\s+airport[^.]*?(?:is|at|named?)?\s*([A-Z][^.,\n]{3,50}?[Aa]irport)[^.]*?(?:(\d+)\s*km)?',
        r'([A-Z][^.,\n]{3,50}?[Aa]irport)\s*\((\d+)\s*km\)',
        r'served\s+by\s+([A-Z][^.,\n]{3,50}?[Aa]irport)[^.]*?(?:(\d+)\s*km)?',
        r'(?:fly|flight)\s+to\s+([A-Z][^.,\n]{3,50}?[Aa]irport)[^.]*?(?:(\d+)\s*km)?',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            name = m.group(1).strip().rstrip(",.")
            dist = m.group(2) if m.lastindex and m.lastindex >= 2 and m.group(2) else ""
            return f"{name} ({dist} km)" if dist else name
    return ""


def extract_railway_wiki(text: str) -> str:
    patterns = [
        r'(?:nearest|closest)\s+railway\s+station[^.]*?(?:is|at)?\s*([A-Z][^.,\n]{3,50}?(?:Junction|Station|Railway)?)[^.]*?(?:(\d+)\s*km)?',
        r'([A-Z][^.,\n]{3,50}?(?:Junction|Railway\s+Station))\s*\((\d+)\s*km\)',
        r'(?:train|rail)\s+to\s+([A-Z][^.,\n]{3,50}?(?:Junction|Station))[^.]*?(?:(\d+)\s*km)?',
        r'(?:nearest|closest)\s+railhead[^.]*?(?:is|at)?\s*([A-Z][^.,\n]{3,50})(?:[^.]*?(\d+)\s*km)?',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            name = m.group(1).strip().rstrip(",.")
            dist = m.group(2) if m.lastindex and m.lastindex >= 2 and m.group(2) else ""
            return f"{name} ({dist} km)" if dist else name
    return ""


def extract_food_wiki(text: str, dest_name: str, state: str) -> list[str]:
    section = find_section(text, ["cuisine", "food", "gastronomy", "local food",
                                  "culinary", "eating", "dishes"])
    search_text = section if len(section) > 50 else text[:3000]
    found = []
    STOP = {"The", "In", "It", "At", "Is", "And", "Or", "But", "From", "With",
            "This", "That", "These", "Their", "There", "They", "Also", "Has",
            "Are", "Was", "Were", "An", "A", "As", "By", "For", "Of", "To",
            state.split()[0] if state else "", dest_name.split()[0],
            "India", "Indian", "Local", "Traditional", "Famous", "Known",
            "Food", "Cuisine", "Dish", "Common"}
    raw = re.findall(r'\b([A-Z][a-z]{2,}(?:\s+[A-Za-z]{2,}){0,2})\b', search_text)
    seen = set()
    for item in raw:
        words = item.split()
        if (1 <= len(words) <= 3 and item not in seen
                and words[0] not in STOP and len(item) > 3 and not item.isupper()):
            seen.add(item)
            found.append(item)
        if len(found) >= 6:
            break
    return found[:5]


def extract_highlights_wiki(text: str) -> list[str]:
    section = find_section(text, [
        "tourist attraction", "places of interest", "sightseeing",
        "attractions", "points of interest", "tourism", "highlights",
        "things to do", "places to visit", "notable"
    ])
    search_text = section if len(section) > 100 else text[:2000]
    lines = [l.strip().lstrip("*-• ") for l in search_text.split("\n") if l.strip()]
    highlights = []
    seen = set()
    for line in lines:
        if 5 < len(line) < 60 and line[0].isupper() and line not in seen:
            if not any(skip in line.lower() for skip in
                       ["see also", "references", "external", "note:", "citation", "edit"]):
                seen.add(line)
                highlights.append(line)
        if len(highlights) >= 6:
            break
    return highlights[:5]


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all",     action="store_true",
                        help="Re-enrich all destinations (not just empty ones)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show results without writing to disk")
    args = parser.parse_args()

    with open(DATA_PATH) as f:
        destinations = json.load(f)

    if args.all:
        targets = destinations
    else:
        targets = [d for d in destinations
                   if not d.get("nearest_airport")
                   or not d.get("food_specialties")
                   or not d.get("nearest_major_city")
                   or len(d.get("highlights", [])) < 3]

    print(f"Enriching {len(targets)}/{len(destinations)} destinations…")
    print("Strategy: Wikivoyage first → Wikipedia fallback\n")

    dest_map = {d["id"]: i for i, d in enumerate(destinations)}
    updated = 0

    with httpx.Client(headers={"User-Agent": "TravelMindBot/1.0 (travel app enrichment)"}) as client:
        for i, dest in enumerate(targets, 1):
            name  = dest["name"]
            state = dest.get("state", "")
            lat   = dest.get("lat",  0)
            lon   = dest.get("lon",  0)
            print(f"[{i}/{len(targets)}] {name}", end=" ", flush=True)

            changes = {}

            # ── nearest_major_city (pure math, no HTTP) ────────────────────
            if not dest.get("nearest_major_city") and lat and lon:
                changes["nearest_major_city"] = nearest_major_city(lat, lon)

            needs_transport = not dest.get("nearest_airport") or not dest.get("nearest_railway")
            needs_food      = not dest.get("food_specialties")
            needs_hl        = len(dest.get("highlights", [])) < 3

            if not (needs_transport or needs_food or needs_hl):
                if changes:
                    print(f"[city={changes.get('nearest_major_city','')}]")
                else:
                    print("—")
                if changes:
                    idx = dest_map[dest["id"]]
                    destinations[idx] = {**destinations[idx], **changes}
                    updated += 1
                continue

            # ── Try Wikivoyage first ───────────────────────────────────────
            print("[WV]", end=" ", flush=True)
            wv_text = fetch_wikivoyage(name, state, client)

            wv_airport = wv_railway = wv_food = wv_hl = None

            if wv_text:
                if needs_transport:
                    wv_airport = extract_airport_from_wikivoyage(wv_text)
                    wv_railway = extract_railway_from_wikivoyage(wv_text)
                if needs_food:
                    wv_food = extract_food_from_wikivoyage(wv_text, name, state)
                if needs_hl:
                    wv_hl = extract_highlights_from_wikivoyage(wv_text)

            # ── Wikipedia fallback for anything still missing ──────────────
            still_needs_wiki = (
                (needs_transport and not (wv_airport and wv_railway)) or
                (needs_food      and not (wv_food and len(wv_food) >= 2)) or
                (needs_hl        and not (wv_hl   and len(wv_hl)   >= 3))
            )

            wiki_text = None
            if still_needs_wiki:
                print("[WP]", end=" ", flush=True)
                wiki_text = fetch_wikipedia(name, state, client)

            # ── Merge: Wikivoyage wins, Wikipedia fills gaps ───────────────
            if needs_transport:
                airport = wv_airport or (extract_airport_wiki(wiki_text) if wiki_text else "")
                railway = wv_railway or (extract_railway_wiki(wiki_text) if wiki_text else "")
                if not dest.get("nearest_airport") and airport:
                    changes["nearest_airport"] = airport
                if not dest.get("nearest_railway") and railway:
                    changes["nearest_railway"] = railway

            if needs_food:
                food = wv_food if (wv_food and len(wv_food) >= 2) else (
                    extract_food_wiki(wiki_text, name, state) if wiki_text else []
                )
                if food and not dest.get("food_specialties"):
                    changes["food_specialties"] = food

            if needs_hl:
                hl = wv_hl if (wv_hl and len(wv_hl) >= 3) else (
                    extract_highlights_wiki(wiki_text) if wiki_text else []
                )
                existing_hl = dest.get("highlights", [])
                if hl and len(hl) > len(existing_hl):
                    changes["highlights"] = hl

            if changes:
                idx = dest_map[dest["id"]]
                destinations[idx] = {**destinations[idx], **changes}
                updated += 1
                tags = []
                if "nearest_airport"    in changes: tags.append("✈ " + changes["nearest_airport"][:20])
                if "nearest_railway"    in changes: tags.append("🚆 " + changes["nearest_railway"][:20])
                if "nearest_major_city" in changes: tags.append("🏙 " + changes["nearest_major_city"])
                if "food_specialties"   in changes: tags.append(f"🍛 {len(changes['food_specialties'])}")
                if "highlights"         in changes: tags.append(f"📍 {len(changes['highlights'])}")
                print("✓ " + "  ".join(tags))
            else:
                print("—")

    print(f"\nUpdated {updated}/{len(targets)} destinations.")

    if args.dry_run:
        print("DRY RUN — not writing to disk.")
        return

    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(destinations, f, indent=2, ensure_ascii=False)
    print(f"\nSaved → {DATA_PATH}")
    print("Next: docker compose exec backend python3 ingest.py")
    print("      to rebuild the RAG chunks with the enriched transport/food data.")


if __name__ == "__main__":
    main()
