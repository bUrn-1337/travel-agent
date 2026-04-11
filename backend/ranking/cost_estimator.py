"""
Deterministic trip cost estimator — P3.

Computes per-person estimated costs based on:
  - Transport (flight / train / bus / drive) derived from distance + infrastructure data
  - Accommodation (~42% of avg_cost_mid, shared by room occupancy)
  - Food (~30% of avg_cost_mid per day)
  - Activities (by primary_vibe)
  - Local transport (flat ₹350/day)

All costs in INR. No external API calls.
"""
import re
import math

# ---------------------------------------------------------------------------
# Activity cost per person per day by primary_vibe
# ---------------------------------------------------------------------------
ACTIVITY_COST_PER_DAY = {
    "wildlife":   2000,
    "adventure":  1800,
    "trekking":   1200,
    "heritage":    500,
    "spiritual":   300,
    "mountains":   800,
    "beach":       600,
    "desert":     1000,
    "backwaters":  900,
    "nature":      600,
    "honeymoon":  1500,
    "offbeat":     700,
    "default":     500,
}

LOCAL_TRANSPORT_PER_DAY = 350   # ₹ rickshaw / local bus / metro

# Accommodation room occupancy divisor per group type
# i.e. how many people share one room → acc cost per person = room_rate / divisor
ROOM_OCCUPANCY = {
    "solo":    1.0,
    "couple":  2.0,
    "friends": 2.5,   # 4 people → ~1.5 rooms
    "family":  2.0,   # 4 people → 2 rooms
}

DELHI_LAT, DELHI_LON = 28.6139, 77.2090   # default origin when no GPS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def _parse_infra_km(s: str) -> int:
    """Extract km from strings like 'Bhuntar Airport (50 km)'. Returns 999 if not found."""
    m = re.search(r'\((\d+)\s*km\)', s or "")
    return int(m.group(1)) if m else 999


