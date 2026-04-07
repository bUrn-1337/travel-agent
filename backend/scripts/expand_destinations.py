"""
Destination Expander — adds ~100 new Indian destinations to destinations.json.

Structural fields (lat/lon, vibes, costs, seasons, group suitability) are
hardcoded with accurate data. Groq fills description + highlights + food_specialties.
Falls back to template values if GROQ_API_KEY is not set or call fails.

Usage:
  python3 scripts/expand_destinations.py             # uses Groq if key is set
  python3 scripts/expand_destinations.py --no-llm    # skip LLM, use templates only
  python3 scripts/expand_destinations.py --dry-run   # print JSON, don't write
"""
import json
import os
import sys
import time
import argparse
from pathlib import Path

import httpx

DATA_PATH = Path(__file__).parent.parent / "data" / "destinations.json"

GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.1-8b-instant"


# ---------------------------------------------------------------------------
# Seed list — ~100 new destinations
# Fields: id, name, state, region, lat, lon, vibes, primary_vibe,
#         avg_cost_budget/mid/luxury, min_days, max_days,
#         best_months, group_suitability, popularity,
#         nearest_airport, nearest_railway, nearest_major_city,
#         distance_from_delhi_km, budget_range
# description / highlights / food_specialties filled by LLM or fallback
# ---------------------------------------------------------------------------
NEW_DESTINATIONS = [

  # ── Uttarakhand (niche + famous) ───────────────────────────────────────────
  {"id":"haridwar","name":"Haridwar","state":"Uttarakhand","region":"North India",
   "lat":29.9457,"lon":78.1642,"vibes":["spiritual","heritage","nature","pilgrimage"],
   "primary_vibe":"spiritual","avg_cost_budget":700,"avg_cost_mid":1500,"avg_cost_luxury":3000,
   "min_days":1,"max_days":3,"best_months":[1,2,3,10,11,12],"popularity":9.0,
   "group_suitability":{"solo":0.8,"couple":0.75,"friends":0.7,"family":0.9},
   "nearest_airport":"Jolly Grant Airport (35 km)","nearest_railway":"Haridwar Junction (1 km)",
   "nearest_major_city":"Dehradun","distance_from_delhi_km":215,"budget_range":"budget"},

  {"id":"dehradun","name":"Dehradun","state":"Uttarakhand","region":"North India",
   "lat":30.3165,"lon":78.0322,"vibes":["nature","mountains","heritage","offbeat"],
   "primary_vibe":"nature","avg_cost_budget":1000,"avg_cost_mid":2000,"avg_cost_luxury":4500,
   "min_days":2,"max_days":4,"best_months":[3,4,5,9,10,11],"popularity":7.5,
   "group_suitability":{"solo":0.8,"couple":0.8,"friends":0.8,"family":0.85},
   "nearest_airport":"Jolly Grant Airport (25 km)","nearest_railway":"Dehradun Railway Station (2 km)",
   "nearest_major_city":"Dehradun","distance_from_delhi_km":290,"budget_range":"budget"},

  {"id":"dhanaulti","name":"Dhanaulti","state":"Uttarakhand","region":"North India",
   "lat":30.4126,"lon":78.2500,"vibes":["mountains","offbeat","nature","honeymoon","snow"],
   "primary_vibe":"mountains","avg_cost_budget":1200,"avg_cost_mid":2200,"avg_cost_luxury":4500,
   "min_days":2,"max_days":4,"best_months":[3,4,5,9,10,11,12,1,2],"popularity":6.5,
   "group_suitability":{"solo":0.75,"couple":0.95,"friends":0.8,"family":0.8},
   "nearest_airport":"Jolly Grant Airport (80 km)","nearest_railway":"Dehradun Railway Station (60 km)",
   "nearest_major_city":"Dehradun","distance_from_delhi_km":330,"budget_range":"budget"},

  {"id":"munsiyari","name":"Munsiyari","state":"Uttarakhand","region":"North India",
   "lat":30.0667,"lon":80.2333,"vibes":["mountains","trekking","offbeat","nature","adventure"],
   "primary_vibe":"mountains","avg_cost_budget":1000,"avg_cost_mid":2000,"avg_cost_luxury":3500,
   "min_days":3,"max_days":7,"best_months":[4,5,6,9,10],"popularity":6.0,
   "group_suitability":{"solo":0.9,"couple":0.8,"friends":0.9,"family":0.6},
   "nearest_airport":"Pantnagar Airport (250 km)","nearest_railway":"Kathgodam (230 km)",
   "nearest_major_city":"Pithoragarh","distance_from_delhi_km":590,"budget_range":"budget"},

  {"id":"kausani","name":"Kausani","state":"Uttarakhand","region":"North India",
   "lat":29.8404,"lon":79.5939,"vibes":["mountains","nature","offbeat","honeymoon","spiritual"],
   "primary_vibe":"mountains","avg_cost_budget":1000,"avg_cost_mid":2000,"avg_cost_luxury":4000,
   "min_days":2,"max_days":4,"best_months":[3,4,5,9,10,11],"popularity":6.5,
   "group_suitability":{"solo":0.8,"couple":0.95,"friends":0.75,"family":0.8},
   "nearest_airport":"Pantnagar Airport (155 km)","nearest_railway":"Kathgodam (120 km)",
   "nearest_major_city":"Almora","distance_from_delhi_km":415,"budget_range":"budget"},

  {"id":"ranikhet","name":"Ranikhet","state":"Uttarakhand","region":"North India",
   "lat":29.6433,"lon":79.4313,"vibes":["mountains","nature","offbeat","heritage"],
   "primary_vibe":"mountains","avg_cost_budget":900,"avg_cost_mid":1800,"avg_cost_luxury":3500,
   "min_days":2,"max_days":4,"best_months":[3,4,5,9,10,11],"popularity":6.0,
   "group_suitability":{"solo":0.75,"couple":0.85,"friends":0.75,"family":0.8},
   "nearest_airport":"Pantnagar Airport (120 km)","nearest_railway":"Kathgodam (85 km)",
   "nearest_major_city":"Almora","distance_from_delhi_km":360,"budget_range":"budget"},

  {"id":"almora","name":"Almora","state":"Uttarakhand","region":"North India",
   "lat":29.5973,"lon":79.6545,"vibes":["mountains","heritage","spiritual","nature","offbeat"],
   "primary_vibe":"mountains","avg_cost_budget":800,"avg_cost_mid":1600,"avg_cost_luxury":3000,
   "min_days":2,"max_days":4,"best_months":[3,4,5,9,10,11],"popularity":6.0,
   "group_suitability":{"solo":0.8,"couple":0.8,"friends":0.75,"family":0.8},
   "nearest_airport":"Pantnagar Airport (130 km)","nearest_railway":"Kathgodam (90 km)",
   "nearest_major_city":"Nainital","distance_from_delhi_km":380,"budget_range":"budget"},

  {"id":"lansdowne","name":"Lansdowne","state":"Uttarakhand","region":"North India",
   "lat":29.8404,"lon":78.6833,"vibes":["mountains","nature","offbeat","heritage"],
   "primary_vibe":"mountains","avg_cost_budget":900,"avg_cost_mid":1800,"avg_cost_luxury":3500,
   "min_days":2,"max_days":3,"best_months":[3,4,5,9,10,11],"popularity":5.5,
   "group_suitability":{"solo":0.8,"couple":0.85,"friends":0.75,"family":0.75},
   "nearest_airport":"Jolly Grant Airport (100 km)","nearest_railway":"Kotdwar (40 km)",
   "nearest_major_city":"Dehradun","distance_from_delhi_km":265,"budget_range":"budget"},

  {"id":"kanatal","name":"Kanatal","state":"Uttarakhand","region":"North India",
   "lat":30.3833,"lon":78.3667,"vibes":["mountains","offbeat","nature","honeymoon","snow"],
   "primary_vibe":"mountains","avg_cost_budget":1500,"avg_cost_mid":2800,"avg_cost_luxury":5500,
   "min_days":2,"max_days":3,"best_months":[3,4,5,9,10,11,12,1,2],"popularity":5.5,
   "group_suitability":{"solo":0.7,"couple":0.95,"friends":0.75,"family":0.75},
   "nearest_airport":"Jolly Grant Airport (85 km)","nearest_railway":"Dehradun (70 km)",
   "nearest_major_city":"Dehradun","distance_from_delhi_km":340,"budget_range":"medium"},

  {"id":"chakrata","name":"Chakrata","state":"Uttarakhand","region":"North India",
   "lat":30.6913,"lon":77.8681,"vibes":["mountains","offbeat","trekking","nature"],
   "primary_vibe":"mountains","avg_cost_budget":900,"avg_cost_mid":1800,"avg_cost_luxury":3000,
   "min_days":2,"max_days":4,"best_months":[4,5,6,9,10],"popularity":5.0,
   "group_suitability":{"solo":0.85,"couple":0.8,"friends":0.85,"family":0.7},
   "nearest_airport":"Jolly Grant Airport (90 km)","nearest_railway":"Dehradun (85 km)",
   "nearest_major_city":"Dehradun","distance_from_delhi_km":320,"budget_range":"budget"},

  {"id":"kedarnath","name":"Kedarnath","state":"Uttarakhand","region":"North India",
   "lat":30.7352,"lon":79.0669,"vibes":["spiritual","mountains","trekking","pilgrimage"],
   "primary_vibe":"spiritual","avg_cost_budget":1500,"avg_cost_mid":2500,"avg_cost_luxury":5000,
   "min_days":2,"max_days":5,"best_months":[5,6,9,10],"popularity":9.0,
   "group_suitability":{"solo":0.8,"couple":0.75,"friends":0.8,"family":0.75},
   "nearest_airport":"Jolly Grant Airport (238 km)","nearest_railway":"Rishikesh (216 km)",
   "nearest_major_city":"Rishikesh","distance_from_delhi_km":455,"budget_range":"medium"},

  {"id":"badrinath","name":"Badrinath","state":"Uttarakhand","region":"North India",
   "lat":30.7433,"lon":79.4938,"vibes":["spiritual","mountains","pilgrimage","nature"],
   "primary_vibe":"spiritual","avg_cost_budget":1200,"avg_cost_mid":2200,"avg_cost_luxury":4000,
   "min_days":2,"max_days":4,"best_months":[5,6,9,10],"popularity":8.5,
   "group_suitability":{"solo":0.8,"couple":0.75,"friends":0.75,"family":0.85},
   "nearest_airport":"Jolly Grant Airport (318 km)","nearest_railway":"Rishikesh (297 km)",
   "nearest_major_city":"Rishikesh","distance_from_delhi_km":530,"budget_range":"budget"},

  {"id":"pangot","name":"Pangot","state":"Uttarakhand","region":"North India",
   "lat":29.4333,"lon":79.6500,"vibes":["wildlife","nature","offbeat","trekking"],
   "primary_vibe":"wildlife","avg_cost_budget":1500,"avg_cost_mid":3000,"avg_cost_luxury":6000,
   "min_days":2,"max_days":4,"best_months":[11,12,1,2,3,4],"popularity":5.5,
   "group_suitability":{"solo":0.85,"couple":0.8,"friends":0.8,"family":0.7},
   "nearest_airport":"Pantnagar Airport (60 km)","nearest_railway":"Kathgodam (35 km)",
   "nearest_major_city":"Nainital","distance_from_delhi_km":310,"budget_range":"medium"},

  {"id":"pithoragarh","name":"Pithoragarh","state":"Uttarakhand","region":"North India",
   "lat":29.5831,"lon":80.2186,"vibes":["mountains","offbeat","trekking","heritage"],
   "primary_vibe":"mountains","avg_cost_budget":1000,"avg_cost_mid":2000,"avg_cost_luxury":3500,
   "min_days":3,"max_days":6,"best_months":[4,5,6,9,10],"popularity":5.5,
   "group_suitability":{"solo":0.85,"couple":0.75,"friends":0.85,"family":0.65},
   "nearest_airport":"Naini Saini Airport (5 km)","nearest_railway":"Tanakpur (151 km)",
   "nearest_major_city":"Almora","distance_from_delhi_km":500,"budget_range":"budget"},

  {"id":"sattal","name":"Sattal","state":"Uttarakhand","region":"North India",
   "lat":29.5404,"lon":79.6273,"vibes":["nature","offbeat","spiritual","wildlife"],
   "primary_vibe":"nature","avg_cost_budget":1200,"avg_cost_mid":2500,"avg_cost_luxury":5000,
   "min_days":2,"max_days":4,"best_months":[3,4,5,9,10,11],"popularity":5.5,
   "group_suitability":{"solo":0.8,"couple":0.85,"friends":0.75,"family":0.8},
   "nearest_airport":"Pantnagar Airport (50 km)","nearest_railway":"Kathgodam (22 km)",
   "nearest_major_city":"Nainital","distance_from_delhi_km":295,"budget_range":"budget"},

  # ── Himachal Pradesh (niche) ───────────────────────────────────────────────
  {"id":"kasol","name":"Kasol","state":"Himachal Pradesh","region":"North India",
   "lat":32.0098,"lon":77.3140,"vibes":["mountains","offbeat","trekking","nature","backpacker"],
   "primary_vibe":"mountains","avg_cost_budget":800,"avg_cost_mid":1800,"avg_cost_luxury":3500,
   "min_days":3,"max_days":7,"best_months":[4,5,6,9,10],"popularity":7.5,
   "group_suitability":{"solo":0.95,"couple":0.8,"friends":0.95,"family":0.5},
   "nearest_airport":"Bhuntar Airport (12 km)","nearest_railway":"Chandigarh Junction (250 km)",
   "nearest_major_city":"Chandigarh","distance_from_delhi_km":520,"budget_range":"budget"},

  {"id":"tirthan-valley","name":"Tirthan Valley","state":"Himachal Pradesh","region":"North India",
   "lat":31.6324,"lon":77.5098,"vibes":["nature","offbeat","trekking","wildlife","mountains"],
   "primary_vibe":"nature","avg_cost_budget":1200,"avg_cost_mid":2500,"avg_cost_luxury":5000,
   "min_days":3,"max_days":7,"best_months":[4,5,6,9,10],"popularity":6.0,
   "group_suitability":{"solo":0.9,"couple":0.85,"friends":0.85,"family":0.7},
   "nearest_airport":"Bhuntar Airport (50 km)","nearest_railway":"Chandigarh Junction (260 km)",
   "nearest_major_city":"Kullu","distance_from_delhi_km":500,"budget_range":"budget"},

  {"id":"jibhi","name":"Jibhi","state":"Himachal Pradesh","region":"North India",
   "lat":31.5933,"lon":77.4619,"vibes":["mountains","offbeat","nature","honeymoon"],
   "primary_vibe":"mountains","avg_cost_budget":1000,"avg_cost_mid":2000,"avg_cost_luxury":4000,
   "min_days":2,"max_days":5,"best_months":[4,5,6,9,10],"popularity":5.5,
   "group_suitability":{"solo":0.85,"couple":0.95,"friends":0.8,"family":0.7},
   "nearest_airport":"Bhuntar Airport (60 km)","nearest_railway":"Chandigarh Junction (270 km)",
   "nearest_major_city":"Kullu","distance_from_delhi_km":510,"budget_range":"budget"},

  {"id":"dalhousie","name":"Dalhousie","state":"Himachal Pradesh","region":"North India",
   "lat":32.5388,"lon":75.9735,"vibes":["mountains","heritage","honeymoon","nature","colonial"],
   "primary_vibe":"mountains","avg_cost_budget":1200,"avg_cost_mid":2500,"avg_cost_luxury":5000,
   "min_days":2,"max_days":5,"best_months":[3,4,5,9,10,11],"popularity":7.0,
   "group_suitability":{"solo":0.75,"couple":0.9,"friends":0.75,"family":0.85},
   "nearest_airport":"Gaggal Airport, Kangra (80 km)","nearest_railway":"Pathankot Junction (80 km)",
   "nearest_major_city":"Pathankot","distance_from_delhi_km":555,"budget_range":"budget"},

  {"id":"khajjiar","name":"Khajjiar","state":"Himachal Pradesh","region":"North India",
   "lat":32.5404,"lon":76.0621,"vibes":["mountains","nature","offbeat"],
   "primary_vibe":"mountains","avg_cost_budget":1000,"avg_cost_mid":2000,"avg_cost_luxury":3500,
   "min_days":1,"max_days":3,"best_months":[3,4,5,9,10,11],"popularity":6.5,
   "group_suitability":{"solo":0.7,"couple":0.85,"friends":0.8,"family":0.85},
   "nearest_airport":"Gaggal Airport, Kangra (100 km)","nearest_railway":"Pathankot (110 km)",
   "nearest_major_city":"Dalhousie","distance_from_delhi_km":570,"budget_range":"budget"},

  {"id":"kalpa","name":"Kalpa","state":"Himachal Pradesh","region":"North India",
   "lat":31.5307,"lon":78.2599,"vibes":["mountains","offbeat","trekking","nature"],
   "primary_vibe":"mountains","avg_cost_budget":1000,"avg_cost_mid":2000,"avg_cost_luxury":3500,
   "min_days":2,"max_days":5,"best_months":[4,5,6,9,10],"popularity":5.5,
   "group_suitability":{"solo":0.9,"couple":0.8,"friends":0.8,"family":0.6},
   "nearest_airport":"Shimla Airport (244 km)","nearest_railway":"Shimla (244 km)",
   "nearest_major_city":"Shimla","distance_from_delhi_km":590,"budget_range":"budget"},

  # ── Jammu & Kashmir ────────────────────────────────────────────────────────
  {"id":"srinagar","name":"Srinagar","state":"Jammu & Kashmir (UT)","region":"North India",
   "lat":34.0837,"lon":74.7973,"vibes":["mountains","heritage","nature","honeymoon","spiritual"],
   "primary_vibe":"mountains","avg_cost_budget":1800,"avg_cost_mid":3500,"avg_cost_luxury":8000,
   "min_days":4,"max_days":8,"best_months":[4,5,6,9,10],"popularity":9.0,
   "group_suitability":{"solo":0.75,"couple":0.95,"friends":0.85,"family":0.8},
   "nearest_airport":"Sheikh ul Alam Airport (14 km)","nearest_railway":"Banihal (100 km)",
   "nearest_major_city":"Jammu","distance_from_delhi_km":876,"budget_range":"medium"},

  {"id":"gulmarg","name":"Gulmarg","state":"Jammu & Kashmir (UT)","region":"North India",
   "lat":34.0500,"lon":74.3833,"vibes":["mountains","adventure","snow","honeymoon","skiing"],
   "primary_vibe":"mountains","avg_cost_budget":2000,"avg_cost_mid":4000,"avg_cost_luxury":9000,
   "min_days":2,"max_days":5,"best_months":[12,1,2,3,4,5,9,10],"popularity":8.5,
   "group_suitability":{"solo":0.75,"couple":0.9,"friends":0.85,"family":0.75},
   "nearest_airport":"Sheikh ul Alam Airport, Srinagar (56 km)","nearest_railway":"Banihal (160 km)",
   "nearest_major_city":"Srinagar","distance_from_delhi_km":876,"budget_range":"medium"},

  {"id":"pahalgam","name":"Pahalgam","state":"Jammu & Kashmir (UT)","region":"North India",
   "lat":34.0161,"lon":75.3150,"vibes":["mountains","nature","trekking","honeymoon","adventure"],
   "primary_vibe":"mountains","avg_cost_budget":1500,"avg_cost_mid":3000,"avg_cost_luxury":7000,
   "min_days":3,"max_days":6,"best_months":[4,5,6,9,10],"popularity":8.5,
   "group_suitability":{"solo":0.8,"couple":0.9,"friends":0.85,"family":0.8},
   "nearest_airport":"Sheikh ul Alam Airport, Srinagar (95 km)","nearest_railway":"Anantnag (45 km)",
   "nearest_major_city":"Srinagar","distance_from_delhi_km":930,"budget_range":"medium"},

  {"id":"vaishno-devi","name":"Vaishno Devi (Katra)","state":"Jammu & Kashmir (UT)","region":"North India",
   "lat":32.9919,"lon":74.9474,"vibes":["spiritual","pilgrimage","mountains","trekking"],
   "primary_vibe":"spiritual","avg_cost_budget":1000,"avg_cost_mid":2000,"avg_cost_luxury":4000,
   "min_days":2,"max_days":4,"best_months":[3,4,5,9,10,11,12,1,2],"popularity":9.5,
   "group_suitability":{"solo":0.75,"couple":0.8,"friends":0.75,"family":0.95},
   "nearest_airport":"Jammu Airport (50 km)","nearest_railway":"Katra Railway Station (1 km)",
   "nearest_major_city":"Jammu","distance_from_delhi_km":670,"budget_range":"budget"},

  # ── Rajasthan (niche) ──────────────────────────────────────────────────────
  {"id":"bundi","name":"Bundi","state":"Rajasthan","region":"West India",
   "lat":25.4382,"lon":75.6476,"vibes":["heritage","offbeat","photography"],
   "primary_vibe":"heritage","avg_cost_budget":800,"avg_cost_mid":1500,"avg_cost_luxury":3000,
   "min_days":1,"max_days":3,"best_months":[10,11,12,1,2,3],"popularity":5.5,
   "group_suitability":{"solo":0.9,"couple":0.8,"friends":0.75,"family":0.7},
   "nearest_airport":"Kota Airport (35 km)","nearest_railway":"Bundi Railway Station (1 km)",
   "nearest_major_city":"Kota","distance_from_delhi_km":455,"budget_range":"budget"},

  {"id":"bikaner","name":"Bikaner","state":"Rajasthan","region":"West India",
   "lat":28.0229,"lon":73.3119,"vibes":["heritage","desert","offbeat"],
   "primary_vibe":"heritage","avg_cost_budget":900,"avg_cost_mid":1800,"avg_cost_luxury":3500,
   "min_days":1,"max_days":3,"best_months":[10,11,12,1,2,3],"popularity":7.0,
   "group_suitability":{"solo":0.8,"couple":0.75,"friends":0.75,"family":0.8},
   "nearest_airport":"Nal Airport (13 km)","nearest_railway":"Bikaner Junction (2 km)",
   "nearest_major_city":"Jaipur","distance_from_delhi_km":435,"budget_range":"budget"},

  {"id":"mount-abu","name":"Mount Abu","state":"Rajasthan","region":"West India",
   "lat":24.5926,"lon":72.7156,"vibes":["mountains","spiritual","heritage","nature","honeymoon"],
   "primary_vibe":"mountains","avg_cost_budget":1000,"avg_cost_mid":2000,"avg_cost_luxury":4000,
   "min_days":2,"max_days":4,"best_months":[10,11,12,1,2,3],"popularity":7.5,
   "group_suitability":{"solo":0.75,"couple":0.9,"friends":0.75,"family":0.85},
   "nearest_airport":"Udaipur Airport (175 km)","nearest_railway":"Abu Road (28 km)",
   "nearest_major_city":"Udaipur","distance_from_delhi_km":685,"budget_range":"budget"},

  {"id":"chittorgarh","name":"Chittorgarh","state":"Rajasthan","region":"West India",
   "lat":24.8887,"lon":74.6270,"vibes":["heritage","offbeat","spiritual"],
   "primary_vibe":"heritage","avg_cost_budget":800,"avg_cost_mid":1600,"avg_cost_luxury":3000,
   "min_days":1,"max_days":2,"best_months":[10,11,12,1,2,3],"popularity":7.0,
   "group_suitability":{"solo":0.8,"couple":0.75,"friends":0.75,"family":0.8},
   "nearest_airport":"Udaipur Airport (115 km)","nearest_railway":"Chittorgarh Junction (1 km)",
   "nearest_major_city":"Udaipur","distance_from_delhi_km":590,"budget_range":"budget"},

  # ── Karnataka (niche) ──────────────────────────────────────────────────────
  {"id":"chikmagalur","name":"Chikmagalur","state":"Karnataka","region":"South India",
   "lat":13.3161,"lon":75.7720,"vibes":["nature","mountains","wildlife","offbeat","coffee"],
   "primary_vibe":"nature","avg_cost_budget":1200,"avg_cost_mid":2500,"avg_cost_luxury":5500,
   "min_days":2,"max_days":5,"best_months":[9,10,11,12,1,2,3],"popularity":7.5,
   "group_suitability":{"solo":0.85,"couple":0.9,"friends":0.85,"family":0.8},
   "nearest_airport":"Mangalore Airport (130 km)","nearest_railway":"Kadur (40 km)",
   "nearest_major_city":"Mangalore","distance_from_delhi_km":1740,"budget_range":"budget"},

  {"id":"sakleshpur","name":"Sakleshpur","state":"Karnataka","region":"South India",
   "lat":12.9424,"lon":75.7855,"vibes":["nature","offbeat","trekking","mountains"],
   "primary_vibe":"nature","avg_cost_budget":1000,"avg_cost_mid":2000,"avg_cost_luxury":4000,
   "min_days":2,"max_days":4,"best_months":[9,10,11,12,1,2,3],"popularity":6.0,
   "group_suitability":{"solo":0.8,"couple":0.85,"friends":0.85,"family":0.75},
   "nearest_airport":"Mangalore Airport (150 km)","nearest_railway":"Sakleshpur (2 km)",
   "nearest_major_city":"Hassan","distance_from_delhi_km":1780,"budget_range":"budget"},

  {"id":"badami","name":"Badami","state":"Karnataka","region":"South India",
   "lat":15.9182,"lon":75.6807,"vibes":["heritage","offbeat","spiritual"],
   "primary_vibe":"heritage","avg_cost_budget":800,"avg_cost_mid":1500,"avg_cost_luxury":3000,
   "min_days":1,"max_days":3,"best_months":[10,11,12,1,2,3],"popularity":6.5,
   "group_suitability":{"solo":0.85,"couple":0.75,"friends":0.8,"family":0.75},
   "nearest_airport":"Hubli Airport (108 km)","nearest_railway":"Badami (2 km)",
   "nearest_major_city":"Hubli","distance_from_delhi_km":1580,"budget_range":"budget"},

  {"id":"kabini","name":"Kabini","state":"Karnataka","region":"South India",
   "lat":11.9333,"lon":76.4167,"vibes":["wildlife","nature","offbeat","adventure"],
   "primary_vibe":"wildlife","avg_cost_budget":2000,"avg_cost_mid":4000,"avg_cost_luxury":12000,
   "min_days":2,"max_days":4,"best_months":[10,11,12,1,2,3,4,5],"popularity":7.5,
   "group_suitability":{"solo":0.75,"couple":0.85,"friends":0.8,"family":0.75},
   "nearest_airport":"Mysore Airport (100 km)","nearest_railway":"Mysore Junction (80 km)",
   "nearest_major_city":"Mysore","distance_from_delhi_km":1900,"budget_range":"luxury"},

  # ── Maharashtra (niche) ────────────────────────────────────────────────────
  {"id":"mahabaleshwar","name":"Mahabaleshwar","state":"Maharashtra","region":"West India",
   "lat":17.9237,"lon":73.6571,"vibes":["mountains","nature","honeymoon","heritage"],
   "primary_vibe":"mountains","avg_cost_budget":1500,"avg_cost_mid":3000,"avg_cost_luxury":6000,
   "min_days":2,"max_days":4,"best_months":[10,11,12,1,2,3,4],"popularity":8.0,
   "group_suitability":{"solo":0.7,"couple":0.9,"friends":0.8,"family":0.85},
   "nearest_airport":"Pune Airport (120 km)","nearest_railway":"Wathar (60 km)",
   "nearest_major_city":"Pune","distance_from_delhi_km":1190,"budget_range":"medium"},

  {"id":"lonavala","name":"Lonavala","state":"Maharashtra","region":"West India",
   "lat":18.7481,"lon":73.4072,"vibes":["mountains","nature","offbeat","adventure"],
   "primary_vibe":"mountains","avg_cost_budget":1200,"avg_cost_mid":2500,"avg_cost_luxury":5000,
   "min_days":1,"max_days":3,"best_months":[7,8,9,10,11,12,1,2],"popularity":7.5,
   "group_suitability":{"solo":0.7,"couple":0.85,"friends":0.9,"family":0.8},
   "nearest_airport":"Pune Airport (65 km)","nearest_railway":"Lonavala Station (1 km)",
   "nearest_major_city":"Pune","distance_from_delhi_km":1370,"budget_range":"budget"},

  {"id":"aurangabad","name":"Aurangabad","state":"Maharashtra","region":"West India",
   "lat":19.8762,"lon":75.3433,"vibes":["heritage","spiritual","offbeat"],
   "primary_vibe":"heritage","avg_cost_budget":1000,"avg_cost_mid":2000,"avg_cost_luxury":4000,
   "min_days":2,"max_days":4,"best_months":[10,11,12,1,2,3],"popularity":7.5,
   "group_suitability":{"solo":0.8,"couple":0.75,"friends":0.8,"family":0.8},
   "nearest_airport":"Aurangabad Airport (10 km)","nearest_railway":"Aurangabad Station (5 km)",
   "nearest_major_city":"Pune","distance_from_delhi_km":1200,"budget_range":"budget"},

  # ── Madhya Pradesh (niche) ─────────────────────────────────────────────────
  {"id":"pachmarhi","name":"Pachmarhi","state":"Madhya Pradesh","region":"Central India",
   "lat":22.4676,"lon":78.4340,"vibes":["nature","mountains","offbeat","spiritual"],
   "primary_vibe":"nature","avg_cost_budget":1000,"avg_cost_mid":2000,"avg_cost_luxury":4000,
   "min_days":2,"max_days":4,"best_months":[10,11,12,1,2,3],"popularity":6.5,
   "group_suitability":{"solo":0.8,"couple":0.85,"friends":0.8,"family":0.85},
   "nearest_airport":"Bhopal Airport (210 km)","nearest_railway":"Pipariya (47 km)",
   "nearest_major_city":"Bhopal","distance_from_delhi_km":780,"budget_range":"budget"},

  {"id":"kanha","name":"Kanha National Park","state":"Madhya Pradesh","region":"Central India",
   "lat":22.3361,"lon":80.6113,"vibes":["wildlife","nature","adventure"],
   "primary_vibe":"wildlife","avg_cost_budget":2000,"avg_cost_mid":4000,"avg_cost_luxury":10000,
   "min_days":2,"max_days":5,"best_months":[10,11,12,1,2,3,4,5],"popularity":8.0,
   "group_suitability":{"solo":0.75,"couple":0.8,"friends":0.8,"family":0.75},
   "nearest_airport":"Jabalpur Airport (160 km)","nearest_railway":"Jabalpur (175 km)",
   "nearest_major_city":"Jabalpur","distance_from_delhi_km":1040,"budget_range":"medium"},

  {"id":"mandu","name":"Mandu","state":"Madhya Pradesh","region":"Central India",
   "lat":22.3404,"lon":75.3940,"vibes":["heritage","offbeat","spiritual"],
   "primary_vibe":"heritage","avg_cost_budget":700,"avg_cost_mid":1500,"avg_cost_luxury":3000,
   "min_days":1,"max_days":3,"best_months":[10,11,12,1,2,3],"popularity":6.0,
   "group_suitability":{"solo":0.85,"couple":0.75,"friends":0.75,"family":0.75},
   "nearest_airport":"Indore Airport (100 km)","nearest_railway":"Indore Junction (100 km)",
   "nearest_major_city":"Indore","distance_from_delhi_km":870,"budget_range":"budget"},

  # ── Kerala (more) ──────────────────────────────────────────────────────────
  {"id":"wayanad","name":"Wayanad","state":"Kerala","region":"South India",
   "lat":11.6854,"lon":76.1320,"vibes":["nature","wildlife","mountains","offbeat"],
   "primary_vibe":"nature","avg_cost_budget":1200,"avg_cost_mid":2500,"avg_cost_luxury":5000,
   "min_days":2,"max_days":5,"best_months":[10,11,12,1,2,3],"popularity":8.0,
   "group_suitability":{"solo":0.8,"couple":0.9,"friends":0.85,"family":0.8},
   "nearest_airport":"Calicut International Airport (85 km)","nearest_railway":"Kozhikode (76 km)",
   "nearest_major_city":"Kozhikode","distance_from_delhi_km":2200,"budget_range":"budget"},

  {"id":"kovalam","name":"Kovalam","state":"Kerala","region":"South India",
   "lat":8.3988,"lon":76.9784,"vibes":["beach","honeymoon","nature","spiritual"],
   "primary_vibe":"beach","avg_cost_budget":1200,"avg_cost_mid":2500,"avg_cost_luxury":6000,
   "min_days":2,"max_days":5,"best_months":[10,11,12,1,2,3,4],"popularity":8.0,
   "group_suitability":{"solo":0.75,"couple":0.95,"friends":0.75,"family":0.75},
   "nearest_airport":"Trivandrum International Airport (16 km)","nearest_railway":"Trivandrum Central (14 km)",
   "nearest_major_city":"Thiruvananthapuram","distance_from_delhi_km":2200,"budget_range":"medium"},

  {"id":"thekkady","name":"Thekkady (Periyar)","state":"Kerala","region":"South India",
   "lat":9.5946,"lon":77.1611,"vibes":["wildlife","nature","adventure","offbeat"],
   "primary_vibe":"wildlife","avg_cost_budget":1500,"avg_cost_mid":3000,"avg_cost_luxury":7000,
   "min_days":2,"max_days":4,"best_months":[10,11,12,1,2,3,4,5],"popularity":8.0,
   "group_suitability":{"solo":0.8,"couple":0.85,"friends":0.8,"family":0.8},
   "nearest_airport":"Madurai Airport (136 km)","nearest_railway":"Kottayam (114 km)",
   "nearest_major_city":"Kottayam","distance_from_delhi_km":2050,"budget_range":"medium"},

  {"id":"kannur","name":"Kannur","state":"Kerala","region":"South India",
   "lat":11.8745,"lon":75.3704,"vibes":["beach","heritage","offbeat","spiritual"],
   "primary_vibe":"beach","avg_cost_budget":1000,"avg_cost_mid":2000,"avg_cost_luxury":4000,
   "min_days":2,"max_days":4,"best_months":[10,11,12,1,2,3],"popularity":6.5,
   "group_suitability":{"solo":0.8,"couple":0.8,"friends":0.75,"family":0.8},
   "nearest_airport":"Calicut Airport (90 km)","nearest_railway":"Kannur Railway Station (2 km)",
   "nearest_major_city":"Kozhikode","distance_from_delhi_km":2350,"budget_range":"budget"},

  # ── Northeast India ─────────────────────────────────────────────────────────
  {"id":"shillong","name":"Shillong","state":"Meghalaya","region":"Northeast India",
   "lat":25.5788,"lon":91.8933,"vibes":["mountains","nature","offbeat","heritage"],
   "primary_vibe":"mountains","avg_cost_budget":1200,"avg_cost_mid":2200,"avg_cost_luxury":4500,
   "min_days":3,"max_days":6,"best_months":[3,4,5,9,10,11],"popularity":7.5,
   "group_suitability":{"solo":0.85,"couple":0.85,"friends":0.9,"family":0.8},
   "nearest_airport":"Shillong Airport (30 km)","nearest_railway":"Guwahati (98 km)",
   "nearest_major_city":"Guwahati","distance_from_delhi_km":1960,"budget_range":"budget"},

  {"id":"cherrapunji","name":"Cherrapunji (Sohra)","state":"Meghalaya","region":"Northeast India",
   "lat":25.2694,"lon":91.7156,"vibes":["nature","offbeat","mountains","adventure"],
   "primary_vibe":"nature","avg_cost_budget":1200,"avg_cost_mid":2200,"avg_cost_luxury":4000,
   "min_days":2,"max_days":4,"best_months":[10,11,12,1,2,3],"popularity":7.0,
   "group_suitability":{"solo":0.85,"couple":0.8,"friends":0.9,"family":0.75},
   "nearest_airport":"Shillong Airport (55 km)","nearest_railway":"Guwahati (150 km)",
   "nearest_major_city":"Shillong","distance_from_delhi_km":1995,"budget_range":"budget"},

  {"id":"dawki","name":"Dawki","state":"Meghalaya","region":"Northeast India",
   "lat":25.1808,"lon":92.0234,"vibes":["nature","offbeat","adventure","backwaters"],
   "primary_vibe":"nature","avg_cost_budget":900,"avg_cost_mid":1800,"avg_cost_luxury":3500,
   "min_days":1,"max_days":3,"best_months":[11,12,1,2,3,4,5],"popularity":6.5,
   "group_suitability":{"solo":0.85,"couple":0.85,"friends":0.9,"family":0.7},
   "nearest_airport":"Shillong Airport (100 km)","nearest_railway":"Guwahati (180 km)",
   "nearest_major_city":"Shillong","distance_from_delhi_km":2000,"budget_range":"budget"},

  {"id":"dzukou-valley","name":"Dzukou Valley","state":"Nagaland","region":"Northeast India",
   "lat":25.5696,"lon":94.2167,"vibes":["trekking","offbeat","nature","mountains"],
   "primary_vibe":"trekking","avg_cost_budget":1000,"avg_cost_mid":2000,"avg_cost_luxury":3500,
   "min_days":3,"max_days":5,"best_months":[6,7,8,9,10],"popularity":5.5,
   "group_suitability":{"solo":0.9,"couple":0.75,"friends":0.9,"family":0.5},
   "nearest_airport":"Dimapur Airport (75 km)","nearest_railway":"Dimapur (75 km)",
   "nearest_major_city":"Kohima","distance_from_delhi_km":2400,"budget_range":"budget"},

  {"id":"dirang","name":"Dirang","state":"Arunachal Pradesh","region":"Northeast India",
   "lat":27.3578,"lon":92.4833,"vibes":["mountains","offbeat","nature","spiritual"],
   "primary_vibe":"mountains","avg_cost_budget":900,"avg_cost_mid":1800,"avg_cost_luxury":3500,
   "min_days":2,"max_days":4,"best_months":[3,4,5,9,10,11],"popularity":5.0,
   "group_suitability":{"solo":0.85,"couple":0.75,"friends":0.85,"family":0.7},
   "nearest_airport":"Tezpur Airport (140 km)","nearest_railway":"Rangapara North (120 km)",
   "nearest_major_city":"Tezpur","distance_from_delhi_km":2100,"budget_range":"budget"},

  # ── Tamil Nadu & South ──────────────────────────────────────────────────────
  {"id":"yercaud","name":"Yercaud","state":"Tamil Nadu","region":"South India",
   "lat":11.7745,"lon":78.2145,"vibes":["mountains","nature","offbeat"],
   "primary_vibe":"nature","avg_cost_budget":900,"avg_cost_mid":1800,"avg_cost_luxury":3500,
   "min_days":2,"max_days":3,"best_months":[10,11,12,1,2,3],"popularity":6.0,
   "group_suitability":{"solo":0.75,"couple":0.85,"friends":0.75,"family":0.8},
   "nearest_airport":"Tiruchirappalli Airport (110 km)","nearest_railway":"Salem Junction (32 km)",
   "nearest_major_city":"Salem","distance_from_delhi_km":2190,"budget_range":"budget"},

  {"id":"valparai","name":"Valparai","state":"Tamil Nadu","region":"South India",
   "lat":10.3268,"lon":76.9557,"vibes":["nature","wildlife","offbeat","mountains"],
   "primary_vibe":"nature","avg_cost_budget":1000,"avg_cost_mid":2000,"avg_cost_luxury":4000,
   "min_days":2,"max_days":4,"best_months":[10,11,12,1,2,3,4],"popularity":6.0,
   "group_suitability":{"solo":0.85,"couple":0.85,"friends":0.8,"family":0.75},
   "nearest_airport":"Coimbatore Airport (115 km)","nearest_railway":"Pollachi (64 km)",
   "nearest_major_city":"Coimbatore","distance_from_delhi_km":2200,"budget_range":"budget"},

  {"id":"chettinad","name":"Chettinad","state":"Tamil Nadu","region":"South India",
   "lat":10.1833,"lon":78.8833,"vibes":["heritage","offbeat","food"],
   "primary_vibe":"heritage","avg_cost_budget":1200,"avg_cost_mid":2500,"avg_cost_luxury":5000,
   "min_days":2,"max_days":3,"best_months":[10,11,12,1,2,3],"popularity":6.5,
   "group_suitability":{"solo":0.8,"couple":0.8,"friends":0.75,"family":0.8},
   "nearest_airport":"Madurai Airport (90 km)","nearest_railway":"Karaikudi (14 km)",
   "nearest_major_city":"Madurai","distance_from_delhi_km":2200,"budget_range":"medium"},

  # ── Gujarat ─────────────────────────────────────────────────────────────────
  {"id":"gir","name":"Gir National Park","state":"Gujarat","region":"West India",
   "lat":21.1315,"lon":70.8234,"vibes":["wildlife","nature","adventure"],
   "primary_vibe":"wildlife","avg_cost_budget":1500,"avg_cost_mid":3000,"avg_cost_luxury":7000,
   "min_days":2,"max_days":4,"best_months":[11,12,1,2,3,4,5],"popularity":8.0,
   "group_suitability":{"solo":0.75,"couple":0.8,"friends":0.8,"family":0.8},
   "nearest_airport":"Rajkot Airport (160 km)","nearest_railway":"Junagadh (65 km)",
   "nearest_major_city":"Junagadh","distance_from_delhi_km":1150,"budget_range":"medium"},

  {"id":"saputara","name":"Saputara","state":"Gujarat","region":"West India",
   "lat":20.5792,"lon":73.7456,"vibes":["mountains","nature","offbeat"],
   "primary_vibe":"mountains","avg_cost_budget":900,"avg_cost_mid":1800,"avg_cost_luxury":3500,
   "min_days":2,"max_days":3,"best_months":[10,11,12,1,2,3],"popularity":6.0,
   "group_suitability":{"solo":0.7,"couple":0.85,"friends":0.75,"family":0.85},
   "nearest_airport":"Surat Airport (170 km)","nearest_railway":"Wagad (56 km)",
   "nearest_major_city":"Surat","distance_from_delhi_km":1210,"budget_range":"budget"},

  # ── Odisha ──────────────────────────────────────────────────────────────────
  {"id":"chilika","name":"Chilika Lake","state":"Odisha","region":"East India",
   "lat":19.7272,"lon":85.3190,"vibes":["nature","wildlife","offbeat","backwaters"],
   "primary_vibe":"nature","avg_cost_budget":800,"avg_cost_mid":1600,"avg_cost_luxury":3000,
   "min_days":1,"max_days":3,"best_months":[11,12,1,2],"popularity":6.5,
   "group_suitability":{"solo":0.8,"couple":0.75,"friends":0.75,"family":0.8},
   "nearest_airport":"Bhubaneswar Airport (100 km)","nearest_railway":"Balugaon (2 km)",
   "nearest_major_city":"Bhubaneswar","distance_from_delhi_km":1480,"budget_range":"budget"},

  {"id":"konark","name":"Konark","state":"Odisha","region":"East India",
   "lat":19.8876,"lon":86.0945,"vibes":["heritage","spiritual","beach","offbeat"],
   "primary_vibe":"heritage","avg_cost_budget":700,"avg_cost_mid":1400,"avg_cost_luxury":3000,
   "min_days":1,"max_days":2,"best_months":[10,11,12,1,2,3],"popularity":8.0,
   "group_suitability":{"solo":0.8,"couple":0.75,"friends":0.8,"family":0.8},
   "nearest_airport":"Bhubaneswar Airport (65 km)","nearest_railway":"Puri (35 km)",
   "nearest_major_city":"Bhubaneswar","distance_from_delhi_km":1510,"budget_range":"budget"},

  # ── West Bengal ─────────────────────────────────────────────────────────────
  {"id":"kalimpong","name":"Kalimpong","state":"West Bengal","region":"East India",
   "lat":27.0660,"lon":88.4677,"vibes":["mountains","offbeat","heritage","nature"],
   "primary_vibe":"mountains","avg_cost_budget":1000,"avg_cost_mid":2000,"avg_cost_luxury":4000,
   "min_days":2,"max_days":5,"best_months":[3,4,5,9,10,11],"popularity":6.5,
   "group_suitability":{"solo":0.85,"couple":0.85,"friends":0.8,"family":0.8},
   "nearest_airport":"Bagdogra Airport (79 km)","nearest_railway":"New Jalpaiguri (67 km)",
   "nearest_major_city":"Siliguri","distance_from_delhi_km":1690,"budget_range":"budget"},

  {"id":"mandarmani","name":"Mandarmani","state":"West Bengal","region":"East India",
   "lat":21.6659,"lon":87.7193,"vibes":["beach","offbeat","nature"],
   "primary_vibe":"beach","avg_cost_budget":900,"avg_cost_mid":1800,"avg_cost_luxury":3500,
   "min_days":2,"max_days":3,"best_months":[10,11,12,1,2,3],"popularity":6.0,
   "group_suitability":{"solo":0.7,"couple":0.85,"friends":0.85,"family":0.75},
   "nearest_airport":"Netaji Subhas Airport, Kolkata (180 km)","nearest_railway":"Contai (30 km)",
   "nearest_major_city":"Kolkata","distance_from_delhi_km":1600,"budget_range":"budget"},

  # ── Andhra Pradesh ──────────────────────────────────────────────────────────
  {"id":"araku-valley","name":"Araku Valley","state":"Andhra Pradesh","region":"South India",
   "lat":18.3301,"lon":82.8828,"vibes":["mountains","nature","offbeat","tribal"],
   "primary_vibe":"nature","avg_cost_budget":1000,"avg_cost_mid":2000,"avg_cost_luxury":3500,
   "min_days":2,"max_days":4,"best_months":[10,11,12,1,2,3],"popularity":7.0,
   "group_suitability":{"solo":0.8,"couple":0.8,"friends":0.85,"family":0.8},
   "nearest_airport":"Visakhapatnam Airport (115 km)","nearest_railway":"Araku (1 km)",
   "nearest_major_city":"Visakhapatnam","distance_from_delhi_km":1700,"budget_range":"budget"},

  {"id":"vizag","name":"Visakhapatnam (Vizag)","state":"Andhra Pradesh","region":"South India",
   "lat":17.6868,"lon":83.2185,"vibes":["beach","nature","heritage","adventure"],
   "primary_vibe":"beach","avg_cost_budget":1200,"avg_cost_mid":2300,"avg_cost_luxury":4500,
   "min_days":2,"max_days":5,"best_months":[10,11,12,1,2,3],"popularity":8.0,
   "group_suitability":{"solo":0.8,"couple":0.85,"friends":0.85,"family":0.85},
   "nearest_airport":"Visakhapatnam Airport (15 km)","nearest_railway":"Visakhapatnam Junction (5 km)",
   "nearest_major_city":"Visakhapatnam","distance_from_delhi_km":1600,"budget_range":"budget"},

  # ── Chhattisgarh / Jharkhand ─────────────────────────────────────────────────
  {"id":"jagdalpur","name":"Jagdalpur (Bastar)","state":"Chhattisgarh","region":"Central India",
   "lat":19.0868,"lon":82.0161,"vibes":["nature","offbeat","tribal","wildlife"],
   "primary_vibe":"offbeat","avg_cost_budget":700,"avg_cost_mid":1400,"avg_cost_luxury":2800,
   "min_days":3,"max_days":6,"best_months":[10,11,12,1,2,3],"popularity":5.5,
   "group_suitability":{"solo":0.85,"couple":0.7,"friends":0.85,"family":0.7},
   "nearest_airport":"Jagdalpur Airport (8 km)","nearest_railway":"Jagdalpur (5 km)",
   "nearest_major_city":"Raipur","distance_from_delhi_km":1200,"budget_range":"budget"},

  # ── Sikkim (more) ─────────────────────────────────────────────────────────────
  {"id":"pelling","name":"Pelling","state":"Sikkim","region":"Northeast India",
   "lat":27.2978,"lon":88.1070,"vibes":["mountains","spiritual","nature","offbeat","trekking"],
   "primary_vibe":"mountains","avg_cost_budget":1200,"avg_cost_mid":2500,"avg_cost_luxury":5000,
   "min_days":2,"max_days":5,"best_months":[3,4,5,9,10,11],"popularity":7.0,
   "group_suitability":{"solo":0.8,"couple":0.9,"friends":0.8,"family":0.8},
   "nearest_airport":"Bagdogra Airport (148 km)","nearest_railway":"New Jalpaiguri (149 km)",
   "nearest_major_city":"Siliguri","distance_from_delhi_km":1780,"budget_range":"budget"},

  {"id":"lachung","name":"Lachung","state":"Sikkim","region":"Northeast India",
   "lat":27.6872,"lon":88.7440,"vibes":["mountains","nature","offbeat","snow"],
   "primary_vibe":"mountains","avg_cost_budget":1500,"avg_cost_mid":3000,"avg_cost_luxury":6000,
   "min_days":2,"max_days":4,"best_months":[3,4,5,9,10],"popularity":7.0,
   "group_suitability":{"solo":0.75,"couple":0.85,"friends":0.85,"family":0.8},
   "nearest_airport":"Bagdogra Airport (200 km)","nearest_railway":"New Jalpaiguri (200 km)",
   "nearest_major_city":"Gangtok","distance_from_delhi_km":1860,"budget_range":"medium"},

  # ── Punjab / Haryana ───────────────────────────────────────────────────────
  {"id":"chandigarh","name":"Chandigarh","state":"Punjab/Haryana","region":"North India",
   "lat":30.7333,"lon":76.7794,"vibes":["heritage","nature","offbeat"],
   "primary_vibe":"heritage","avg_cost_budget":1200,"avg_cost_mid":2500,"avg_cost_luxury":5000,
   "min_days":1,"max_days":3,"best_months":[10,11,12,1,2,3],"popularity":7.0,
   "group_suitability":{"solo":0.8,"couple":0.8,"friends":0.8,"family":0.8},
   "nearest_airport":"Chandigarh Airport (13 km)","nearest_railway":"Chandigarh Station (8 km)",
   "nearest_major_city":"Chandigarh","distance_from_delhi_km":250,"budget_range":"medium"},

  # ── Telangana ─────────────────────────────────────────────────────────────
  {"id":"warangal","name":"Warangal","state":"Telangana","region":"South India",
   "lat":17.9689,"lon":79.5941,"vibes":["heritage","offbeat","spiritual"],
   "primary_vibe":"heritage","avg_cost_budget":800,"avg_cost_mid":1600,"avg_cost_luxury":3000,
   "min_days":1,"max_days":3,"best_months":[10,11,12,1,2,3],"popularity":6.0,
   "group_suitability":{"solo":0.8,"couple":0.7,"friends":0.75,"family":0.75},
   "nearest_airport":"Rajiv Gandhi Intl Airport, Hyderabad (150 km)","nearest_railway":"Warangal (2 km)",
   "nearest_major_city":"Hyderabad","distance_from_delhi_km":1450,"budget_range":"budget"},

  # ── Assam (more) ────────────────────────────────────────────────────────────
  {"id":"haflong","name":"Haflong","state":"Assam","region":"Northeast India",
   "lat":25.1654,"lon":93.0156,"vibes":["mountains","nature","offbeat"],
   "primary_vibe":"nature","avg_cost_budget":800,"avg_cost_mid":1600,"avg_cost_luxury":3000,
   "min_days":2,"max_days":4,"best_months":[10,11,12,1,2,3,4],"popularity":4.5,
   "group_suitability":{"solo":0.85,"couple":0.75,"friends":0.8,"family":0.7},
   "nearest_airport":"Silchar Airport (79 km)","nearest_railway":"Haflong Hill (2 km)",
   "nearest_major_city":"Silchar","distance_from_delhi_km":1900,"budget_range":"budget"},

  # ── Madhya Pradesh (more) ──────────────────────────────────────────────────
  {"id":"pench","name":"Pench National Park","state":"Madhya Pradesh","region":"Central India",
   "lat":21.6833,"lon":79.3000,"vibes":["wildlife","nature","adventure"],
   "primary_vibe":"wildlife","avg_cost_budget":1800,"avg_cost_mid":3500,"avg_cost_luxury":9000,
   "min_days":2,"max_days":4,"best_months":[10,11,12,1,2,3,4,5],"popularity":7.5,
   "group_suitability":{"solo":0.75,"couple":0.8,"friends":0.8,"family":0.75},
   "nearest_airport":"Nagpur Airport (90 km)","nearest_railway":"Seoni (32 km)",
   "nearest_major_city":"Nagpur","distance_from_delhi_km":1100,"budget_range":"medium"},

  {"id":"gwalior","name":"Gwalior","state":"Madhya Pradesh","region":"Central India",
   "lat":26.2183,"lon":78.1828,"vibes":["heritage","spiritual","offbeat"],
   "primary_vibe":"heritage","avg_cost_budget":900,"avg_cost_mid":1800,"avg_cost_luxury":3500,
   "min_days":1,"max_days":3,"best_months":[10,11,12,1,2,3],"popularity":7.0,
   "group_suitability":{"solo":0.8,"couple":0.75,"friends":0.75,"family":0.8},
   "nearest_airport":"Rajmata Vijaya Raje Scindia Airport (10 km)","nearest_railway":"Gwalior Junction (3 km)",
   "nearest_major_city":"Agra","distance_from_delhi_km":321,"budget_range":"budget"},

  # ── Himachal (more) ───────────────────────────────────────────────────────
  {"id":"kheerganga","name":"Kheerganga","state":"Himachal Pradesh","region":"North India",
   "lat":32.0765,"lon":77.3547,"vibes":["trekking","offbeat","spiritual","nature"],
   "primary_vibe":"trekking","avg_cost_budget":800,"avg_cost_mid":1500,"avg_cost_luxury":2500,
   "min_days":2,"max_days":4,"best_months":[5,6,7,8,9],"popularity":7.0,
   "group_suitability":{"solo":0.95,"couple":0.75,"friends":0.95,"family":0.4},
   "nearest_airport":"Bhuntar Airport (22 km)","nearest_railway":"Chandigarh (255 km)",
   "nearest_major_city":"Kullu","distance_from_delhi_km":535,"budget_range":"budget"},

  {"id":"narkanda","name":"Narkanda","state":"Himachal Pradesh","region":"North India",
   "lat":31.2660,"lon":77.4544,"vibes":["mountains","nature","offbeat","snow","skiing"],
   "primary_vibe":"mountains","avg_cost_budget":1000,"avg_cost_mid":2000,"avg_cost_luxury":4000,
   "min_days":2,"max_days":4,"best_months":[12,1,2,3,4,5,9,10,11],"popularity":5.5,
   "group_suitability":{"solo":0.75,"couple":0.85,"friends":0.8,"family":0.8},
   "nearest_airport":"Shimla Airport (68 km)","nearest_railway":"Shimla (65 km)",
   "nearest_major_city":"Shimla","distance_from_delhi_km":415,"budget_range":"budget"},

  {"id":"sangla-valley","name":"Sangla Valley","state":"Himachal Pradesh","region":"North India",
   "lat":31.4179,"lon":78.2358,"vibes":["mountains","offbeat","trekking","nature"],
   "primary_vibe":"mountains","avg_cost_budget":1000,"avg_cost_mid":2000,"avg_cost_luxury":4000,
   "min_days":3,"max_days":6,"best_months":[5,6,7,9,10],"popularity":6.0,
   "group_suitability":{"solo":0.9,"couple":0.8,"friends":0.85,"family":0.65},
   "nearest_airport":"Shimla Airport (218 km)","nearest_railway":"Shimla (215 km)",
   "nearest_major_city":"Shimla","distance_from_delhi_km":550,"budget_range":"budget"},

  # ── More Beach ──────────────────────────────────────────────────────────────
  {"id":"pondicherry-auroville","name":"Auroville & White Town","state":"Puducherry","region":"South India",
   "lat":11.9345,"lon":79.8083,"vibes":["spiritual","beach","heritage","offbeat"],
   "primary_vibe":"spiritual","avg_cost_budget":1000,"avg_cost_mid":2200,"avg_cost_luxury":5000,
   "min_days":2,"max_days":5,"best_months":[10,11,12,1,2,3],"popularity":7.5,
   "group_suitability":{"solo":0.9,"couple":0.85,"friends":0.75,"family":0.75},
   "nearest_airport":"Chennai Airport (162 km)","nearest_railway":"Pondicherry (5 km)",
   "nearest_major_city":"Chennai","distance_from_delhi_km":2210,"budget_range":"budget"},

  {"id":"tarkarli","name":"Tarkarli","state":"Maharashtra","region":"West India",
   "lat":16.0155,"lon":73.4633,"vibes":["beach","nature","adventure","offbeat"],
   "primary_vibe":"beach","avg_cost_budget":1000,"avg_cost_mid":2000,"avg_cost_luxury":4500,
   "min_days":2,"max_days":4,"best_months":[10,11,12,1,2,3,4],"popularity":6.5,
   "group_suitability":{"solo":0.75,"couple":0.85,"friends":0.85,"family":0.8},
   "nearest_airport":"Goa Airport (150 km)","nearest_railway":"Kudal (35 km)",
   "nearest_major_city":"Goa","distance_from_delhi_km":1530,"budget_range":"budget"},

  {"id":"gokarna","name":"Gokarna","state":"Karnataka","region":"South India",
   "lat":14.5479,"lon":74.3188,"vibes":["beach","spiritual","offbeat","nature"],
   "primary_vibe":"beach","avg_cost_budget":800,"avg_cost_mid":1800,"avg_cost_luxury":4000,
   "min_days":2,"max_days":5,"best_months":[10,11,12,1,2,3,4],"popularity":7.5,
   "group_suitability":{"solo":0.9,"couple":0.8,"friends":0.9,"family":0.65},
   "nearest_airport":"Goa Airport (160 km)","nearest_railway":"Gokarna Road (9 km)",
   "nearest_major_city":"Hubli","distance_from_delhi_km":1660,"budget_range":"budget"},

  # ── Rajasthan (more) ─────────────────────────────────────────────────────
  {"id":"shekhawati","name":"Shekhawati","state":"Rajasthan","region":"West India",
   "lat":28.0000,"lon":75.5000,"vibes":["heritage","offbeat","art","desert"],
   "primary_vibe":"heritage","avg_cost_budget":700,"avg_cost_mid":1500,"avg_cost_luxury":3000,
   "min_days":2,"max_days":4,"best_months":[10,11,12,1,2,3],"popularity":5.5,
   "group_suitability":{"solo":0.85,"couple":0.75,"friends":0.75,"family":0.75},
   "nearest_airport":"Jaipur Airport (165 km)","nearest_railway":"Sikar (10 km)",
   "nearest_major_city":"Jaipur","distance_from_delhi_km":240,"budget_range":"budget"},

  {"id":"baran","name":"Baran (Shahabad)","state":"Rajasthan","region":"West India",
   "lat":25.0993,"lon":76.5225,"vibes":["heritage","offbeat","wildlife"],
   "primary_vibe":"offbeat","avg_cost_budget":700,"avg_cost_mid":1400,"avg_cost_luxury":2800,
   "min_days":1,"max_days":3,"best_months":[10,11,12,1,2,3],"popularity":4.0,
   "group_suitability":{"solo":0.8,"couple":0.65,"friends":0.75,"family":0.7},
   "nearest_airport":"Kota Airport (77 km)","nearest_railway":"Baran (2 km)",
   "nearest_major_city":"Kota","distance_from_delhi_km":530,"budget_range":"budget"},

  # ── Lakshadweep / Island ───────────────────────────────────────────────────
  {"id":"agatti","name":"Agatti Island","state":"Lakshadweep (UT)","region":"South India",
   "lat":10.8635,"lon":72.1886,"vibes":["beach","nature","offbeat","honeymoon","adventure"],
   "primary_vibe":"beach","avg_cost_budget":3000,"avg_cost_mid":6000,"avg_cost_luxury":15000,
   "min_days":3,"max_days":7,"best_months":[10,11,12,1,2,3,4],"popularity":6.5,
   "group_suitability":{"solo":0.75,"couple":0.95,"friends":0.75,"family":0.7},
   "nearest_airport":"Agatti Aerodrome (2 km)","nearest_railway":"Kochi (459 km by sea)",
   "nearest_major_city":"Kochi","distance_from_delhi_km":2800,"budget_range":"luxury"},

  # ── Madhya Pradesh spiritual ───────────────────────────────────────────────
  {"id":"ujjain","name":"Ujjain","state":"Madhya Pradesh","region":"Central India",
   "lat":23.1765,"lon":75.7885,"vibes":["spiritual","heritage","pilgrimage"],
   "primary_vibe":"spiritual","avg_cost_budget":700,"avg_cost_mid":1400,"avg_cost_luxury":3000,
   "min_days":1,"max_days":3,"best_months":[10,11,12,1,2,3],"popularity":8.0,
   "group_suitability":{"solo":0.75,"couple":0.7,"friends":0.7,"family":0.9},
   "nearest_airport":"Devi Ahilya Bai Airport, Indore (60 km)","nearest_railway":"Ujjain Junction (2 km)",
   "nearest_major_city":"Indore","distance_from_delhi_km":800,"budget_range":"budget"},

  # ── Assam (more) ───────────────────────────────────────────────────────────
  {"id":"bhalukpong","name":"Bhalukpong","state":"Arunachal Pradesh","region":"Northeast India",
   "lat":27.0175,"lon":92.6489,"vibes":["nature","wildlife","offbeat","adventure"],
   "primary_vibe":"nature","avg_cost_budget":900,"avg_cost_mid":1800,"avg_cost_luxury":3500,
   "min_days":2,"max_days":4,"best_months":[10,11,12,1,2,3,4],"popularity":4.5,
   "group_suitability":{"solo":0.85,"couple":0.75,"friends":0.85,"family":0.7},
   "nearest_airport":"Tezpur Airport (50 km)","nearest_railway":"Balipara (40 km)",
   "nearest_major_city":"Tezpur","distance_from_delhi_km":1850,"budget_range":"budget"},

  # ── Telangana ────────────────────────────────────────────────────────────────
  {"id":"hyderabad","name":"Hyderabad","state":"Telangana","region":"South India",
   "lat":17.3850,"lon":78.4867,"vibes":["heritage","food","offbeat","spiritual"],
   "primary_vibe":"heritage","avg_cost_budget":1200,"avg_cost_mid":2500,"avg_cost_luxury":5500,
   "min_days":2,"max_days":5,"best_months":[10,11,12,1,2,3],"popularity":8.5,
   "group_suitability":{"solo":0.85,"couple":0.8,"friends":0.85,"family":0.85},
   "nearest_airport":"Rajiv Gandhi International Airport (22 km)","nearest_railway":"Secunderabad (5 km)",
   "nearest_major_city":"Hyderabad","distance_from_delhi_km":1500,"budget_range":"medium"},

  # ── Uttarakhand (more) ────────────────────────────────────────────────────
  {"id":"binsar","name":"Binsar","state":"Uttarakhand","region":"North India",
   "lat":29.7196,"lon":79.7476,"vibes":["mountains","nature","wildlife","offbeat"],
   "primary_vibe":"mountains","avg_cost_budget":1200,"avg_cost_mid":2500,"avg_cost_luxury":5000,
   "min_days":2,"max_days":4,"best_months":[3,4,5,9,10,11],"popularity":6.0,
   "group_suitability":{"solo":0.85,"couple":0.9,"friends":0.75,"family":0.8},
   "nearest_airport":"Pantnagar Airport (140 km)","nearest_railway":"Kathgodam (105 km)",
   "nearest_major_city":"Almora","distance_from_delhi_km":420,"budget_range":"budget"},

  {"id":"tungnath","name":"Tungnath & Chandrashila","state":"Uttarakhand","region":"North India",
   "lat":30.4833,"lon":79.2333,"vibes":["trekking","spiritual","mountains","nature","offbeat"],
   "primary_vibe":"trekking","avg_cost_budget":1000,"avg_cost_mid":2000,"avg_cost_luxury":3500,
   "min_days":2,"max_days":4,"best_months":[5,6,9,10],"popularity":7.0,
   "group_suitability":{"solo":0.9,"couple":0.75,"friends":0.9,"family":0.6},
   "nearest_airport":"Jolly Grant Airport (230 km)","nearest_railway":"Rishikesh (215 km)",
   "nearest_major_city":"Rishikesh","distance_from_delhi_km":440,"budget_range":"budget"},

  {"id":"chaukori","name":"Chaukori","state":"Uttarakhand","region":"North India",
   "lat":29.8714,"lon":80.4100,"vibes":["mountains","offbeat","nature","tea"],
   "primary_vibe":"mountains","avg_cost_budget":900,"avg_cost_mid":1800,"avg_cost_luxury":3500,
   "min_days":2,"max_days":4,"best_months":[3,4,5,9,10,11],"popularity":5.0,
   "group_suitability":{"solo":0.8,"couple":0.9,"friends":0.75,"family":0.75},
   "nearest_airport":"Naini Saini Airport, Pithoragarh (100 km)","nearest_railway":"Tanakpur (128 km)",
   "nearest_major_city":"Pithoragarh","distance_from_delhi_km":480,"budget_range":"budget"},

  {"id":"bhimtal","name":"Bhimtal","state":"Uttarakhand","region":"North India",
   "lat":29.3449,"lon":79.5684,"vibes":["nature","mountains","offbeat"],
   "primary_vibe":"nature","avg_cost_budget":900,"avg_cost_mid":1800,"avg_cost_luxury":3500,
   "min_days":2,"max_days":3,"best_months":[3,4,5,9,10,11],"popularity":6.0,
   "group_suitability":{"solo":0.75,"couple":0.85,"friends":0.8,"family":0.85},
   "nearest_airport":"Pantnagar Airport (50 km)","nearest_railway":"Kathgodam (23 km)",
   "nearest_major_city":"Nainital","distance_from_delhi_km":300,"budget_range":"budget"},

  {"id":"mukteshwar","name":"Mukteshwar","state":"Uttarakhand","region":"North India",
   "lat":29.4666,"lon":79.6333,"vibes":["mountains","nature","offbeat","spiritual","adventure"],
   "primary_vibe":"mountains","avg_cost_budget":1200,"avg_cost_mid":2500,"avg_cost_luxury":5000,
   "min_days":2,"max_days":4,"best_months":[3,4,5,9,10,11],"popularity":6.5,
   "group_suitability":{"solo":0.8,"couple":0.9,"friends":0.8,"family":0.8},
   "nearest_airport":"Pantnagar Airport (70 km)","nearest_railway":"Kathgodam (50 km)",
   "nearest_major_city":"Nainital","distance_from_delhi_km":340,"budget_range":"budget"},

]

