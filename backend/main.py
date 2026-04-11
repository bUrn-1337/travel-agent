"""
Travel Agent API — Prototype 1 + RAG
FastAPI backend: hybrid search (full-text + semantic) + composite ranking + RAG generation.
"""
import json
import os
import sys
import logging
from pathlib import Path
from datetime import datetime
from contextlib import asynccontextmanager

import secrets
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, RedirectResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

# Add project root to path so relative imports work
sys.path.insert(0, str(Path(__file__).parent))

from search.minsearch import Index
from rag.embedder import build_index, semantic_scores
from rag.vector_store import chunk_count
from rag.pipeline import stream_travel_plan, get_travel_plan_json
from rag.retriever import retrieve_for_plan
from ranking.scorer import rank_destinations
from ranking.cost_estimator import estimate_trip_cost
from rag.photo_fetcher import get_photo_url, get_photos
from database import get_db, init_db
from models import User, SavedTrip
import auth as auth_utils

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Simple in-memory plan cache  key → plan dict
# Keyed by (dest_id, days, budget_tier, group_type, vibes_tuple)
# ---------------------------------------------------------------------------
_PLAN_CACHE: dict[tuple, dict] = {}
_MAX_CACHE  = 200   # evict oldest when full

def _cache_key(dest_id: str, days: int, budget: float, group: str, vibes: list[str]) -> tuple:
    budget_tier = int(budget // 500) * 500   # round to nearest 500
    return (dest_id, days, budget_tier, group, tuple(sorted(vibes)))

def _cache_get(key: tuple) -> dict | None:
    return _PLAN_CACHE.get(key)

def _cache_set(key: tuple, value: dict) -> None:
    if len(_PLAN_CACHE) >= _MAX_CACHE:
        oldest = next(iter(_PLAN_CACHE))
        del _PLAN_CACHE[oldest]
    _PLAN_CACHE[key] = value

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
DATA_PATH = Path(__file__).parent / "data" / "destinations.json"

with open(DATA_PATH) as f:
    DESTINATIONS: list[dict] = json.load(f)

# ---------------------------------------------------------------------------
# Search index (built at startup)
# ---------------------------------------------------------------------------
SEARCH_INDEX = Index(
    text_fields=["name", "description", "vibes", "highlights", "food_specialties", "state", "region"],
    keyword_fields=["state", "region"],
)
SEARCH_INDEX.fit(DESTINATIONS)

BOOST = {
    "name": 4.0,
    "vibes": 3.5,
    "description": 1.5,
    "highlights": 2.0,
    "food_specialties": 1.0,
    "state": 2.5,
    "region": 2.0,
}

# ---------------------------------------------------------------------------
# Startup: build semantic embeddings
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initialising database...")
    init_db()
    logger.info("Building semantic index...")
    build_index(DESTINATIONS)
    yield
    logger.info("Shutting down.")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Travel Agent API",
    description="Indian destination recommendation — hybrid search + composite ranking",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
VALID_VIBES = [
    "mountains", "beach", "heritage", "adventure", "wildlife",
    "spiritual", "offbeat", "desert", "backwaters", "nature",
    "honeymoon", "family", "trekking",
]

VALID_GROUP_TYPES = ["solo", "couple", "friends", "family"]


class SearchRequest(BaseModel):
    city: str = Field(default="", description="User's current city (used for context)")
    vibes: list[str] = Field(default=[], description="Selected travel vibes")
    days: int = Field(default=5, ge=1, le=30, description="Number of travel days")
    budget_per_day: float = Field(default=2000, ge=0, description="Budget per person per day in INR")
    group_type: str = Field(default="friends", description="Group type: solo/couple/friends/family")
    query: str = Field(default="", description="Free text describing the trip")
    travel_month: int = Field(default=0, ge=0, le=12, description="Month of travel (1-12), 0 = current month")
    top_k: int = Field(default=30, ge=5, le=50, description="Max results to return")
    # P2: GPS coordinates from browser geolocation API
    user_lat: float | None = Field(default=None, description="User latitude (GPS)")
    user_lon: float | None = Field(default=None, description="User longitude (GPS)")


class SearchResponse(BaseModel):
    destinations: list[dict]
    top_picks: list[dict]   # top 3 — frontend auto-generates plans for these
    total: int
    query_info: dict


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/api/vibes")
def get_vibes():
    """Return all available vibe categories."""
    return {"vibes": VALID_VIBES}


@app.get("/api/destinations")
def list_destinations():
    """Return all destinations (minimal info)."""
    return [
        {
            "id": d["id"],
            "name": d["name"],
            "state": d["state"],
            "primary_vibe": d["primary_vibe"],
            "popularity": d["popularity"],
        }
        for d in DESTINATIONS
    ]


@app.get("/api/destinations/geo")
def destinations_geo():
    """Minimal lat/lon payload for map initialisation — all 144 destinations."""
    return [
        {
            "id":           d["id"],
            "name":         d["name"],
            "state":        d["state"],
            "region":       d["region"],
            "lat":          d["lat"],
            "lon":          d["lon"],
            "primary_vibe": d.get("primary_vibe", ""),
            "vibes":        d.get("vibes", []),
            "popularity":   d.get("popularity", 5),
        }
        for d in DESTINATIONS
    ]


@app.get("/api/destinations/{dest_id}")
def get_destination(dest_id: str):
    """Return full details for a single destination."""
    dest = next((d for d in DESTINATIONS if d["id"] == dest_id), None)
    if not dest:
        raise HTTPException(status_code=404, detail="Destination not found")
    return dest


@app.post("/api/search", response_model=SearchResponse)
def search(req: SearchRequest):
    """
    Main search endpoint.

    Pipeline:
    1. Build composite query string from vibes + free text
    2. Full-text search via minsearch (TF-IDF + field boosting) → candidate pool
    3. Semantic scoring via sentence-transformers
    4. Composite ranking (vibe match + budget + group + season + popularity + semantic)
    5. Return top_k sorted results
    """
    # Normalise vibes
    vibes = [v.lower().strip() for v in req.vibes if v.strip()]
    group_type = req.group_type.lower() if req.group_type else "friends"
    travel_month = req.travel_month or datetime.now().month

    # Build query string: combine vibes + free text for both keyword and semantic search
    query_parts = vibes + ([req.query] if req.query else []) + ([req.city] if req.city else [])
    query_str = " ".join(query_parts)

    # --- Step 1: Full-text retrieval (get broad candidate pool) ---
    if query_str.strip():
        candidates = SEARCH_INDEX.search(
            query=query_str,
            boost=BOOST,
            top_k=len(DESTINATIONS),  # rank all, semantic filter comes later
        )
    else:
        candidates = DESTINATIONS[:]

    # --- Step 2: Semantic scoring ---
    candidate_ids = [d["id"] for d in candidates]
    sem_scores = semantic_scores(query_str, candidate_ids) if query_str else {}

    # --- Step 3: Composite ranking (now includes GPS distance) ---
    ranked = rank_destinations(
        destinations=candidates,
        vibes=vibes,
        budget_per_day=req.budget_per_day,
        days=req.days,
        group_type=group_type,
        travel_month=travel_month,
        semantic_scores_map=sem_scores,
        user_lat=req.user_lat,
        user_lon=req.user_lon,
        top_k=req.top_k,
    )

    gps_active = req.user_lat is not None and req.user_lon is not None

    # P3: attach deterministic cost estimates to top 3 picks
    # P5: attach photo URLs
    top3 = ranked[:3]
    for dest in top3:
        dest["cost_estimate"] = estimate_trip_cost(
            dest=dest,
            days=req.days,
            group_type=group_type,
            budget_per_day=req.budget_per_day,
            user_lat=req.user_lat,
            user_lon=req.user_lon,
        )
        photos = get_photos(dest["id"], dest["name"], dest.get("state", ""))
        dest["photo_url"]  = photos[0] if photos else None
        dest["photo_urls"] = photos

    return SearchResponse(
        destinations=ranked,
        top_picks=top3,
        total=len(ranked),
        query_info={
            "query":            query_str,
            "vibes":            vibes,
            "days":             req.days,
            "budget_per_day":   req.budget_per_day,
            "group_type":       group_type,
            "travel_month":     travel_month,
            "semantic_enabled": bool(sem_scores),
            "gps_active":       gps_active,
        },
    )


class GenerateRequest(BaseModel):
    destination_id: str = Field(..., description="Destination ID from search results")
    days:           int   = Field(default=5,    ge=1, le=30)
    budget_per_day: float = Field(default=2000, ge=0)
    group_type:     str   = Field(default="friends")
    vibes:          list[str] = Field(default=[])
    query:          str   = Field(default="", description="Extra user question / context")


@app.get("/api/photos/{dest_id}")
def get_photo(dest_id: str, count: int = 6):
    """Return photo URLs for a destination (P5). count=1..15. Cached per dest_id."""
    dest = next((d for d in DESTINATIONS if d["id"] == dest_id), None)
    if not dest:
        raise HTTPException(status_code=404, detail="Destination not found")
    count = max(1, min(count, 15))
    urls = get_photos(dest_id, dest["name"], dest.get("state", ""), count=count)
    return {"photo_url": urls[0] if urls else None, "photo_urls": urls, "name": dest["name"]}


@app.post("/api/generate")
async def generate(req: GenerateRequest):
    """
    RAG generation endpoint — streams a full travel plan for one destination.

    Pipeline:
      1. Retrieve relevant chunks from ChromaDB (filtered by destination_id)
      2. Build prompt with retrieved context + user preferences
      3. Stream LLM response (Groq / Gemini) or format fallback
    Returns: SSE text/event-stream
    """
    dest = next((d for d in DESTINATIONS if d["id"] == req.destination_id), None)
    if not dest:
        raise HTTPException(status_code=404, detail="Destination not found")

    vibes      = [v.lower().strip() for v in req.vibes if v.strip()]
    group_type = req.group_type.lower() or "friends"

    def _event_stream():
        for token in stream_travel_plan(
            destination=dest,
            days=req.days,
            budget_per_day=req.budget_per_day,
            group_type=group_type,
            vibes=vibes,
            extra_query=req.query,
        ):
            # SSE format: "data: <token>\n\n"
            # Encode newlines so SSE parser handles them correctly
            escaped = token.replace("\n", "\\n")
            yield f"data: {escaped}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class StructuredRequest(BaseModel):
    destination_id: str   = Field(..., description="Destination ID")
    days:           int   = Field(default=5,    ge=1, le=30)
    budget_per_day: float = Field(default=2000, ge=0)
    group_type:     str   = Field(default="friends")
    vibes:          list[str] = Field(default=[])
    query:          str   = Field(default="")


@app.post("/api/generate/structured")
async def generate_structured(req: StructuredRequest):
    """
    P3 — Returns a complete structured JSON travel plan (blocking, not streamed).
    Response includes: summary, day-by-day itinerary, food guide,
    transport options, accommodation options, and tips.
    """
    dest = next((d for d in DESTINATIONS if d["id"] == req.destination_id), None)
    if not dest:
        raise HTTPException(status_code=404, detail="Destination not found")

    vibes      = [v.lower().strip() for v in req.vibes if v.strip()]
    group_type = req.group_type.lower() or "friends"

    ck = _cache_key(dest["id"], req.days, req.budget_per_day, group_type, vibes)
    plan = _cache_get(ck)
    if plan is None:
        plan = get_travel_plan_json(
            destination=dest,
            days=req.days,
            budget_per_day=req.budget_per_day,
            group_type=group_type,
            vibes=vibes,
            extra_query=req.query,
        )
        _cache_set(ck, plan)
    else:
        logger.info(f"Cache hit for {dest['id']}")

    cost = estimate_trip_cost(
        dest=dest,
        days=req.days,
        group_type=group_type,
        budget_per_day=req.budget_per_day,
    )

    return {
        "destination":  {"id": dest["id"], "name": dest["name"], "state": dest["state"]},
        "plan":          plan,
        "cost_estimate": cost,
        "cached":        ck in _PLAN_CACHE,
    }


class RefineRequest(BaseModel):
    destination_id: str       = Field(...)
    days:           int       = Field(default=5, ge=1, le=30)
    budget_per_day: float     = Field(default=2000, ge=0)
    group_type:     str       = Field(default="friends")
    vibes:          list[str] = Field(default=[])
    existing_plan:  str       = Field(default="", description="Previously generated plan (markdown)")
    user_message:   str       = Field(..., description="Follow-up request from user")


@app.post("/api/refine")
async def refine_plan(req: RefineRequest):
    """
    Refinement chat — streams an updated/focused answer given an existing plan + follow-up.
    Uses retrieved chunks for context + the previous plan summary.
    SSE stream of markdown tokens.
    """
    dest = next((d for d in DESTINATIONS if d["id"] == req.destination_id), None)
    if not dest:
        raise HTTPException(status_code=404, detail="Destination not found")

    vibes      = [v.lower().strip() for v in req.vibes if v.strip()]
    group_type = req.group_type.lower() or "friends"

    # Retrieve relevant chunks for the follow-up question
    chunks = retrieve_for_plan(
        destination_id=req.destination_id,
        user_query=req.user_message,
        days=req.days,
        group_type=group_type,
        vibes=vibes,
        n_results=6,
    )

    groq_key   = os.getenv("GROQ_API_KEY",   "").strip()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()

    # Build refinement prompt
    context = "\n\n".join(c["text"] for c in chunks[:4])
    vibe_str   = ", ".join(vibes) or "general"
    budget_str = f"₹{int(req.budget_per_day):,}"

    existing_snippet = req.existing_plan[:1200] if req.existing_plan else "No previous plan."

    prompt = f"""You are an expert Indian travel planner. The user has a travel plan for {dest['name']}, {dest['state']} and wants a specific follow-up answered.

TRIP DETAILS: {req.days} days | {budget_str}/day | {group_type} | {vibe_str}

EXISTING PLAN SUMMARY (first 1200 chars):
{existing_snippet}

RELEVANT KNOWLEDGE BASE:
{context}

USER FOLLOW-UP REQUEST:
{req.user_message}

Answer the user's specific request directly and concisely. Be practical and specific to {dest['name']}. Use markdown formatting."""

    from rag.generator import _stream_groq, _stream_gemini

    def _event_stream():
        try:
            if groq_key:
                yield from (
                    f"data: {t.replace(chr(10), chr(92)+'n')}\n\n"
                    for t in _stream_groq(prompt, groq_key)
                )
            elif gemini_key:
                yield from (
                    f"data: {t.replace(chr(10), chr(92)+'n')}\n\n"
                    for t in _stream_gemini(prompt, gemini_key)
                )
            else:
                yield f"data: No LLM key configured. Cannot refine plan.\\n\n\n"
        except Exception as e:
            yield f"data: Error: {str(e)}\\n\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/cache/stats")
