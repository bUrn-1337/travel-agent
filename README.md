# TravelMind

AI-powered India travel recommendation and planning app — hybrid search, RAG itinerary generation, 521 destinations.
Github link :- [https://github.com/bUrn-1337/travel-agent/](url)

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes Docker Compose)
- Git

---

## Quick Start

```bash
# 1. Clone
git clone <repo-url>
cd travel-agent

# 2. Set environment variables
cp .env.example .env
# Edit .env — minimum required: GROQ_API_KEY or GEMINI_API_KEY

# 3. Build and start all three services
docker compose up --build

# 4. Build the RAG knowledge base (first run only — takes ~5 min)
docker compose exec backend python3 ingest.py

# App is live at http://localhost:3000
```

---

## Environment Variables

Create a `.env` file in the project root:


```env
# LLM — at least one required for AI plan generation
GROQ_API_KEY=gsk_...           # https://console.groq.com — free tier
GEMINI_API_KEY=AIza...         # https://aistudio.google.com — free tier

# Photos — optional (Wikipedia fallback used if unset)
PEXELS_API_KEY=...             # https://www.pexels.com/api — free tier

# Google Login — optional (login feature disabled if unset)
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...

# Security — set any random string in production
SECRET_KEY=change-me-in-production

# Database — default works with docker-compose
POSTGRES_PASSWORD=postgres

# OAuth redirect base — change if deploying to a domain
FRONTEND_URL=http://localhost:3000
```

