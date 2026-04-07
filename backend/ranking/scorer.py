"""
Composite destination scoring algorithm.

Score = weighted sum of:
  - vibe_match      (0-1): how many requested vibes the destination covers
  - semantic        (0-1): cosine similarity between query text and destination embedding
  - budget_fit      (0-1): how well avg daily cost fits user's budget
  - group_fit       (0-1): destination's suitability for the group type
  - distance        (0-1): proximity to user's GPS location (exponential decay)
  - season_fit      (0-1): whether current/travel month is in best_months
  - popularity      (0-1): normalized popularity score
  - duration_fit    (0-1): whether requested days falls in [min_days, max_days]

Weights are tunable — kept data-driven, no LLM.
distance weight is 0 when no GPS provided (neutral fallback 0.5).
"""
import math
from datetime import datetime
from typing import Optional

WEIGHTS = {
    "vibe_match":   0.27,
    "semantic":     0.22,
    "budget_fit":   0.17,
    "group_fit":    0.09,
    "distance":     0.08,
    "season_fit":   0.07,
    "popularity":   0.07,
    "duration_fit": 0.03,
}


def vibe_match_score(destination: dict, requested_vibes: list[str]) -> float:
    """Fraction of requested vibes present in destination + partial keyword match."""
    if not requested_vibes:
        return 0.5
    dest_vibes = set(v.lower() for v in destination.get("vibes", []))
    requested = [v.lower() for v in requested_vibes]
    # Exact matches
    exact = sum(1 for v in requested if v in dest_vibes)
    # Partial / synonym matches (e.g. "hill station" → mountains)
    SYNONYMS: dict[str, list[str]] = {
        "mountains": ["mountains", "hill station", "snow", "trekking", "alpine", "hills"],
        "beach": ["beach", "coastal", "sea", "water sports", "island", "snorkeling", "scuba"],
        "heritage": ["heritage", "history", "architecture", "ruins", "fort", "temple", "palace"],
        "adventure": ["adventure", "trekking", "rafting", "paragliding", "skiing", "climbing"],
        "wildlife": ["wildlife", "safari", "tiger", "forest", "national park"],
        "spiritual": ["spiritual", "pilgrimage", "temple", "meditation", "yoga"],
        "offbeat": ["offbeat", "remote", "hidden", "backpacker", "unexplored"],
        "desert": ["desert", "sand dunes", "camel safari", "arid"],
        "backwaters": ["backwaters", "houseboat", "boat", "lagoon", "river"],
        "nature": ["nature", "forest", "waterfall", "biodiversity", "flora"],
        "honeymoon": ["honeymoon", "romantic", "couple"],
        "family": ["family", "kids"],
    }
    partial = 0
    for rv in requested:
        synonyms = SYNONYMS.get(rv, [rv])
        if any(s in dest_vibes for s in synonyms):
            partial = max(partial, 0.5)
    score = exact / len(requested)
    # Boost if any partial match fills the gap
    if score < 1.0 and partial > 0:
        score = min(1.0, score + 0.2)
    return score


def budget_fit_score(destination: dict, budget_per_day: float, days: int) -> float:
    """
    Returns 1.0 if the mid-range cost per day is at or below budget.
    Decays smoothly as cost exceeds budget.
    If budget is 0 or not provided, returns neutral 0.5.
    """
    if not budget_per_day or budget_per_day <= 0:
        return 0.5
    cost = destination.get("avg_cost_mid", 0)
    if cost <= 0:
        return 0.5
    ratio = cost / budget_per_day
    if ratio <= 1.0:
        return 1.0
    elif ratio <= 1.5:
        # Slight over budget: linear decay [1.0 → 0.3]
        return 1.0 - (ratio - 1.0) * 1.4
    else:
        # Way over budget: steep decay
        return max(0.0, 0.3 - (ratio - 1.5) * 0.3)


