"""
Travel Agent API — Prototype 1 + RAG
FastAPI backend: hybrid search (full-text + semantic) + composite ranking + RAG generation.
"""
import json
import sys
import logging
from pathlib import Path
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# Add project root to path so relative imports work
sys.path.insert(0, str(Path(__file__).parent))

from search.minsearch import Index
from rag.embedder import build_index, semantic_scores
from rag.vector_store import chunk_count
from rag.pipeline import stream_travel_plan, get_travel_plan_json
from ranking.scorer import rank_destinations
from ranking.cost_estimator import estimate_trip_cost

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

    plan = get_travel_plan_json(
        destination=dest,
        days=req.days,
        budget_per_day=req.budget_per_day,
        group_type=group_type,
        vibes=vibes,
        extra_query=req.query,
    )

    cost = estimate_trip_cost(
        dest=dest,
        days=req.days,
        group_type=group_type,
        budget_per_day=req.budget_per_day,
    )

    return {
        "destination": {"id": dest["id"], "name": dest["name"], "state": dest["state"]},
        "plan":         plan,
        "cost_estimate": cost,
    }


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
