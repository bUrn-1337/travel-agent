"""
Second batch of destinations — ~55 more.
Focuses on under-represented states and missing major places.
Run after expand_destinations.py.

Usage:
  python3 scripts/expand_destinations_2.py [--dry-run] [--no-llm]
"""
import json, os, sys, time, argparse
from pathlib import Path
import httpx

DATA_PATH  = Path(__file__).parent.parent / "data" / "destinations.json"
GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.1-8b-instant"
SYSTEM     = "Expert Indian travel writer. Return ONLY valid JSON."
SCHEMA     = '{"description":"2-3 vivid sentences","highlights":["attraction1","attraction2","attraction3","attraction4","attraction5"],"food_specialties":["dish1","dish2","dish3","dish4"],"accommodation":["type1","type2","type3"]}'

NEW_DESTINATIONS_2 = [

  # ── Uttar Pradesh ──────────────────────────────────────────────────────────
  {"id":"mathura","name":"Mathura","state":"Uttar Pradesh","region":"North India",
   "lat":27.4924,"lon":77.6737,"vibes":["spiritual","heritage","pilgrimage"],
   "primary_vibe":"spiritual","avg_cost_budget":700,"avg_cost_mid":1500,"avg_cost_luxury":3000,
   "min_days":1,"max_days":3,"best_months":[10,11,12,1,2,3,8],"popularity":8.5,
   "group_suitability":{"solo":0.75,"couple":0.75,"friends":0.7,"family":0.9},
   "nearest_airport":"Agra Airport (60 km)","nearest_railway":"Mathura Junction (2 km)",
   "nearest_major_city":"Agra","distance_from_delhi_km":145,"budget_range":"budget"},

  {"id":"vrindavan","name":"Vrindavan","state":"Uttar Pradesh","region":"North India",
   "lat":27.5794,"lon":77.6969,"vibes":["spiritual","heritage","pilgrimage"],
   "primary_vibe":"spiritual","avg_cost_budget":700,"avg_cost_mid":1400,"avg_cost_luxury":2800,
   "min_days":1,"max_days":2,"best_months":[10,11,12,1,2,3,8],"popularity":8.0,
   "group_suitability":{"solo":0.75,"couple":0.75,"friends":0.7,"family":0.9},
   "nearest_airport":"Agra Airport (65 km)","nearest_railway":"Mathura Junction (10 km)",
   "nearest_major_city":"Mathura","distance_from_delhi_km":150,"budget_range":"budget"},

  {"id":"lucknow","name":"Lucknow","state":"Uttar Pradesh","region":"North India",
   "lat":26.8467,"lon":80.9462,"vibes":["heritage","food","culture","offbeat"],
   "primary_vibe":"heritage","avg_cost_budget":1000,"avg_cost_mid":2200,"avg_cost_luxury":5000,
   "min_days":2,"max_days":4,"best_months":[10,11,12,1,2,3],"popularity":7.5,
   "group_suitability":{"solo":0.8,"couple":0.75,"friends":0.8,"family":0.85},
   "nearest_airport":"Chaudhary Charan Singh Airport (15 km)","nearest_railway":"Lucknow Junction (3 km)",
   "nearest_major_city":"Lucknow","distance_from_delhi_km":497,"budget_range":"budget"},

  {"id":"prayagraj","name":"Prayagraj (Allahabad)","state":"Uttar Pradesh","region":"North India",
   "lat":25.4358,"lon":81.8463,"vibes":["spiritual","heritage","pilgrimage"],
   "primary_vibe":"spiritual","avg_cost_budget":800,"avg_cost_mid":1600,"avg_cost_luxury":3500,
   "min_days":1,"max_days":3,"best_months":[10,11,12,1,2,3],"popularity":8.0,
   "group_suitability":{"solo":0.75,"couple":0.7,"friends":0.7,"family":0.9},
   "nearest_airport":"Bamrauli Airport (12 km)","nearest_railway":"Prayagraj Junction (3 km)",
   "nearest_major_city":"Varanasi","distance_from_delhi_km":635,"budget_range":"budget"},

  {"id":"dudhwa","name":"Dudhwa National Park","state":"Uttar Pradesh","region":"North India",
   "lat":28.3237,"lon":80.6433,"vibes":["wildlife","nature","offbeat","adventure"],
   "primary_vibe":"wildlife","avg_cost_budget":1500,"avg_cost_mid":3000,"avg_cost_luxury":7000,
   "min_days":2,"max_days":4,"best_months":[11,12,1,2,3,4,5],"popularity":6.0,
   "group_suitability":{"solo":0.75,"couple":0.8,"friends":0.8,"family":0.75},
   "nearest_airport":"Lucknow Airport (230 km)","nearest_railway":"Dudhwa (2 km)",
   "nearest_major_city":"Lucknow","distance_from_delhi_km":390,"budget_range":"medium"},

  # ── Goa (more specific) ────────────────────────────────────────────────────
  {"id":"north-goa","name":"North Goa","state":"Goa","region":"West India",
   "lat":15.5524,"lon":73.8272,"vibes":["beach","adventure","heritage","backpacker"],
   "primary_vibe":"beach","avg_cost_budget":1200,"avg_cost_mid":2800,"avg_cost_luxury":7000,
   "min_days":3,"max_days":7,"best_months":[10,11,12,1,2,3],"popularity":9.0,
   "group_suitability":{"solo":0.9,"couple":0.8,"friends":0.95,"family":0.7},
   "nearest_airport":"Dabolim Airport (42 km)","nearest_railway":"Thivim (12 km)",
   "nearest_major_city":"Panaji","distance_from_delhi_km":1905,"budget_range":"medium"},

  {"id":"south-goa","name":"South Goa","state":"Goa","region":"West India",
   "lat":15.1731,"lon":74.0476,"vibes":["beach","nature","honeymoon","offbeat","luxury"],
   "primary_vibe":"beach","avg_cost_budget":1800,"avg_cost_mid":4000,"avg_cost_luxury":10000,
   "min_days":3,"max_days":7,"best_months":[10,11,12,1,2,3],"popularity":8.5,
   "group_suitability":{"solo":0.7,"couple":0.95,"friends":0.75,"family":0.8},
   "nearest_airport":"Dabolim Airport (25 km)","nearest_railway":"Margao (15 km)",
   "nearest_major_city":"Margao","distance_from_delhi_km":1920,"budget_range":"luxury"},

  # ── Andaman (more) ─────────────────────────────────────────────────────────
  {"id":"havelock-island","name":"Havelock Island (Swaraj Dweep)","state":"Andaman & Nicobar Islands","region":"South India",
   "lat":12.0015,"lon":92.9853,"vibes":["beach","adventure","nature","honeymoon","offbeat"],
   "primary_vibe":"beach","avg_cost_budget":2000,"avg_cost_mid":4000,"avg_cost_luxury":10000,
   "min_days":3,"max_days":6,"best_months":[10,11,12,1,2,3,4],"popularity":8.5,
   "group_suitability":{"solo":0.8,"couple":0.95,"friends":0.85,"family":0.75},
   "nearest_airport":"Veer Savarkar Airport, Port Blair (57 km by ferry)","nearest_railway":"Chennai (1370 km by ship)",
   "nearest_major_city":"Port Blair","distance_from_delhi_km":2200,"budget_range":"medium"},

  {"id":"neil-island","name":"Neil Island (Shaheed Dweep)","state":"Andaman & Nicobar Islands","region":"South India",
   "lat":11.8340,"lon":93.0507,"vibes":["beach","offbeat","nature","honeymoon"],
   "primary_vibe":"beach","avg_cost_budget":1800,"avg_cost_mid":3500,"avg_cost_luxury":8000,
   "min_days":2,"max_days":4,"best_months":[10,11,12,1,2,3,4],"popularity":7.5,
   "group_suitability":{"solo":0.8,"couple":0.95,"friends":0.75,"family":0.7},
   "nearest_airport":"Veer Savarkar Airport, Port Blair (37 km by ferry)","nearest_railway":"Port Blair (ferry)",
   "nearest_major_city":"Port Blair","distance_from_delhi_km":2200,"budget_range":"medium"},

  # ── Bihar (more) ───────────────────────────────────────────────────────────
  {"id":"nalanda","name":"Nalanda","state":"Bihar","region":"East India",
   "lat":25.1363,"lon":85.4424,"vibes":["heritage","spiritual","offbeat","education"],
   "primary_vibe":"heritage","avg_cost_budget":600,"avg_cost_mid":1200,"avg_cost_luxury":2500,
   "min_days":1,"max_days":2,"best_months":[10,11,12,1,2,3],"popularity":7.0,
   "group_suitability":{"solo":0.8,"couple":0.7,"friends":0.75,"family":0.8},
   "nearest_airport":"Gaya Airport (85 km)","nearest_railway":"Rajgir (12 km)",
   "nearest_major_city":"Patna","distance_from_delhi_km":780,"budget_range":"budget"},

  {"id":"rajgir","name":"Rajgir","state":"Bihar","region":"East India",
   "lat":25.0220,"lon":85.4217,"vibes":["spiritual","heritage","nature","pilgrimage"],
   "primary_vibe":"spiritual","avg_cost_budget":700,"avg_cost_mid":1400,"avg_cost_luxury":3000,
   "min_days":1,"max_days":3,"best_months":[10,11,12,1,2,3],"popularity":7.0,
   "group_suitability":{"solo":0.75,"couple":0.7,"friends":0.7,"family":0.85},
   "nearest_airport":"Gaya Airport (78 km)","nearest_railway":"Rajgir (2 km)",
   "nearest_major_city":"Patna","distance_from_delhi_km":790,"budget_range":"budget"},

  # ── Assam (more) ───────────────────────────────────────────────────────────
  {"id":"manas","name":"Manas National Park","state":"Assam","region":"Northeast India",
   "lat":26.7034,"lon":91.0047,"vibes":["wildlife","nature","adventure","offbeat"],
   "primary_vibe":"wildlife","avg_cost_budget":1500,"avg_cost_mid":3000,"avg_cost_luxury":7000,
   "min_days":2,"max_days":4,"best_months":[10,11,12,1,2,3,4],"popularity":7.0,
   "group_suitability":{"solo":0.75,"couple":0.8,"friends":0.8,"family":0.75},
   "nearest_airport":"Lokapriya Gopinath Bordoloi Airport, Guwahati (140 km)","nearest_railway":"Barpeta Road (41 km)",
   "nearest_major_city":"Guwahati","distance_from_delhi_km":1070,"budget_range":"medium"},

  {"id":"jorhat","name":"Jorhat","state":"Assam","region":"Northeast India",
   "lat":26.7564,"lon":94.2037,"vibes":["nature","offbeat","tea","heritage"],
   "primary_vibe":"nature","avg_cost_budget":900,"avg_cost_mid":1800,"avg_cost_luxury":3500,
   "min_days":2,"max_days":4,"best_months":[10,11,12,1,2,3,4],"popularity":5.5,
   "group_suitability":{"solo":0.8,"couple":0.75,"friends":0.8,"family":0.75},
   "nearest_airport":"Jorhat Airport (5 km)","nearest_railway":"Mariani Junction (16 km)",
   "nearest_major_city":"Dibrugarh","distance_from_delhi_km":1385,"budget_range":"budget"},

  # ── Jharkhand (new state!) ─────────────────────────────────────────────────
  {"id":"ranchi","name":"Ranchi","state":"Jharkhand","region":"East India",
   "lat":23.3441,"lon":85.3096,"vibes":["nature","offbeat","adventure","waterfalls"],
   "primary_vibe":"nature","avg_cost_budget":900,"avg_cost_mid":1800,"avg_cost_luxury":3500,
   "min_days":2,"max_days":4,"best_months":[10,11,12,1,2,3],"popularity":6.5,
   "group_suitability":{"solo":0.75,"couple":0.8,"friends":0.85,"family":0.8},
   "nearest_airport":"Birsa Munda Airport (5 km)","nearest_railway":"Ranchi Station (3 km)",
   "nearest_major_city":"Ranchi","distance_from_delhi_km":1180,"budget_range":"budget"},

  {"id":"deoghar","name":"Deoghar","state":"Jharkhand","region":"East India",
   "lat":24.4853,"lon":86.6952,"vibes":["spiritual","pilgrimage","heritage"],
   "primary_vibe":"spiritual","avg_cost_budget":700,"avg_cost_mid":1400,"avg_cost_luxury":2800,
   "min_days":1,"max_days":3,"best_months":[7,8,10,11,12,1,2,3],"popularity":7.5,
   "group_suitability":{"solo":0.7,"couple":0.7,"friends":0.65,"family":0.9},
   "nearest_airport":"Deoghar Airport (7 km)","nearest_railway":"Jasidih Junction (8 km)",
   "nearest_major_city":"Dhanbad","distance_from_delhi_km":990,"budget_range":"budget"},

  {"id":"betla","name":"Betla National Park (Palamu)","state":"Jharkhand","region":"East India",
   "lat":23.9225,"lon":84.1338,"vibes":["wildlife","nature","offbeat","adventure"],
   "primary_vibe":"wildlife","avg_cost_budget":1000,"avg_cost_mid":2000,"avg_cost_luxury":4000,
   "min_days":2,"max_days":4,"best_months":[11,12,1,2,3,4,5],"popularity":5.5,
   "group_suitability":{"solo":0.75,"couple":0.75,"friends":0.8,"family":0.75},
   "nearest_airport":"Birsa Munda Airport, Ranchi (175 km)","nearest_railway":"Daltonganj (25 km)",
   "nearest_major_city":"Ranchi","distance_from_delhi_km":1130,"budget_range":"budget"},

  # ── Manipur ────────────────────────────────────────────────────────────────
  {"id":"imphal","name":"Imphal","state":"Manipur","region":"Northeast India",
   "lat":24.8170,"lon":93.9368,"vibes":["heritage","nature","offbeat","spiritual"],
   "primary_vibe":"heritage","avg_cost_budget":900,"avg_cost_mid":1800,"avg_cost_luxury":3500,
   "min_days":2,"max_days":5,"best_months":[10,11,12,1,2,3,4],"popularity":5.5,
   "group_suitability":{"solo":0.8,"couple":0.7,"friends":0.8,"family":0.75},
   "nearest_airport":"Imphal Airport (8 km)","nearest_railway":"Jiribam (225 km)",
   "nearest_major_city":"Imphal","distance_from_delhi_km":2220,"budget_range":"budget"},

  # ── Tripura (new state!) ───────────────────────────────────────────────────
  {"id":"neermahal","name":"Neermahal","state":"Tripura","region":"Northeast India",
   "lat":23.4997,"lon":91.1143,"vibes":["heritage","offbeat","nature"],
   "primary_vibe":"heritage","avg_cost_budget":700,"avg_cost_mid":1400,"avg_cost_luxury":2800,
   "min_days":1,"max_days":3,"best_months":[10,11,12,1,2,3,4],"popularity":5.0,
   "group_suitability":{"solo":0.8,"couple":0.8,"friends":0.75,"family":0.8},
   "nearest_airport":"Agartala Airport (55 km)","nearest_railway":"Agartala (54 km)",
   "nearest_major_city":"Agartala","distance_from_delhi_km":1690,"budget_range":"budget"},

  {"id":"unakoti","name":"Unakoti","state":"Tripura","region":"Northeast India",
   "lat":24.3160,"lon":92.1088,"vibes":["heritage","spiritual","offbeat","nature"],
   "primary_vibe":"heritage","avg_cost_budget":700,"avg_cost_mid":1400,"avg_cost_luxury":2800,
   "min_days":1,"max_days":2,"best_months":[10,11,12,1,2,3,4],"popularity":5.0,
   "group_suitability":{"solo":0.85,"couple":0.75,"friends":0.8,"family":0.75},
   "nearest_airport":"Agartala Airport (145 km)","nearest_railway":"Dharmanagar (25 km)",
   "nearest_major_city":"Agartala","distance_from_delhi_km":1750,"budget_range":"budget"},

  # ── Mizoram (new state!) ───────────────────────────────────────────────────
  {"id":"aizawl","name":"Aizawl","state":"Mizoram","region":"Northeast India",
   "lat":23.7271,"lon":92.7176,"vibes":["mountains","offbeat","nature","heritage"],
   "primary_vibe":"mountains","avg_cost_budget":1000,"avg_cost_mid":2000,"avg_cost_luxury":4000,
   "min_days":2,"max_days":5,"best_months":[10,11,12,1,2,3,4],"popularity":5.0,
   "group_suitability":{"solo":0.85,"couple":0.75,"friends":0.8,"family":0.75},
   "nearest_airport":"Lengpui Airport (32 km)","nearest_railway":"Bairabi (180 km)",
   "nearest_major_city":"Aizawl","distance_from_delhi_km":2200,"budget_range":"budget"},

  {"id":"phawngpui","name":"Phawngpui (Blue Mountain)","state":"Mizoram","region":"Northeast India",
   "lat":22.5333,"lon":92.9333,"vibes":["trekking","offbeat","nature","mountains"],
   "primary_vibe":"trekking","avg_cost_budget":900,"avg_cost_mid":1800,"avg_cost_luxury":3000,
   "min_days":3,"max_days":5,"best_months":[10,11,12,1,2,3],"popularity":4.5,
   "group_suitability":{"solo":0.9,"couple":0.7,"friends":0.9,"family":0.5},
   "nearest_airport":"Lengpui Airport, Aizawl (260 km)","nearest_railway":"Bairabi (310 km)",
   "nearest_major_city":"Aizawl","distance_from_delhi_km":2350,"budget_range":"budget"},

  # ── Kerala (more) ──────────────────────────────────────────────────────────
  {"id":"fort-kochi","name":"Fort Kochi","state":"Kerala","region":"South India",
   "lat":9.9631,"lon":76.2429,"vibes":["heritage","beach","offbeat","culture","art"],
   "primary_vibe":"heritage","avg_cost_budget":1200,"avg_cost_mid":2500,"avg_cost_luxury":6000,
   "min_days":2,"max_days":4,"best_months":[10,11,12,1,2,3],"popularity":8.0,
   "group_suitability":{"solo":0.9,"couple":0.9,"friends":0.8,"family":0.8},
   "nearest_airport":"Cochin International Airport (35 km)","nearest_railway":"Ernakulam Junction (14 km)",
   "nearest_major_city":"Kochi","distance_from_delhi_km":2100,"budget_range":"budget"},

  {"id":"athirappilly","name":"Athirappilly Falls","state":"Kerala","region":"South India",
   "lat":10.2848,"lon":76.5688,"vibes":["nature","wildlife","adventure","offbeat"],
   "primary_vibe":"nature","avg_cost_budget":1000,"avg_cost_mid":2000,"avg_cost_luxury":4500,
   "min_days":1,"max_days":3,"best_months":[6,7,8,9,10,11,12],"popularity":7.5,
   "group_suitability":{"solo":0.75,"couple":0.85,"friends":0.85,"family":0.85},
   "nearest_airport":"Cochin International Airport (55 km)","nearest_railway":"Chalakudy (33 km)",
   "nearest_major_city":"Kochi","distance_from_delhi_km":2050,"budget_range":"budget"},

  {"id":"kumarakom","name":"Kumarakom","state":"Kerala","region":"South India",
   "lat":9.6178,"lon":76.4292,"vibes":["backwaters","nature","honeymoon","luxury"],
   "primary_vibe":"backwaters","avg_cost_budget":2000,"avg_cost_mid":4500,"avg_cost_luxury":12000,
   "min_days":2,"max_days":5,"best_months":[9,10,11,12,1,2,3],"popularity":8.0,
   "group_suitability":{"solo":0.6,"couple":0.95,"friends":0.65,"family":0.75},
   "nearest_airport":"Cochin International Airport (75 km)","nearest_railway":"Kottayam (16 km)",
   "nearest_major_city":"Kottayam","distance_from_delhi_km":1990,"budget_range":"luxury"},

  # ── Karnataka (more) ──────────────────────────────────────────────────────
  {"id":"dandeli","name":"Dandeli","state":"Karnataka","region":"South India",
   "lat":15.2648,"lon":74.6211,"vibes":["wildlife","adventure","nature","offbeat"],
   "primary_vibe":"wildlife","avg_cost_budget":1200,"avg_cost_mid":2500,"avg_cost_luxury":5500,
   "min_days":2,"max_days":4,"best_months":[10,11,12,1,2,3,4,5],"popularity":7.0,
   "group_suitability":{"solo":0.8,"couple":0.8,"friends":0.9,"family":0.75},
   "nearest_airport":"Hubli Airport (75 km)","nearest_railway":"Dharwad (75 km)",
   "nearest_major_city":"Hubli","distance_from_delhi_km":1700,"budget_range":"budget"},

  {"id":"belur-halebidu","name":"Belur & Halebidu","state":"Karnataka","region":"South India",
   "lat":13.1619,"lon":75.8643,"vibes":["heritage","offbeat","spiritual"],
   "primary_vibe":"heritage","avg_cost_budget":700,"avg_cost_mid":1400,"avg_cost_luxury":3000,
   "min_days":1,"max_days":2,"best_months":[10,11,12,1,2,3],"popularity":7.0,
   "group_suitability":{"solo":0.8,"couple":0.75,"friends":0.75,"family":0.8},
   "nearest_airport":"Mangalore Airport (170 km)","nearest_railway":"Hassan (27 km)",
   "nearest_major_city":"Hassan","distance_from_delhi_km":1820,"budget_range":"budget"},

  # ── Tamil Nadu (more) ─────────────────────────────────────────────────────
  {"id":"kanyakumari","name":"Kanyakumari","state":"Tamil Nadu","region":"South India",
   "lat":8.0883,"lon":77.5385,"vibes":["spiritual","beach","heritage","nature"],
   "primary_vibe":"spiritual","avg_cost_budget":900,"avg_cost_mid":1800,"avg_cost_luxury":3500,
   "min_days":1,"max_days":3,"best_months":[10,11,12,1,2,3],"popularity":8.5,
   "group_suitability":{"solo":0.75,"couple":0.8,"friends":0.75,"family":0.9},
   "nearest_airport":"Trivandrum Airport (90 km)","nearest_railway":"Kanyakumari Station (1 km)",
   "nearest_major_city":"Thiruvananthapuram","distance_from_delhi_km":2640,"budget_range":"budget"},

  {"id":"vellore","name":"Vellore","state":"Tamil Nadu","region":"South India",
   "lat":12.9165,"lon":79.1325,"vibes":["heritage","spiritual","offbeat"],
   "primary_vibe":"heritage","avg_cost_budget":800,"avg_cost_mid":1600,"avg_cost_luxury":3000,
   "min_days":1,"max_days":2,"best_months":[10,11,12,1,2,3],"popularity":6.5,
   "group_suitability":{"solo":0.75,"couple":0.7,"friends":0.7,"family":0.8},
   "nearest_airport":"Chennai Airport (135 km)","nearest_railway":"Katpadi Junction (5 km)",
   "nearest_major_city":"Chennai","distance_from_delhi_km":2180,"budget_range":"budget"},

  # ── Maharashtra (more) ────────────────────────────────────────────────────
  {"id":"nashik","name":"Nashik","state":"Maharashtra","region":"West India",
   "lat":19.9975,"lon":73.7898,"vibes":["spiritual","heritage","wine","nature"],
   "primary_vibe":"spiritual","avg_cost_budget":1000,"avg_cost_mid":2000,"avg_cost_luxury":4500,
   "min_days":2,"max_days":4,"best_months":[10,11,12,1,2,3],"popularity":7.5,
   "group_suitability":{"solo":0.75,"couple":0.8,"friends":0.8,"family":0.85},
   "nearest_airport":"Ozar Airport (25 km)","nearest_railway":"Nashik Road (8 km)",
   "nearest_major_city":"Pune","distance_from_delhi_km":1185,"budget_range":"budget"},

  {"id":"pune","name":"Pune","state":"Maharashtra","region":"West India",
   "lat":18.5204,"lon":73.8567,"vibes":["heritage","nature","offbeat","adventure"],
   "primary_vibe":"heritage","avg_cost_budget":1200,"avg_cost_mid":2500,"avg_cost_luxury":5500,
   "min_days":2,"max_days":4,"best_months":[10,11,12,1,2,3],"popularity":7.5,
   "group_suitability":{"solo":0.8,"couple":0.8,"friends":0.85,"family":0.8},
   "nearest_airport":"Pune Airport (10 km)","nearest_railway":"Pune Junction (3 km)",
   "nearest_major_city":"Pune","distance_from_delhi_km":1470,"budget_range":"medium"},

  # ── Gujarat (more) ────────────────────────────────────────────────────────
  {"id":"ahmedabad","name":"Ahmedabad","state":"Gujarat","region":"West India",
   "lat":23.0225,"lon":72.5714,"vibes":["heritage","food","culture","offbeat"],
   "primary_vibe":"heritage","avg_cost_budget":1200,"avg_cost_mid":2500,"avg_cost_luxury":5500,
   "min_days":2,"max_days":4,"best_months":[10,11,12,1,2,3],"popularity":8.0,
   "group_suitability":{"solo":0.8,"couple":0.75,"friends":0.8,"family":0.85},
   "nearest_airport":"Sardar Vallabhbhai Patel Airport (12 km)","nearest_railway":"Ahmedabad Junction (3 km)",
   "nearest_major_city":"Ahmedabad","distance_from_delhi_km":920,"budget_range":"budget"},

  {"id":"somnath","name":"Somnath","state":"Gujarat","region":"West India",
   "lat":20.9030,"lon":70.3758,"vibes":["spiritual","heritage","beach","pilgrimage"],
   "primary_vibe":"spiritual","avg_cost_budget":800,"avg_cost_mid":1600,"avg_cost_luxury":3500,
   "min_days":1,"max_days":3,"best_months":[10,11,12,1,2,3],"popularity":8.5,
   "group_suitability":{"solo":0.7,"couple":0.75,"friends":0.7,"family":0.9},
   "nearest_airport":"Diu Airport (65 km)","nearest_railway":"Veraval (6 km)",
   "nearest_major_city":"Rajkot","distance_from_delhi_km":1250,"budget_range":"budget"},

  {"id":"dwaraka","name":"Dwaraka","state":"Gujarat","region":"West India",
   "lat":22.2324,"lon":68.9671,"vibes":["spiritual","heritage","beach","pilgrimage"],
   "primary_vibe":"spiritual","avg_cost_budget":800,"avg_cost_mid":1600,"avg_cost_luxury":3000,
   "min_days":1,"max_days":3,"best_months":[10,11,12,1,2,3],"popularity":8.0,
   "group_suitability":{"solo":0.7,"couple":0.75,"friends":0.7,"family":0.9},
   "nearest_airport":"Jamnagar Airport (138 km)","nearest_railway":"Dwarka Station (1 km)",
   "nearest_major_city":"Jamnagar","distance_from_delhi_km":1400,"budget_range":"budget"},

  # ── Rajasthan (more) ──────────────────────────────────────────────────────
  {"id":"alwar","name":"Alwar & Sariska","state":"Rajasthan","region":"West India",
   "lat":27.5530,"lon":76.6346,"vibes":["wildlife","heritage","nature","offbeat"],
   "primary_vibe":"wildlife","avg_cost_budget":1200,"avg_cost_mid":2500,"avg_cost_luxury":5000,
   "min_days":2,"max_days":3,"best_months":[10,11,12,1,2,3,4],"popularity":6.5,
   "group_suitability":{"solo":0.75,"couple":0.8,"friends":0.8,"family":0.75},
   "nearest_airport":"Jaipur Airport (160 km)","nearest_railway":"Alwar Station (3 km)",
   "nearest_major_city":"Jaipur","distance_from_delhi_km":162,"budget_range":"budget"},

  {"id":"ranakpur","name":"Ranakpur","state":"Rajasthan","region":"West India",
   "lat":25.1167,"lon":73.4833,"vibes":["spiritual","heritage","nature","offbeat"],
   "primary_vibe":"heritage","avg_cost_budget":900,"avg_cost_mid":1800,"avg_cost_luxury":4000,
   "min_days":1,"max_days":2,"best_months":[10,11,12,1,2,3],"popularity":7.0,
   "group_suitability":{"solo":0.8,"couple":0.75,"friends":0.75,"family":0.8},
   "nearest_airport":"Udaipur Airport (95 km)","nearest_railway":"Falna (35 km)",
   "nearest_major_city":"Udaipur","distance_from_delhi_km":620,"budget_range":"budget"},

  {"id":"nathdwara","name":"Nathdwara","state":"Rajasthan","region":"West India",
   "lat":24.9330,"lon":73.8212,"vibes":["spiritual","heritage","pilgrimage"],
   "primary_vibe":"spiritual","avg_cost_budget":700,"avg_cost_mid":1400,"avg_cost_luxury":2800,
   "min_days":1,"max_days":2,"best_months":[10,11,12,1,2,3],"popularity":7.5,
   "group_suitability":{"solo":0.7,"couple":0.7,"friends":0.65,"family":0.9},
   "nearest_airport":"Udaipur Airport (49 km)","nearest_railway":"Nathdwara (2 km)",
   "nearest_major_city":"Udaipur","distance_from_delhi_km":590,"budget_range":"budget"},

  # ── Odisha (more) ─────────────────────────────────────────────────────────
  {"id":"bhubaneswar","name":"Bhubaneswar","state":"Odisha","region":"East India",
   "lat":20.2961,"lon":85.8245,"vibes":["heritage","spiritual","offbeat"],
   "primary_vibe":"heritage","avg_cost_budget":900,"avg_cost_mid":1800,"avg_cost_luxury":3500,
   "min_days":2,"max_days":4,"best_months":[10,11,12,1,2,3],"popularity":7.5,
   "group_suitability":{"solo":0.8,"couple":0.75,"friends":0.75,"family":0.8},
   "nearest_airport":"Bhubaneswar Airport (4 km)","nearest_railway":"Bhubaneswar Station (3 km)",
   "nearest_major_city":"Bhubaneswar","distance_from_delhi_km":1480,"budget_range":"budget"},

  {"id":"bhitarkanika","name":"Bhitarkanika","state":"Odisha","region":"East India",
   "lat":20.7500,"lon":86.8833,"vibes":["wildlife","nature","offbeat","backwaters"],
   "primary_vibe":"wildlife","avg_cost_budget":1200,"avg_cost_mid":2500,"avg_cost_luxury":5000,
   "min_days":2,"max_days":4,"best_months":[11,12,1,2,3,4],"popularity":6.0,
   "group_suitability":{"solo":0.8,"couple":0.75,"friends":0.8,"family":0.7},
   "nearest_airport":"Bhubaneswar Airport (195 km)","nearest_railway":"Bhadrak (65 km)",
   "nearest_major_city":"Bhubaneswar","distance_from_delhi_km":1550,"budget_range":"budget"},

  # ── West Bengal (more) ────────────────────────────────────────────────────
  {"id":"murshidabad","name":"Murshidabad","state":"West Bengal","region":"East India",
   "lat":24.1789,"lon":88.2710,"vibes":["heritage","offbeat","history"],
   "primary_vibe":"heritage","avg_cost_budget":700,"avg_cost_mid":1400,"avg_cost_luxury":2800,
   "min_days":2,"max_days":3,"best_months":[10,11,12,1,2,3],"popularity":6.5,
   "group_suitability":{"solo":0.85,"couple":0.75,"friends":0.75,"family":0.8},
   "nearest_airport":"Netaji Subhas Airport, Kolkata (220 km)","nearest_railway":"Baharampur Court (10 km)",
   "nearest_major_city":"Kolkata","distance_from_delhi_km":1390,"budget_range":"budget"},

  {"id":"digha","name":"Digha","state":"West Bengal","region":"East India",
   "lat":21.6271,"lon":87.5090,"vibes":["beach","nature","budget","offbeat"],
   "primary_vibe":"beach","avg_cost_budget":700,"avg_cost_mid":1400,"avg_cost_luxury":2800,
   "min_days":2,"max_days":3,"best_months":[10,11,12,1,2,3],"popularity":6.5,
   "group_suitability":{"solo":0.7,"couple":0.8,"friends":0.85,"family":0.85},
   "nearest_airport":"Netaji Subhas Airport, Kolkata (187 km)","nearest_railway":"Digha (2 km)",
   "nearest_major_city":"Kolkata","distance_from_delhi_km":1600,"budget_range":"budget"},

  # ── Punjab (more) ─────────────────────────────────────────────────────────
  {"id":"anandpur-sahib","name":"Anandpur Sahib","state":"Punjab","region":"North India",
   "lat":31.2339,"lon":76.5003,"vibes":["spiritual","heritage","pilgrimage"],
   "primary_vibe":"spiritual","avg_cost_budget":700,"avg_cost_mid":1400,"avg_cost_luxury":3000,
   "min_days":1,"max_days":2,"best_months":[10,11,12,1,2,3],"popularity":7.5,
   "group_suitability":{"solo":0.75,"couple":0.7,"friends":0.7,"family":0.9},
   "nearest_airport":"Chandigarh Airport (80 km)","nearest_railway":"Anandpur Sahib (2 km)",
   "nearest_major_city":"Chandigarh","distance_from_delhi_km":320,"budget_range":"budget"},

  # ── Himachal (a couple more niche) ────────────────────────────────────────
  {"id":"spello-valley","name":"Spiti Valley","state":"Himachal Pradesh","region":"North India",
   "lat":32.2460,"lon":78.0353,"vibes":["mountains","offbeat","desert","spiritual","trekking"],
   "primary_vibe":"mountains","avg_cost_budget":1500,"avg_cost_mid":3000,"avg_cost_luxury":6000,
   "min_days":5,"max_days":12,"best_months":[6,7,8,9],"popularity":8.0,
   "group_suitability":{"solo":0.9,"couple":0.8,"friends":0.9,"family":0.55},
   "nearest_airport":"Shimla Airport (210 km)","nearest_railway":"Shimla (210 km)",
   "nearest_major_city":"Shimla","distance_from_delhi_km":535,"budget_range":"medium"},

  {"id":"barot","name":"Barot Valley","state":"Himachal Pradesh","region":"North India",
   "lat":32.0442,"lon":76.8769,"vibes":["mountains","offbeat","nature","trekking","fishing"],
   "primary_vibe":"mountains","avg_cost_budget":900,"avg_cost_mid":1800,"avg_cost_luxury":3500,
   "min_days":2,"max_days":5,"best_months":[4,5,6,9,10],"popularity":5.0,
   "group_suitability":{"solo":0.9,"couple":0.8,"friends":0.85,"family":0.7},
   "nearest_airport":"Gaggal Airport, Kangra (85 km)","nearest_railway":"Jogindernagar (45 km)",
   "nearest_major_city":"Mandi","distance_from_delhi_km":520,"budget_range":"budget"},

  # ── MP (more) ────────────────────────────────────────────────────────────
  {"id":"panna","name":"Panna National Park","state":"Madhya Pradesh","region":"Central India",
   "lat":24.7180,"lon":80.1500,"vibes":["wildlife","nature","adventure"],
   "primary_vibe":"wildlife","avg_cost_budget":1500,"avg_cost_mid":3000,"avg_cost_luxury":7000,
   "min_days":2,"max_days":4,"best_months":[10,11,12,1,2,3,4,5],"popularity":6.5,
   "group_suitability":{"solo":0.75,"couple":0.8,"friends":0.8,"family":0.75},
   "nearest_airport":"Khajuraho Airport (25 km)","nearest_railway":"Satna (90 km)",
   "nearest_major_city":"Khajuraho","distance_from_delhi_km":615,"budget_range":"medium"},

  {"id":"amarkantak","name":"Amarkantak","state":"Madhya Pradesh","region":"Central India",
   "lat":22.6740,"lon":81.7567,"vibes":["spiritual","nature","offbeat","trekking"],
   "primary_vibe":"spiritual","avg_cost_budget":700,"avg_cost_mid":1400,"avg_cost_luxury":2800,
   "min_days":2,"max_days":3,"best_months":[10,11,12,1,2,3],"popularity":6.0,
   "group_suitability":{"solo":0.8,"couple":0.75,"friends":0.75,"family":0.85},
   "nearest_airport":"Raipur Airport (225 km)","nearest_railway":"Pendra Road (35 km)",
   "nearest_major_city":"Bilaspur","distance_from_delhi_km":1050,"budget_range":"budget"},

  # ── Uttarakhand (a couple more) ───────────────────────────────────────────
  {"id":"nainital-zoo","name":"Corbett Ramnagar","state":"Uttarakhand","region":"North India",
   "lat":29.3949,"lon":79.1268,"vibes":["wildlife","nature","adventure"],
   "primary_vibe":"wildlife","avg_cost_budget":1500,"avg_cost_mid":3000,"avg_cost_luxury":8000,
   "min_days":2,"max_days":4,"best_months":[11,12,1,2,3,4,5,6],"popularity":8.5,
   "group_suitability":{"solo":0.75,"couple":0.8,"friends":0.8,"family":0.8},
   "nearest_airport":"Pantnagar Airport (55 km)","nearest_railway":"Ramnagar (3 km)",
   "nearest_major_city":"Haldwani","distance_from_delhi_km":260,"budget_range":"medium"},

  {"id":"gangotri","name":"Gangotri","state":"Uttarakhand","region":"North India",
   "lat":30.9946,"lon":78.9394,"vibes":["spiritual","mountains","trekking","pilgrimage"],
   "primary_vibe":"spiritual","avg_cost_budget":1000,"avg_cost_mid":2000,"avg_cost_luxury":3500,
   "min_days":2,"max_days":4,"best_months":[5,6,9,10],"popularity":8.0,
   "group_suitability":{"solo":0.8,"couple":0.75,"friends":0.75,"family":0.8},
   "nearest_airport":"Jolly Grant Airport, Dehradun (249 km)","nearest_railway":"Rishikesh (248 km)",
   "nearest_major_city":"Rishikesh","distance_from_delhi_km":475,"budget_range":"budget"},

  {"id":"yamunotri","name":"Yamunotri","state":"Uttarakhand","region":"North India",
   "lat":31.0146,"lon":78.4623,"vibes":["spiritual","mountains","trekking","pilgrimage"],
   "primary_vibe":"spiritual","avg_cost_budget":1000,"avg_cost_mid":2000,"avg_cost_luxury":3500,
   "min_days":2,"max_days":3,"best_months":[5,6,9,10],"popularity":7.5,
   "group_suitability":{"solo":0.75,"couple":0.7,"friends":0.7,"family":0.8},
   "nearest_airport":"Jolly Grant Airport, Dehradun (220 km)","nearest_railway":"Rishikesh (215 km)",
   "nearest_major_city":"Rishikesh","distance_from_delhi_km":450,"budget_range":"budget"},
]