Getting API keys:
- **Groq**: [console.groq.com](https://console.groq.com) → Create API Key (free, no card erquired)
- **Gemini**: [aistudio.google.com](https://aistudio.google.com) → Get API Key (free)
- **Pexels**: [pexels.com/api](https://www.pexels.com/api/) → Your API Key (free)
- **Google OAuth**: [console.cloud.google.com](https://console.cloud.google.com) → APIs & Services → Credentials → OAuth 2.0 Client ID → Authorised redirect URI: `http://localhost:3000/auth/google/callback`

---

## Running the App

```bash
# Start (first time — builds images)
docker compose up --build

# Start (subsequent runs)
docker compose up

# Stop
docker compose down

# Stop and delete all data (database + vector store)
docker compose down -v
```

After starting, rebuild the knowledge base if you haven't yet:

```bash
docker compose exec backend python3 ingest.py
```

---

## Rebuilding After Code Changes

```bash
# Rebuild everything
docker compose up --build --force-recreate

# Rebuild only the backend
docker compose build backend && docker compose up -d --force-recreate backend

# Rebuild only the frontend
docker compose build frontend && docker compose up -d --force-recreate frontend
```

To push individual static file changes to the running frontend container without a full rebuild:

```bash
docker compose cp frontend/style.css frontend:/usr/share/nginx/html/style.css
```

---

## Database Management

```bash
# Connect to PostgreSQL
docker compose exec db psql -U postgres -d travelagent

# Useful queries
\dt                              -- list tables
SELECT count(*) FROM users;
SELECT name, destination_id FROM saved_trips;
```

---

## RAG Knowledge Base

The knowledge base must be built once after the backend starts. It chunks all 521 destinations into typed text segments and stores them in ChromaDB.

```bash
# Build / rebuild the full knowledge base
docker compose exec backend python3 ingest.py

# Check knowledge base status
curl http://localhost:3000/api/rag/status
```

ChromaDB data is stored in a Docker volume (`chroma_data`) and persists between restarts.

---

## Data Enrichment Scripts

These only need to be run if you modify the destination database.

```bash
# Expand destinations from Wikipedia category pages (192 → 521)
docker compose exec backend python3 scripts/wiki_expand.py

# Enrich new destinations with Wikivoyage + Wikipedia data
# (nearest_airport, food_specialties, highlights, nearest_major_city)
docker compose exec backend python3 scripts/wiki_enrich.py

# Re-enrich everything including existing destinations
docker compose exec backend python3 scripts/wiki_enrich.py --all

# Preview enrichment without writing to disk
docker compose exec backend python3 scripts/wiki_enrich.py --dry-run

# After enrichment, rebuild the RAG index
docker compose exec backend python3 ingest.py
```

---

## API Endpoints

All API calls go through `http://localhost:3000/api/` (proxied by nginx to the backend).

### Search

```bash
# Search destinations
curl -X POST http://localhost:3000/api/search \
  -H "Content-Type: application/json" \
  -d '{
    "vibes": ["mountains", "trekking"],
    "days": 5,
    "budget_per_day": 2000,
    "group_type": "friends",
    "travel_month": 6,
    "top_k": 10
  }'

# List all destinations (minimal)
curl http://localhost:3000/api/destinations

# Get a single destination
curl http://localhost:3000/api/destinations/manali

# Similar destinations
curl http://localhost:3000/api/destinations/manali/similar?n=3

# Transport options from GPS location
curl "http://localhost:3000/api/destinations/manali/travel?lat=28.61&lon=77.20"

# Photos
curl "http://localhost:3000/api/photos/manali?count=6"
```

### AI Generation (SSE streaming)

```bash
# Stream a travel plan (SSE — use curl with no-buffer)
curl -N -X POST http://localhost:3000/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "destination_id": "manali",
    "days": 5,
    "budget_per_day": 2000,
    "group_type": "friends",
    "vibes": ["mountains", "adventure"]
  }'

# Stream a packing list
curl -N -X POST http://localhost:3000/api/packing-list \
  -H "Content-Type: application/json" \
  -d '{
    "destination_id": "manali",
    "days": 5,
    "group_type": "friends",
    "travel_month": 12
  }'

# Structured JSON plan (blocking)
curl -X POST http://localhost:3000/api/generate/structured \
  -H "Content-Type: application/json" \
  -d '{"destination_id": "manali", "days": 5, "budget_per_day": 2000}'
```

### Auth

```bash
# Start Google login (open in browser)
http://localhost:3000/auth/google

# Check current user (requires cookie)
curl http://localhost:3000/auth/me --cookie "tm_session=<token>"

# Logout
curl -X POST http://localhost:3000/auth/logout
```

### Trips (requires login)

```bash
# Save a trip (requires tm_session cookie)
curl -X POST http://localhost:3000/api/trips \
  -H "Content-Type: application/json" \
  --cookie "tm_session=<token>" \
  -d '{
    "destination_id": "manali",
    "destination_name": "Manali",
    "destination_data": {},
    "plan_markdown": "## Day 1\n...",
    "days": 5,
    "budget_per_day": 2000,
    "group_type": "friends"
  }'

# List saved trips
curl http://localhost:3000/api/trips --cookie "tm_session=<token>"

# Delete a trip
curl -X DELETE http://localhost:3000/api/trips/<trip-id> --cookie "tm_session=<token>"

# Share a trip (make public)
curl -X POST http://localhost:3000/api/trips/<trip-id>/share --cookie "tm_session=<token>"

# View a shared trip (no auth)
curl http://localhost:3000/api/share/<trip-id>
```

### Diagnostics

```bash
curl http://localhost:3000/health
curl http://localhost:3000/api/rag/status
curl http://localhost:3000/api/cache/stats
```

---

## Project Structure

```
travel-agent/
├── docker-compose.yml
├── .env                       ← create this (see Environment Variables)
├── frontend/
│   ├── Dockerfile             ← nginx:alpine, copies all static files
│   ├── nginx.conf             ← serves static + proxies /api /auth to backend
│   ├── index.html             ← homepage
│   ├── destination.html       ← destination detail page
│   ├── trips.html             ← my trips
│   ├── trip.html              ← shared trip view
│   ├── app.js                 ← homepage logic
│   ├── destination.js         ← destination page logic
│   ├── trips.js / trip.js     ← trips pages logic
│   ├── auth.js                ← OAuth login/logout
│   ├── style.css              ← global styles
│   └── destination.css        ← destination page styles
└── backend/
    ├── Dockerfile             ← Python 3.11, installs requirements
    ├── requirements.txt
    ├── main.py                ← FastAPI app, all routes
    ├── auth.py                ← Google OAuth + JWT
    ├── database.py            ← SQLAlchemy setup
    ├── models.py              ← User, SavedTrip ORM models
    ├── ingest.py              ← builds ChromaDB knowledge base
    ├── start.sh               ← entrypoint: starts uvicorn
    ├── data/
    │   └── destinations.json  ← 521 destination records
    ├── search/
    │   └── minsearch.py       ← TF-IDF search index
    ├── rag/
    │   ├── embedder.py        ← sentence-transformers semantic scoring
    │   ├── chunker.py         ← splits destinations into typed chunks
    │   ├── corpus_builder.py  ← builds text for embedding
    │   ├── vector_store.py    ← ChromaDB wrapper
    │   ├── retriever.py       ← diversity-aware chunk retrieval
    │   ├── pipeline.py        ← RAG orchestration
    │   ├── generator.py       ← Groq/Gemini/fallback LLM
    │   └── photo_fetcher.py   ← Pexels → Wikipedia photo chain
    ├── ranking/
    │   ├── scorer.py          ← 8-signal composite ranker
    │   └── cost_estimator.py  ← cost estimation + transport
    └── scripts/
        ├── wiki_expand.py     ← Wikipedia category scraper
        └── wiki_enrich.py     ← Wikivoyage + Wikipedia enrichment
```

---

## Common Issues

**`docker` command not found (WSL)**
Open Docker Desktop on Windows first, then ensure WSL integration is enabled in Settings → Resources → WSL Integration.

**Port 3000 already in use**
```bash
docker compose down
# or change the port in docker-compose.yml: "3001:80"
```

**RAG knowledge base empty / plans not generating**
```bash
docker compose exec backend python3 ingest.py
curl http://localhost:3000/api/rag/status   # should show chunks_in_db > 0
```

**Login not working**
Ensure `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `FRONTEND_URL=http://localhost:3000` are set in `.env`, and that `http://localhost:3000/auth/google/callback` is added as an authorised redirect URI in Google Cloud Console.

**Photos not loading**
Set `PEXELS_API_KEY` in `.env`. Without it the app falls back to Wikipedia pageimages, which may return no results for some destinations.

**Plan generation says "No LLM key configured"**
Set at least one of `GROQ_API_KEY` or `GEMINI_API_KEY` in `.env`.