def cache_stats():
    return {"cached_plans": len(_PLAN_CACHE), "max_cache": _MAX_CACHE}


@app.get("/api/rag/status")
def rag_status():
    """Return the current state of the RAG knowledge base."""
    n = chunk_count()
    return {
        "chunks_in_db":  n,
        "indexed":       n > 0,
        "message": (
            "RAG knowledge base ready." if n > 0
            else "Knowledge base is empty. Run: python3 ingest.py"
        ),
    }


@app.get("/health")
def health():
    return {"status": "ok", "destinations_loaded": len(DESTINATIONS), "rag_chunks": chunk_count()}


# ---------------------------------------------------------------------------
# P7 — AUTH ROUTES
# ---------------------------------------------------------------------------

@app.get("/auth/google")
def google_login(response: RedirectResponse = None):
    """Redirect browser to Google OAuth consent screen."""
    state = secrets.token_urlsafe(16)
    url   = auth_utils.get_google_auth_url(state)
    resp  = RedirectResponse(url=url)
    resp.set_cookie("oauth_state", state, httponly=True, samesite="lax", max_age=300)
    return resp


@app.get("/auth/google/callback")
def google_callback(code: str = None, state: str = None, error: str = None,
                    request: Request = None, db: Session = Depends(get_db)):
    """Handle Google OAuth callback, create/update user, set JWT cookie."""
    frontend = auth_utils.FRONTEND_URL

    if error or not code:
        return RedirectResponse(url=f"{frontend}/?auth_error=access_denied")

    try:
        tokens      = auth_utils.exchange_code(code)
        google_user = auth_utils.get_google_user(tokens["access_token"])
    except Exception as e:
        logger.error(f"OAuth error: {e}")
        return RedirectResponse(url=f"{frontend}/?auth_error=oauth_failed")

    # Upsert user
    user = db.query(User).filter(User.google_id == google_user["sub"]).first()
    if not user:
        user = User(
            google_id  = google_user["sub"],
            email      = google_user.get("email", ""),
            name       = google_user.get("name", ""),
            avatar_url = google_user.get("picture"),
        )
        db.add(user)
    else:
        user.name       = google_user.get("name", user.name)
        user.avatar_url = google_user.get("picture", user.avatar_url)
    db.commit()
    db.refresh(user)

    token = auth_utils.create_jwt(user.id)
    resp  = RedirectResponse(url=f"{frontend}/?login=success")
    auth_utils.set_auth_cookie(resp, token)
    resp.delete_cookie("oauth_state")
    return resp