def groq_fill(dest: dict, api_key: str) -> dict:
    prompt = (
        f"Destination: {dest['name']}, {dest['state']}\n"
        f"Vibes: {', '.join(dest.get('vibes', []))}\n\n"
        f"Return ONLY this JSON with real accurate info:\n{SCHEMA}"
    )
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user",   "content": prompt},
        ],
        "temperature": 0.4, "max_tokens": 700,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    with httpx.Client(timeout=30) as c:
        r = c.post(GROQ_URL, headers=headers, json=payload)
        if r.status_code == 429:
            raise httpx.HTTPStatusError("429", request=r.request, response=r)
        r.raise_for_status()
        return json.loads(r.json()["choices"][0]["message"]["content"])


def template_fill(dest: dict) -> dict:
    return {
        "description": (
            f"{dest['name']} is a {dest['primary_vibe']} destination in {dest['state']}, {dest['region']}. "
            f"It offers experiences centred around {', '.join(dest['vibes'][:3])}."
        ),
        "highlights":       ["Main attractions", "Local sights", "Cultural experiences", "Nature walks", "Local markets"],
        "food_specialties": ["Local thali", "Regional snacks", "Street food", "Traditional sweets"],
        "accommodation":    ["hotel", "guesthouse", "homestay"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-llm",  action="store_true")
    args = parser.parse_args()

    with open(DATA_PATH) as f:
        existing = json.load(f)
    existing_ids = {d["id"] for d in existing}

    seeds = [d for d in NEW_DESTINATIONS_2 if d["id"] not in existing_ids]
    print(f"{len(seeds)} new destinations to add")
    if not seeds:
        print("Nothing to add.")
        return

    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    use_llm  = bool(groq_key) and not args.no_llm

    new_dests = []
    for i, seed in enumerate(seeds, 1):
        print(f"[{i}/{len(seeds)}] {seed['name']}...", end=" ", flush=True)
        filled = None
        if use_llm:
            for attempt in range(3):
                try:
                    filled = groq_fill(seed, groq_key)
                    print("OK (Groq)")
                    time.sleep(2.0)
                    break
                except Exception as e:
                    if "429" in str(e):
                        wait = 4 * (attempt + 1)
                        print(f"429 wait {wait}s...", end=" ", flush=True)
                        time.sleep(wait)
                    else:
                        print(f"err ({e})", end=" ", flush=True)
                        break
        if not filled:
            filled = template_fill(seed)
            if use_llm:
                print("template (LLM failed)")
            else:
                print("template")

        dest = {
            **seed,
            "description":     filled.get("description", template_fill(seed)["description"]),
            "highlights":      filled.get("highlights",  template_fill(seed)["highlights"]),
            "food_specialties":filled.get("food_specialties", template_fill(seed)["food_specialties"]),
            "accommodation":   filled.get("accommodation", template_fill(seed)["accommodation"]),
        }
        new_dests.append(dest)

    if args.dry_run:
        print(json.dumps(new_dests, indent=2, ensure_ascii=False))
        return

    combined = existing + new_dests
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2, ensure_ascii=False)
    print(f"\nDone! destinations.json now has {len(combined)} (+{len(new_dests)} new)")
    print("Run: python3 scripts/enrich_descriptions.py  to fill descriptions")
    print("Then: python3 ingest.py --no-wikipedia  for quick index update")


if __name__ == "__main__":
    main()
