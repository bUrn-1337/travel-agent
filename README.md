# TravelMind

An AI-powered India travel recommendation and planning app. Search 521 destinations, get personalised itineraries, discover places to eat and stay, and save trips — all running locally with Docker.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [How It Works](#how-it-works)
  - [Search Pipeline](#search-pipeline)
  - [RAG Plan Generation](#rag-plan-generation)
  - [Destination Data](#destination-data)
  - [Authentication](#authentication)
- [API Reference](#api-reference)
- [External APIs Used](#external-apis-used)
- [Running Locally](#running-locally)
- [Environment Variables](#environment-variables)
- [Project Structure](#project-structure)

---

## Features

- **521 Indian destinations** — cities, hill stations, beaches, forts, wildlife sanctuaries, pilgrimage sites, offbeat villages
- **Hybrid search** — combines TF-IDF keyword scoring with semantic (sentence-transformer) embeddings
- **Composite ranking** — vibe match, budget fit, seasonal suitability, group type, GPS proximity, popularity
- **AI travel plan generation** — streaming day-by-day itinerary via Groq (Llama 3.1) or Gemini, with ChromaDB RAG context
- **AI packing list** — streaming categorised packing list tailored to destination + travel month
- **Photo galleries** — Pexels API with Wikipedia pageimages fallback
- **GPS-aware transport options** — "Getting There" section uses your browser location to calculate distances and suggest flights/trains/buses
- **Deep booking links** — Google Flights, Skyscanner, EasyMyTrip, MakeMyTrip, Google Hotels, Booking.com, Airbnb
- **Similar destinations** — Jaccard vibe similarity + budget proximity + region bonus
- **Google OAuth login** — save and share trips across sessions
- **My Trips** — view, revisit, and share saved itineraries via public links

---

## Architecture

```
Browser
  │
  ▼
nginx (port 3000)
  │  serves static HTML/CSS/JS
  │  proxies /api/* and /auth/* to backend
  │
  ▼
FastAPI (port 8000)
  │
  ├─ Search: minsearch (TF-IDF) + sentence-transformers (cosine similarity)
  │
  ├─ Ranking: composite scorer (8 weighted signals)
  │
  ├─ RAG: ChromaDB vector store → Groq / Gemini LLM → SSE stream
  │
  ├─ Photos: Pexels API → Wikipedia pageimages fallback
  │
  ├─ Auth: Google OAuth 2.0 → JWT (httpOnly cookie)
  │
  └─ DB: PostgreSQL (users + saved trips)
```

All three services run as Docker containers defined in `docker-compose.yml`.

---

## How It Works

### Search Pipeline

When the user submits a search from the homepage:

1. **Query construction** — vibes (e.g. "mountains", "heritage"), free text, and city are concatenated into a single query string.

2. **Full-text retrieval** (`search/minsearch.py`) — a lightweight TF-IDF index built at startup over `name`, `description`, `vibes`, `highlights`, `food_specialties`, `state`, and `region`. Field boosts:
   - `name` × 4.0, `vibes` × 3.5, `state` × 2.5, `highlights` × 2.0, `region` × 2.0, `description` × 1.5, `food_specialties` × 1.0

3. **Semantic scoring** (`rag/embedder.py`) — `all-MiniLM-L6-v2` (sentence-transformers, 384-dim) embeds all destination descriptions at startup. At query time, cosine similarity is computed between the query embedding and each candidate.

4. **Composite ranking** (`ranking/scorer.py`) — each destination is scored across 8 signals:

   | Signal | Weight | Description |
   |---|---|---|
   | `vibe_match` | 27% | Fraction of requested vibes in destination + synonym expansion |
   | `semantic` | 22% | Cosine similarity from sentence-transformers |
   | `budget_fit` | 17% | Gaussian decay around destination's avg daily cost |
   | `group_fit` | 9% | Destination's suitability score for the group type |
   | `distance` | 8% | Exponential decay from user's GPS coords (0 if no GPS) |
   | `season_fit` | 7% | Whether the travel month is in the destination's `best_months` |
   | `popularity` | 7% | Normalized popularity score (1–10) |
   | `duration_fit` | 3% | Whether requested trip length fits the destination's min/max days |

5. **Response** — top 30 results returned; top 3 get cost estimates and photo URLs pre-attached.

---

### RAG Plan Generation

When the user clicks "Generate Plan" on a destination page:

1. **Retrieval** (`rag/retriever.py`) — ChromaDB is queried for the most relevant chunks filtered by `destination_id`. Chunks are classified by section type (transport, food, accommodation, general) to ensure diversity.

2. **Prompt assembly** (`rag/pipeline.py`) — retrieved chunks + destination metadata + user preferences (days, budget, group, vibes) are assembled into a structured prompt.

3. **LLM streaming** (`rag/generator.py`) — tried in order:
   - **Groq** — `llama-3.1-8b-instant` via OpenAI-compatible chat completions API (fast, free tier)
   - **Gemini** — `gemini-1.5-flash` via Google Generative Language API (SSE stream)
   - **No-LLM fallback** — formats the retrieved chunks into a readable plan without any LLM

4. **SSE stream** — tokens are sent as `data: <token>\n\n` events and assembled progressively in the browser using `EventSource`.

The same streaming infrastructure handles the **packing list** endpoint — a separate prompt builder generates a categorised packing list (Clothing, Documents, Gear, Toiletries, Electronics, Snacks) adapted to the destination's vibes, travel month, and group type.

---

### Destination Data

The 521 destinations are stored in `backend/data/destinations.json` and were built from three sources:

**1. Hand-curated base (192 destinations)**
Original structured records with full metadata: vibes, best months, group suitability, cost estimates, highlights, food specialties, transport info.

**2. Wikipedia expansion (`scripts/wiki_expand.py`)**
Queries 41 Wikipedia categories (e.g. "Hill stations in Himachal Pradesh", "Wildlife sanctuaries in Rajasthan") via the MediaWiki API to discover destination names, then fetches coordinates and descriptions from the Wikipedia REST summary API. Added 329 new destinations.

**3. Wikivoyage + Wikipedia enrichment (`scripts/wiki_enrich.py`)**
For the 329 new destinations, enriches missing structured fields:
- **`nearest_airport`** — from Wikivoyage `== Get in ==` / `=== By plane ===` section (structured IATA codes + distances), falls back to Wikipedia prose with regex extraction
- **`nearest_railway`** — from Wikivoyage `=== By train ===`, falls back to Wikipedia
- **`food_specialties`** — from Wikivoyage `== Eat ==` section (`'''Dish Name'''` bullets), falls back to Wikipedia cuisine section
- **`highlights`** — from Wikivoyage `== See ==` + `== Do ==` (`'''Place Name'''` bullets), falls back to Wikipedia tourist attractions section
- **`nearest_major_city`** — pure Haversine distance from destination coordinates to a list of 90 major Indian cities (no HTTP needed)

Wikivoyage is preferred because it has structured, travel-specific sections written specifically for travellers. Wikipedia is used as a fallback for destinations Wikivoyage doesn't cover.

The ChromaDB RAG index is built by `ingest.py`, which chunks each destination's text fields into typed segments (description, highlights, food, transport, accommodation) and upserts them with metadata filters for retrieval.

---

### Authentication

Google OAuth 2.0 flow:

1. User clicks "Sign in with Google" → `GET /auth/google` → redirect to Google consent screen with `state` nonce (stored in httpOnly cookie)
2. Google redirects back to `GET /auth/google/callback?code=...`
3. Backend exchanges code for tokens at `https://oauth2.googleapis.com/token`
4. Fetches user profile from `https://www.googleapis.com/oauth2/v3/userinfo`
5. Upserts user record in PostgreSQL
6. Issues a 7-day JWT signed with `SECRET_KEY`, set as httpOnly `SameSite=Lax` cookie (`tm_session`)
7. All protected routes (`/api/trips`, `/auth/me`) verify the JWT from the cookie

---

## API Reference

### Search & Discovery

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/search` | Main search — returns ranked destinations |
| `GET` | `/api/destinations` | List all destinations (minimal info) |
| `GET` | `/api/destinations/{id}` | Full destination details |
| `GET` | `/api/destinations/{id}/travel?lat=&lon=` | Transport options from user's GPS location |
| `GET` | `/api/destinations/{id}/similar?n=3` | Similar destinations by vibe + budget |
| `GET` | `/api/destinations/geo` | All destinations with lat/lon for map |
| `GET` | `/api/vibes` | List of valid vibe categories |
| `GET` | `/api/photos/{id}?count=6` | Photo URLs for a destination |

### AI Generation

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/generate` | Stream travel plan as SSE |
| `POST` | `/api/generate/structured` | Blocking JSON travel plan (cached) |
| `POST` | `/api/packing-list` | Stream packing list as SSE |
| `POST` | `/api/refine` | Stream follow-up answer given existing plan |

### Auth

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/auth/google` | Start Google OAuth flow |
| `GET` | `/auth/google/callback` | OAuth callback (set JWT cookie) |
| `GET` | `/auth/me` | Current user info |
| `POST` | `/auth/logout` | Clear session cookie |

### Trips

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/trips` | Save a trip (auth required) |
| `GET` | `/api/trips` | List user's saved trips (auth required) |
| `DELETE` | `/api/trips/{id}` | Delete a trip (auth required) |
| `POST` | `/api/trips/{id}/share` | Make trip public, return share URL |
| `GET` | `/api/share/{id}` | Get a public shared trip (no auth) |

### Diagnostics

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Service health + destination count + RAG chunks |
| `GET` | `/api/rag/status` | ChromaDB chunk count |
| `GET` | `/api/cache/stats` | In-memory plan cache stats |

---

## External APIs Used

| API | Used For | Key Required | Free Tier |
|---|---|---|---|
| **Groq** (`api.groq.com`) | Primary LLM — `llama-3.1-8b-instant`, streaming travel plans and packing lists | `GROQ_API_KEY` | Yes — generous free tier |
| **Google Gemini** (`generativelanguage.googleapis.com`) | Fallback LLM — `gemini-1.5-flash`, SSE streaming | `GEMINI_API_KEY` | Yes — free tier |
| **Pexels** (`api.pexels.com/v1/search`) | Destination photos — landscape-oriented, cached per destination | `PEXELS_API_KEY` | Yes — 200 req/hour |
| **Wikipedia REST API** (`en.wikipedia.org/api/rest_v1`) | Destination descriptions + coordinates during data enrichment scripts | None | Free, no key |
| **Wikivoyage MediaWiki API** (`en.wikivoyage.org/w/api.php`) | Travel-specific data (airports, food, highlights) during enrichment | None | Free, no key |
| **Wikipedia MediaWiki API** (`en.wikipedia.org/w/api.php`) | Category-based destination discovery + full article text | None | Free, no key |
| **Wikipedia Pageimages API** | Fallback photos when Pexels has no results | None | Free, no key |
| **Google OAuth 2.0** (`accounts.google.com`) | User authentication | `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET` | Free |
| **Browser Geolocation API** | User's GPS coordinates for distance-based ranking and transport options | None | Browser native |

---

## Running Locally

**Prerequisites:** Docker + Docker Compose

```bash
# 1. Clone the repo
git clone <repo-url>
cd travel-agent

# 2. Copy and fill environment variables
cp .env.example .env
# Edit .env — at minimum set GROQ_API_KEY or GEMINI_API_KEY

# 3. Start all services
docker compose up --build

# 4. Build the RAG knowledge base (first time only)
docker compose exec backend python3 ingest.py

# App is now running at http://localhost:3000
```

**Rebuilding after code changes:**
```bash
docker compose up --build --force-recreate
```

**Re-running enrichment scripts** (if you modify destination data):
```bash
# Expand destinations from Wikipedia categories
docker compose exec backend python3 scripts/wiki_expand.py

# Enrich with Wikivoyage + Wikipedia transport/food/highlights
docker compose exec backend python3 scripts/wiki_enrich.py

# Rebuild RAG index
docker compose exec backend python3 ingest.py
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GROQ_API_KEY` | Recommended | Primary LLM for plan generation |
| `GEMINI_API_KEY` | Optional | Fallback LLM if Groq is unavailable |
| `PEXELS_API_KEY` | Optional | Destination photos (Wikipedia fallback used if unset) |
| `GOOGLE_CLIENT_ID` | Optional | Google OAuth (login disabled if unset) |
| `GOOGLE_CLIENT_SECRET` | Optional | Google OAuth |
| `SECRET_KEY` | Optional | JWT signing key (auto-generated dev default) |
| `POSTGRES_PASSWORD` | Optional | PostgreSQL password (default: `postgres`) |
| `FRONTEND_URL` | Optional | Base URL for OAuth redirects (default: `http://localhost:3000`) |

---

## Project Structure

```
travel-agent/
├── docker-compose.yml
├── frontend/
│   ├── index.html          # Homepage — search form + results
│   ├── destination.html    # Destination detail page
│   ├── trips.html          # My Trips list
│   ├── trip.html           # Single shared trip view
│   ├── app.js              # Search logic, vibe picker, results rendering
│   ├── destination.js      # Destination page: photos, plan generation, packing list
│   ├── trips.js            # My Trips page
│   ├── auth.js             # OAuth login/logout, session state
│   ├── style.css           # Global styles
│   ├── destination.css     # Destination page styles
│   ├── nginx.conf          # Reverse proxy config (/ → static, /api → backend:8000)
│   └── Dockerfile
└── backend/
    ├── main.py             # FastAPI app — all routes
    ├── auth.py             # Google OAuth + JWT utilities
    ├── database.py         # SQLAlchemy setup
    ├── models.py           # User + SavedTrip ORM models
    ├── ingest.py           # Chunks destinations.json → ChromaDB
    ├── data/
    │   └── destinations.json   # 521 destination records
    ├── search/
    │   └── minsearch.py    # Lightweight TF-IDF index
    ├── rag/
    │   ├── embedder.py     # sentence-transformers semantic scoring
    │   ├── vector_store.py # ChromaDB wrapper
    │   ├── retriever.py    # RAG retrieval (typed chunks, diversity)
    │   ├── pipeline.py     # Prompt assembly + streaming orchestration
    │   ├── generator.py    # Groq / Gemini LLM calls + no-LLM fallback
    │   ├── chunker.py      # Splits destination fields into typed chunks
    │   ├── corpus_builder.py   # Builds text corpus for embedding
    │   └── photo_fetcher.py    # Pexels + Wikipedia photo fetch + cache
    ├── ranking/
    │   ├── scorer.py       # 8-signal composite ranking algorithm
    │   └── cost_estimator.py   # Trip cost estimation + transport options
    └── scripts/
        ├── wiki_expand.py  # Wikipedia category scraper (192 → 521 destinations)
        └── wiki_enrich.py  # Wikivoyage + Wikipedia field enrichment
```