def _transport_options(dest: dict, user_lat=None, user_lon=None) -> tuple[list[dict], int]:
    """
    Build list of transport option dicts and return (options, dist_km).
    Each option: {mode, route, duration, one_way_cost_inr, notes}
    """
    olat = user_lat if user_lat is not None else DELHI_LAT
    olon = user_lon if user_lon is not None else DELHI_LON
    dist_km = int(_haversine_km(olat, olon, dest["lat"], dest["lon"]))

    airport_str  = dest.get("nearest_airport",  "")
    railway_str  = dest.get("nearest_railway",   "")
    airport_dist = _parse_infra_km(airport_str)
    rail_dist    = _parse_infra_km(railway_str)

    options: list[dict] = []

    # ── Flight ──────────────────────────────────────────────────────────────
    if dist_km > 300 and airport_dist < 120:
        if   dist_km <  600: fare = 3500
        elif dist_km < 1200: fare = 5500
        elif dist_km < 2000: fare = 7500
        else:                fare = 9500
        transfer = min(airport_dist * 15, 2000)   # cab to airport, capped
        airport_label = airport_str.split("(")[0].strip() or "nearest airport"
        options.append({
            "mode":            "Flight",
            "route":           f"Fly to {airport_label}",
            "duration":        f"~{max(1, dist_km // 600)}h flight + {airport_dist} km transfer",
            "one_way_cost_inr": fare + transfer,
            "notes":           "Book 2–4 weeks in advance on MakeMyTrip / Ixigo for best fares.",
        })

    # ── Train ────────────────────────────────────────────────────────────────
    if rail_dist < 200:
        if   dist_km <  400: fare = 350
        elif dist_km <  800: fare = 600
        elif dist_km < 1500: fare = 900
        else:                fare = 1400
        transfer = rail_dist * 12
        station_label = railway_str.split("(")[0].strip() or "nearest station"
        options.append({
            "mode":            "Train",
            "route":           f"Train to {station_label}",
            "duration":        f"~{max(2, dist_km // 60)}h train + {rail_dist} km transfer",
            "one_way_cost_inr": fare + transfer,
            "notes":           "Book on IRCTC. 3AC for comfort, Sleeper for budget.",
        })

    # ── Bus ──────────────────────────────────────────────────────────────────
    if dist_km < 800:
        fare = max(150, int(dist_km * 1.8))
        options.append({
            "mode":            "Bus",
            "route":           "State / private bus (direct or via nearest city)",
            "duration":        f"~{max(2, dist_km // 55)}h",
            "one_way_cost_inr": fare,
            "notes":           "Volvo AC sleeper available on popular routes.",
        })

    # ── Self-drive / Cab ─────────────────────────────────────────────────────
    if dist_km < 1200:
        fare = int(dist_km * 4.2)   # ₹4.2/km fuel + tolls
        options.append({
            "mode":            "Self Drive / Cab",
            "route":           f"~{dist_km} km road trip",
            "duration":        f"~{max(3, dist_km // 60)}h",
            "one_way_cost_inr": fare,
            "notes":           "Cab hire will cost ~₹12–16/km. Fuel estimate is for own vehicle.",
        })

    # Fallback if nothing matched (very remote)
    if not options:
        label = airport_str.split("(")[0].strip() or "nearest airport"
        options.append({
            "mode":            "Flight + Transfer",
            "route":           f"Fly via {label}",
            "duration":        "Check airline schedules",
            "one_way_cost_inr": 9000,
            "notes":           "Remote destination — plan transfers carefully.",
        })

    return options, dist_km


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def estimate_trip_cost(
    dest: dict,
    days: int,
    group_type: str = "friends",
    budget_per_day: float = 2000,
    user_lat: float = None,
    user_lon: float = None,
) -> dict:
    """
    Return a deterministic cost breakdown for a trip.

    Returns
    -------
    {
      "per_person": {
        "transport_return", "accommodation", "food",
        "activities", "local_transport", "total"
      },
      "daily_breakdown": {"accommodation", "food", "activities", "local"},
      "transport_options": [ {mode, route, duration, one_way_cost_inr, notes}, ... ],
      "dist_from_origin_km": int,
      "fits_budget": bool,
      "budget_gap_inr": int,   # negative = under budget, positive = over
      "days": int,
    }
    """
    gt        = (group_type or "friends").lower()
    occupancy = ROOM_OCCUPANCY.get(gt, 2.0)
    primary   = dest.get("primary_vibe", "default")
    avg_mid   = dest.get("avg_cost_mid", 2500)

    # Accommodation: avg_cost_mid is per-person per-day; ~42% is stay cost
    # We apply room sharing via the occupancy divisor on a room-rate basis
    room_rate_per_day = avg_mid * 0.42 * occupancy  # full room per night (INR)
    acc_per_person_day = room_rate_per_day / occupancy
    acc_total = int(acc_per_person_day * days)

    # Food: ~30% of avg daily cost
    food_per_day = int(avg_mid * 0.30)
    food_total   = food_per_day * days

    # Activities
    act_per_day  = ACTIVITY_COST_PER_DAY.get(primary, ACTIVITY_COST_PER_DAY["default"])
    act_total    = act_per_day * days

    # Local transport
    local_total = LOCAL_TRANSPORT_PER_DAY * days

    # Return transport (cheapest option × 2)
    transport_options, dist_km = _transport_options(dest, user_lat, user_lon)
    cheapest_one_way = min(o["one_way_cost_inr"] for o in transport_options)
    transport_total  = cheapest_one_way * 2

    total_per_person = acc_total + food_total + act_total + local_total + transport_total

    user_total_budget = budget_per_day * days
    budget_gap        = int(total_per_person - user_total_budget)

    return {
        "per_person": {
            "transport_return": transport_total,
            "accommodation":    acc_total,
            "food":             food_total,
            "activities":       act_total,
            "local_transport":  local_total,
            "total":            total_per_person,
        },
        "daily_breakdown": {
            "accommodation": int(acc_per_person_day),
            "food":          food_per_day,
            "activities":    act_per_day,
            "local":         LOCAL_TRANSPORT_PER_DAY,
        },
        "transport_options":   transport_options,
        "dist_from_origin_km": dist_km,
        "fits_budget":         budget_gap <= 0,
        "budget_gap_inr":      budget_gap,
        "days":                days,
    }