@app.get("/auth/me")
def get_me(request: Request, db: Session = Depends(get_db)):
    """Return current user info from JWT cookie."""
    user = auth_utils.get_optional_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"id": user.id, "name": user.name, "email": user.email, "avatar_url": user.avatar_url}


@app.post("/auth/logout")
def logout():
    resp = JSONResponse({"message": "Logged out"})
    auth_utils.clear_auth_cookie(resp)
    return resp


# ---------------------------------------------------------------------------
# P7 — TRIP ROUTES
# ---------------------------------------------------------------------------

class SaveTripRequest(BaseModel):
    destination_id:   str       = Field(...)
    destination_name: str       = Field(...)
    destination_data: dict      = Field(...)
    plan_markdown:    str       = Field(default="")
    days:             int       = Field(default=5)
    budget_per_day:   int       = Field(default=2000)
    group_type:       str       = Field(default="friends")
    vibes:            list[str] = Field(default=[])
    photo_url:        str | None = Field(default=None)


@app.post("/api/trips")
def save_trip(req: SaveTripRequest, request: Request,
              db: Session = Depends(get_db)):
    user = auth_utils.get_current_user(request, db)
    trip = SavedTrip(
        user_id          = user.id,
        destination_id   = req.destination_id,
        destination_name = req.destination_name,
        destination_data = req.destination_data,
        plan_markdown    = req.plan_markdown,
        days             = req.days,
        budget_per_day   = req.budget_per_day,
        group_type       = req.group_type,
        vibes            = req.vibes,
        photo_url        = req.photo_url,
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return {"id": trip.id, "message": "Trip saved"}


@app.get("/api/trips")
def list_trips(request: Request, db: Session = Depends(get_db)):
    user  = auth_utils.get_current_user(request, db)
    trips = (db.query(SavedTrip)
               .filter(SavedTrip.user_id == user.id)
               .order_by(SavedTrip.created_at.desc())
               .all())
    return [t.to_dict() for t in trips]


@app.delete("/api/trips/{trip_id}")
def delete_trip(trip_id: str, request: Request, db: Session = Depends(get_db)):
    user = auth_utils.get_current_user(request, db)
    trip = db.query(SavedTrip).filter(
        SavedTrip.id == trip_id, SavedTrip.user_id == user.id
    ).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    db.delete(trip)
    db.commit()
    return {"message": "Deleted"}


@app.post("/api/trips/{trip_id}/share")
def share_trip(trip_id: str, request: Request, db: Session = Depends(get_db)):
    user = auth_utils.get_current_user(request, db)
    trip = db.query(SavedTrip).filter(
        SavedTrip.id == trip_id, SavedTrip.user_id == user.id
    ).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    trip.is_public = True
    db.commit()
    share_url = f"{auth_utils.FRONTEND_URL}/trip/{trip.id}"
    return {"share_url": share_url}


@app.get("/api/share/{trip_id}")
def get_shared_trip(trip_id: str, db: Session = Depends(get_db)):
    """Public endpoint — returns a trip that has been made shareable."""
    trip = db.query(SavedTrip).filter(
        SavedTrip.id == trip_id, SavedTrip.is_public == True  # noqa: E712
    ).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found or not public")
    return trip.to_dict()