def distance_score(
    destination: dict,
    user_lat: Optional[float],
    user_lon: Optional[float],
) -> float:
    """
    Exponential decay based on haversine distance from user to destination.
    Returns 0.5 (neutral) if GPS not provided.

    Decay constant 2000 km:
      0 km   → 1.00  (same city)
      500 km → 0.78  (neighbouring state)
      1000km → 0.61  (cross-country short-haul)
      2000km → 0.37  (far end of India)
      3500km → 0.17  (very remote)
    """
    if user_lat is None or user_lon is None:
        return 0.5

    dest_lat = destination.get("lat")
    dest_lon = destination.get("lon")
    if dest_lat is None or dest_lon is None:
        return 0.5

    # Haversine formula
    R    = 6371.0
    lat1 = math.radians(user_lat)
    lat2 = math.radians(dest_lat)
    dlat = math.radians(dest_lat - user_lat)
    dlon = math.radians(dest_lon - user_lon)
    a    = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    dist_km = 2 * R * math.asin(math.sqrt(a))

    return math.exp(-dist_km / 2000.0)


def group_fit_score(destination: dict, group_type: str) -> float:
    suitability = destination.get("group_suitability", {})
    return suitability.get(group_type.lower(), 0.5) if group_type else 0.5


def season_fit_score(destination: dict, travel_month: int = None) -> float:
    """1.0 if travel_month is in best_months, 0.3 if not. Default: use current month."""
    month = travel_month or datetime.now().month
    best = destination.get("best_months", [])
    if not best:
        return 0.5
    return 1.0 if month in best else 0.3


def popularity_score(destination: dict) -> float:
    return destination.get("popularity", 5.0) / 10.0


def duration_fit_score(destination: dict, days: int) -> float:
    if not days:
        return 0.5
    min_d = destination.get("min_days", 1)
    max_d = destination.get("max_days", 14)
    if min_d <= days <= max_d:
        return 1.0
    elif days < min_d:
        # Too few days — partial fit
        return max(0.1, 1.0 - (min_d - days) * 0.2)
    else:
        # More days than max — flexible destination still OK
        return 0.7


def score_destination(
    destination: dict,
    vibes: list[str],
    budget_per_day: float,
    days: int,
    group_type: str,
    travel_month: int = None,
    semantic_score: float = 0.5,
    user_lat: Optional[float] = None,
    user_lon: Optional[float] = None,
) -> dict:
    """
    Compute composite score and return score breakdown dict.
    """
    vm  = vibe_match_score(destination, vibes)
    bf  = budget_fit_score(destination, budget_per_day, days)
    gf  = group_fit_score(destination, group_type)
    ds  = distance_score(destination, user_lat, user_lon)
    sf  = season_fit_score(destination, travel_month)
    pop = popularity_score(destination)
    dur = duration_fit_score(destination, days)
    sem = semantic_score

    composite = (
        WEIGHTS["vibe_match"]   * vm
        + WEIGHTS["semantic"]   * sem
        + WEIGHTS["budget_fit"] * bf
        + WEIGHTS["group_fit"]  * gf
        + WEIGHTS["distance"]   * ds
        + WEIGHTS["season_fit"] * sf
        + WEIGHTS["popularity"] * pop
        + WEIGHTS["duration_fit"] * dur
    )

    return {
        "composite": round(composite, 4),
        "breakdown": {
            "vibe_match":   round(vm, 3),
            "semantic":     round(sem, 3),
            "budget_fit":   round(bf, 3),
            "group_fit":    round(gf, 3),
            "distance":     round(ds, 3),
            "season_fit":   round(sf, 3),
            "popularity":   round(pop, 3),
            "duration_fit": round(dur, 3),
        },
    }


def rank_destinations(
    destinations: list[dict],
    vibes: list[str],
    budget_per_day: float,
    days: int,
    group_type: str,
    travel_month: int = None,
    semantic_scores_map: dict[str, float] = None,
    user_lat: Optional[float] = None,
    user_lon: Optional[float] = None,
    top_k: int = 50,
) -> list[dict]:
    """
    Score and sort all destinations. Returns enriched dicts with score info.
    """
    semantic_scores_map = semantic_scores_map or {}
    scored = []
    for dest in destinations:
        sem = semantic_scores_map.get(dest["id"], 0.5)
        score_info = score_destination(
            dest, vibes, budget_per_day, days, group_type,
            travel_month, sem, user_lat, user_lon,
        )
        enriched = {**dest, "score": score_info["composite"], "score_breakdown": score_info["breakdown"]}
        scored.append(enriched)

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]