# ---------------------------------------------------------------------------
# LLM fill — description + highlights + food_specialties
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are an expert Indian travel writer. "
    "Return ONLY valid JSON — no markdown, no explanation."
)

JSON_SCHEMA = """{
  "description": "2-3 sentence vivid description of the destination for a traveller",
  "highlights": ["attraction1", "attraction2", "attraction3", "attraction4", "attraction5"],
  "food_specialties": ["dish1", "dish2", "dish3", "dish4"],
  "accommodation": ["type1", "type2", "type3"]
}"""

def _groq_fill(dest: dict, api_key: str) -> dict:
    prompt = (
        f"Destination: {dest['name']}, {dest['state']}\n"
        f"Vibes: {', '.join(dest['vibes'])}\n"
        f"Region: {dest['region']}\n\n"
        f"Return ONLY this JSON (fill with real, accurate info):\n{JSON_SCHEMA}"
    )
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
        "max_tokens": 600,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    with httpx.Client(timeout=30) as client:
        resp = client.post(GROQ_URL, headers=headers, json=payload)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return json.loads(content)


def _template_fill(dest: dict) -> dict:
    return {
        "description": (
            f"{dest['name']} is a {dest['primary_vibe']} destination in {dest['state']}, {dest['region']}. "
            f"Known for its {', '.join(dest['vibes'][:3])} experiences, it is ideal for "
            f"{max(dest['group_suitability'], key=dest['group_suitability'].get)} travellers."
        ),
        "highlights": [f"Explore {dest['name']}", "Local markets", "Scenic viewpoints",
                       "Cultural experiences", "Nature walks"],
        "food_specialties": ["Local thali", "Regional snacks", "Street food", "Traditional sweets"],
        "accommodation": ["hotel", "guesthouse", "homestay"],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-llm",   action="store_true", help="Skip Groq, use template fill")
    parser.add_argument("--dry-run",  action="store_true", help="Print JSON only, don't write")
    parser.add_argument("--only-ids", help="Comma-separated dest IDs to process (for partial runs)")
    args = parser.parse_args()

    with open(DATA_PATH) as f:
        existing = json.load(f)

    existing_ids = {d["id"] for d in existing}

    seeds = NEW_DESTINATIONS
    if args.only_ids:
        wanted = set(args.only_ids.split(","))
        seeds = [d for d in seeds if d["id"] in wanted]

    # Filter out already-existing IDs
    seeds = [d for d in seeds if d["id"] not in existing_ids]
    print(f"\n{len(seeds)} new destinations to add (skipping {len(NEW_DESTINATIONS) - len(seeds)} already present)\n")

    if not seeds:
        print("Nothing to add.")
        return

    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    use_llm  = bool(groq_key) and not args.no_llm

    if use_llm:
        print(f"Using Groq ({GROQ_MODEL}) to fill description + highlights + food\n")
    else:
        print("No GROQ_API_KEY / --no-llm — using template fill\n")

    new_dests = []
    for i, seed in enumerate(seeds, 1):
        print(f"[{i}/{len(seeds)}] {seed['name']}, {seed['state']}...", end=" ", flush=True)
        if use_llm:
            try:
                filled = _groq_fill(seed, groq_key)
                time.sleep(0.4)   # rate limit
                print("OK (Groq)")
            except Exception as e:
                print(f"WARN: Groq failed ({e}), using template")
                filled = _template_fill(seed)
        else:
            filled = _template_fill(seed)
            print("template")

        dest = {
            **seed,
            "description":      filled.get("description", _template_fill(seed)["description"]),
            "highlights":        filled.get("highlights",  _template_fill(seed)["highlights"]),
            "food_specialties":  filled.get("food_specialties", _template_fill(seed)["food_specialties"]),
            "accommodation":     filled.get("accommodation", _template_fill(seed)["accommodation"]),
            "budget_range":      seed.get("budget_range", "medium"),
        }
        new_dests.append(dest)

    if args.dry_run:
        print("\n--- DRY RUN OUTPUT ---")
        print(json.dumps(new_dests, indent=2, ensure_ascii=False))
        return

    combined = existing + new_dests
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2, ensure_ascii=False)

    print(f"\nDone! destinations.json now has {len(combined)} destinations (+{len(new_dests)} new)")
    print("Next step: run  python3 ingest.py --no-wikipedia  to index new destinations quickly")
    print("Or:             python3 ingest.py                 for full Wikipedia enrichment")


if __name__ == "__main__":
    main()
