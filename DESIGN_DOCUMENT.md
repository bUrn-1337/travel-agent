# TravelMind — Indian Destination Recommender
**Date:** April 6, 2026
**Version:** 1.0

---

## 1. Summary

TravelMind is a web application that recommends Indian travel destinations to users based on their location, travel preferences, budget, trip duration, and group type. The system is designed to be **search and algorithm-first**, with AI (LLM) used only at the final generation step — not as the primary decision-maker.

The most critical design decisions are:

1. **Hybrid retrieval over pure vector search.** A TF-IDF inverted index (minsearch) runs in parallel with semantic cosine similarity. TF-IDF catches exact keyword matches (state names, destination names); sentence-transformers catch semantic intent ("peaceful mountains" → Spiti Valley). Neither alone is sufficient.

2. **Composite scoring algorithm over LLM ranking.** Seven deterministic factors — vibe match, semantic similarity, budget fit, group suitability, season, popularity, and trip duration — are combined with fixed weights. This is transparent, auditable, and fast. The LLM never decides which destination is "better."

3. **Section-aware RAG chunking over fixed-size slicing.** The knowledge base is split on document section boundaries (Overview, Food, Transport, Itinerary, etc.) rather than arbitrary word counts. This ensures that a query for "food in Manali" retrieves the Food chunk, not a fragment of an unrelated section.

4. **No hard LLM dependency.** The system degrades gracefully at every stage: if sentence-transformers fails, keyword search still works; if no LLM API key is set, the RAG stage formats retrieved chunks directly into a readable plan.

5. **Two-stage output pipeline.** Stage 1 returns up to 50 ranked destinations (search + score). Stage 2 generates a full travel plan (itinerary, food, transport, accommodation) only for the destination the user selects. This avoids unnecessary LLM calls.

---

## Main Design Part

---

### High-Level Design

#### System Architecture — Component Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                          USER (Browser)                             │
│   Inputs: city · vibes · days · budget · group type · free text     │
└────────────────────────────┬────────────────────────────────────────┘
                             │ HTTP (REST + SSE)
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       FASTAPI BACKEND                               │
│                                                                     │
│  ┌──────────────────┐   ┌───────────────────┐   ┌───────────────┐  │
│  │   /api/search    │   │  /api/generate    │   │ /api/rag/     │  │
│  │  POST endpoint   │   │  POST endpoint    │   │   status      │  │
│  └────────┬─────────┘   └────────┬──────────┘   └───────────────┘  │
│           │                      │                                  │
│  ┌────────▼──────────────────────▼──────────────────────────────┐  │
│  │                    SEARCH + RANKING MODULE                    │  │
│  │  minsearch (TF-IDF) ──► candidate pool                       │  │
│  │  embedder (cosine)  ──► semantic scores                       │  │
│  │  scorer             ──► composite ranking                     │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                       RAG MODULE                               │ │
│  │  corpus_builder ──► Wikipedia API + JSON → markdown docs      │ │
│  │  chunker        ──► section-aware chunks                      │ │
│  │  vector_store   ──► ChromaDB (cosine, persistent)             │ │
│  │  retriever      ──► embed query → filtered ChromaDB search    │ │
│  │  generator      ──► Groq / Gemini / fallback formatter        │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌──────────────────────────────────────┐                          │
│  │           DATA LAYER                 │                          │
│  │  destinations.json  (62 records)     │                          │
│  │  chroma_db/         (620 chunks)     │                          │
│  └──────────────────────────────────────┘                          │
└─────────────────────────────────────────────────────────────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
      Wikipedia API    Groq / Gemini   HuggingFace
      (MediaWiki)      (LLM, optional)  (embeddings)
```

---

#### Level 0 DFD — Context Diagram

```
                    ┌───────────────────────────┐
    city            │                           │  ranked destinations
    vibes    ──────►│     TRAVELMIND SYSTEM     ├──────────────────────► USER
    days            │                           │  travel plan (stream)
    budget   ◄──────│                           │
    group           └─────────────┬─────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │   EXTERNAL DATA SOURCES    │
                    │  · Wikipedia (knowledge)   │
                    │  · HuggingFace (model)     │
                    │  · Groq / Gemini (LLM)     │
                    └────────────────────────────┘
```

---

#### Level 1 DFD — System Decomposition

```
                        USER
                         │
           ┌─────────────▼──────────────┐
           │        query inputs         │
           └─────────────┬──────────────┘
                         │
           ┌─────────────▼──────────────┐         ┌──────────────────┐
           │   P1: QUERY PROCESSING     │         │  destinations    │
           │   normalise vibes          │◄────────│  .json (62)      │
           │   build query string       │         └──────────────────┘
           └─────────────┬──────────────┘
                         │ normalised query
            ┌────────────▼────────────┐
            │   P2: HYBRID RETRIEVAL  │
            │  ┌─────────────────┐    │
            │  │ TF-IDF search   │    │   ← inverted index over
            │  │ (minsearch)     │    │     name, description,
            │  └────────┬────────┘    │     vibes, highlights,
            │           │             │     state, region
            │  ┌────────▼────────┐    │
            │  │ Semantic search │    │   ← sentence-transformers
            │  │ (cosine sim)    │    │     all-MiniLM-L6-v2
            │  └────────┬────────┘    │
            └───────────┬─────────────┘
                        │ candidate pool + similarity scores
            ┌───────────▼─────────────┐
            │  P3: COMPOSITE SCORING  │   ← 7-factor weighted sum
            │  vibe_match  × 0.30     │     (see Low-Level Design)
            │  semantic    × 0.25     │
            │  budget_fit  × 0.18     │
            │  group_fit   × 0.10     │
            │  season_fit  × 0.07     │
            │  popularity  × 0.07     │
            │  duration    × 0.03     │
            └───────────┬─────────────┘
                        │ top-K ranked destinations
                        ▼
                      USER (sees results list)
                        │
                  [selects destination]
                        │
            ┌───────────▼─────────────┐
            │   P4: RAG RETRIEVAL     │   ← embed rich query
            │   ChromaDB query        │     filter by destination_id
            │   (filtered by dest_id) │     section types: itinerary,
            │                         │     food, transport, accomm…
            └───────────┬─────────────┘
                        │ top-K relevant chunks
            ┌───────────▼─────────────┐
            │   P5: PLAN GENERATION   │   ← prompt: chunks + user prefs
            │   Groq / Gemini LLM     │     streaming SSE response
            │   (or fallback format)  │
            └───────────┬─────────────┘
                        │ streamed markdown
                        ▼
                      USER (reads travel plan)
```

---

#### Ingestion Pipeline (offline, run once)

```
  destinations.json
         │
         ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                    INGESTION PIPELINE                        │
  │                                                             │
  │  For each of 62 destinations:                              │
  │                                                             │
  │  1. corpus_builder                                          │
  │     ├── Wikipedia MediaWiki API → intro text (≤1500 chars) │
  │     └── JSON metadata → 8 structured sections              │
  │         (Overview / Highlights / Food / Transport /         │
  │          Accommodation / Season / Suitability / Itinerary) │
  │                    ↓                                        │
  │  2. chunker                                                 │
  │     └── split on "## " headers → ~10 chunks/destination    │
  │         max 250 words/chunk, sub-split large sections       │
  │                    ↓                                        │
  │  3. embedder                                                │
  │     └── SentenceTransformer("all-MiniLM-L6-v2")            │
  │         → 384-dim normalised vectors                        │
  │                    ↓                                        │
  │  4. vector_store                                            │
  │     └── ChromaDB upsert                                     │
  │         id:       "{dest_id}_{section}_{i}"                 │
  │         metadata: {destination_id, destination_name,        │
  │                    section_type}                            │
  └─────────────────────────────────────────────────────────────┘
         │
         ▼
  chroma_db/ (persistent)
  620 chunks total (10 × 62 destinations)
```

---

#### Sequence Diagram — Search Flow

```
User          Frontend        FastAPI        minsearch       embedder       scorer
 │                │               │               │               │            │
 │──[POST /search]►               │               │               │            │
 │                │──────────────►│               │               │            │
 │                │               │──[search()]──►│               │            │
 │                │               │◄──candidates──│               │            │
 │                │               │──[embed query]────────────────►            │
 │                │               │◄──sim scores──────────────────│            │
 │                │               │──[rank()]──────────────────────────────────►
 │                │               │◄──ranked list──────────────────────────────│
 │                │◄──JSON─────────│               │               │            │
 │◄──results cards│               │               │               │            │
```

#### Sequence Diagram — RAG Generate Flow

```
User          Frontend        FastAPI        ChromaDB       embedder       LLM
 │                │               │               │               │          │
 │──[Generate]───►│               │               │               │          │
 │                │──[POST /gen]──►               │               │          │
 │                │               │──[embed query]────────────────►          │
 │                │               │◄──q_vector────────────────────│          │
 │                │               │──[query(dest_id filter)]──────►          │
 │                │               │◄──top-K chunks────────────────│          │
 │                │               │──[build prompt]               │          │
 │                │               │──[stream request]──────────────────────► │
 │                │               │◄──token stream─────────────────────────  │
 │                │◄──SSE tokens──│               │               │          │
 │◄─live markdown─│               │               │               │          │
```

---

### Low-Level Design

#### Algorithm 1: Composite Scoring

```
FUNCTION score_destination(dest, vibes, budget_per_day, days, group_type,
                           travel_month, semantic_score):

  // Factor 1: Vibe Match (0-1)
  dest_vibes ← set(dest.vibes)
  exact ← count(v in vibes where v in dest_vibes)
  partial ← 0.2 if any synonym of any v matches dest_vibes
  vibe_score ← min(1.0, exact/len(vibes) + partial)

  // Factor 2: Budget Fit (0-1)
  ratio ← dest.avg_cost_mid / budget_per_day
  IF ratio ≤ 1.0    → budget_score ← 1.0
  IF ratio ≤ 1.5    → budget_score ← 1.0 - (ratio - 1.0) × 1.4
  ELSE              → budget_score ← max(0, 0.3 - (ratio - 1.5) × 0.3)

  // Factor 3: Group Fit (0-1)
  group_score ← dest.group_suitability[group_type]   // pre-rated per destination

  // Factor 4: Season Fit (0-1)
  season_score ← 1.0 if travel_month in dest.best_months else 0.3

  // Factor 5: Popularity (0-1)
  pop_score ← dest.popularity / 10.0

  // Factor 6: Duration Fit (0-1)
  IF min_days ≤ days ≤ max_days → dur_score ← 1.0
  IF days < min_days            → dur_score ← max(0.1, 1 - (min-days)×0.2)
  IF days > max_days            → dur_score ← 0.7

  // Factor 7: Semantic (0-1)  ← from RAG retrieval
  sem_score ← semantic_score   // cosine similarity, pre-computed

  // Weighted sum
  composite ← 0.30×vibe_score  + 0.25×sem_score    + 0.18×budget_score
             + 0.10×group_score + 0.07×season_score + 0.07×pop_score
             + 0.03×dur_score

  RETURN { composite, breakdown: {all 7 sub-scores} }
```

---

#### Algorithm 2: TF-IDF Inverted Index (minsearch)

```
BUILD INDEX (offline, at startup):
  For each destination d in corpus:
    For each text_field f in [name, description, vibes, highlights, state, region]:
      tokens ← tokenise(lowercase(d[f]))
      For each token t:
        inv_index[f][t].append(d.id)
        tf[f][d.id][t] ← log(1 + count(t)) / log(1 + len(tokens))
        df[f][t] += 1

QUERY (at request time):
  query_tokens ← tokenise(query_string)
  scores ← defaultdict(0)
  For each field f:
    boost_f ← field_boost[f]    // name=4, vibes=3.5, state=2.5, ...
    For each token t in query_tokens:
      idf ← log((N - df[f][t] + 0.5) / (df[f][t] + 0.5) + 1)
      For each doc_id in inv_index[f][t]:
        scores[doc_id] += boost_f × tf[f][doc_id][t] × idf

  RETURN top-K docs sorted by scores[doc_id] descending
```

---

#### Algorithm 3: RAG Retrieval — Query Construction

```
INPUT: destination_id, user_query, days, group_type, vibes

rich_query ← concat(
  user_query,
  join(vibes, " "),
  str(days) + " days",
  group_type,
  "itinerary food accommodation transport best time"
)

q_vector ← SentenceTransformer.encode(rich_query, normalize=True)

results ← ChromaDB.query(
  query_embeddings = [q_vector],
  n_results        = 10,
  where            = { "destination_id": { "$eq": destination_id } },
  include          = ["documents", "metadatas", "distances"]
)

// Sort: similarity desc, with section-type priority
// Priority order: itinerary > highlights > overview > food >
//                 transport > accommodation > season > ...

RETURN sorted(results, key=(−similarity, section_priority))
```

---

#### Algorithm 4: Section-Aware Chunking

```
INPUT: document (multi-section markdown)

chunks ← []
sections ← split(document, on="^## " regex)

For each section in sections:
  heading     ← first_line(section).strip("# ")
  body        ← remaining_lines(section)
  section_tag ← map_heading_to_type(heading)
                // "Food & Cuisine" → "food"
                // "Getting There"  → "transport"
                // "Sample N-Day"   → "itinerary"

  full_text   ← heading + "\n" + body
  word_count  ← len(full_text.split())

  IF word_count ≤ 250:
    emit chunk(full_text, section_tag)
  ELSE:
    sub_chunks ← split_at_paragraph_boundaries(full_text, max=250)
    For each sc in sub_chunks:
      emit chunk(sc, section_tag)

chunk_id ← "{dest_id}_{section_tag}_{heading_index}_{sub_index}"
```

---

#### Data Schema: Destination Record

```
{
  "id":                 string,          
  "name":               string,
  "state":              string,
  "region":             string,          // North/South/East/West/Island/Northeast India
  "lat":                float,
  "lon":                float,
  "vibes":              [string],        // ["mountains", "adventure", "snow", ...]
  "primary_vibe":       string,
  "description":        string,          // 60-120 word curated description
  "avg_cost_budget":    int,             // INR per person per day
  "avg_cost_mid":       int,
  "avg_cost_luxury":    int,
  "min_days":           int,
  "max_days":           int,
  "best_months":        [int],           // [4, 5, 6, 9, 10] = Apr/May/Jun/Sep/Oct
  "group_suitability":  {                // 0.0 – 1.0 per group type
    "solo": float,
    "couple": float,
    "friends": float,
    "family": float
  },
  "popularity":         float,           // 0.0 – 10.0
  "nearest_airport":    string,
  "nearest_railway":    string,
  "nearest_major_city": string,
  "distance_from_delhi_km": int,
  "highlights":         [string],
  "food_specialties":   [string],
  "accommodation":      [string],
  "budget_range":       string           // "low" / "medium" / "high"
}
```

---

#### Data Schema: ChromaDB Chunk

```
Collection: "travel_knowledge"
Distance metric: cosine

Document (chunk text):
  "Food & Cuisine
   Must-try local specialties: Siddu, Dham, Babru, Trout Fish.
   The local food culture in Manali reflects the flavours of Himachal Pradesh."

Metadata:
  destination_id:   "manali"
  destination_name: "Manali"
  section_type:     "food"

ID: "manali_food_3_0"

Embedding: float[384]  (all-MiniLM-L6-v2, L2-normalised)
```

---

#### API Contract

| Endpoint | Method | Input | Output |
|---|---|---|---|
| `/api/search` | POST | SearchRequest | SearchResponse (JSON) |
| `/api/generate` | POST | GenerateRequest | SSE stream (text/event-stream) |
| `/api/rag/status` | GET | — | `{chunks_in_db, indexed, message}` |
| `/api/destinations` | GET | — | Minimal list (id, name, state) |
| `/api/destinations/{id}` | GET | dest_id | Full destination record |
| `/api/vibes` | GET | — | Available vibe categories |
| `/health` | GET | — | `{status, destinations_loaded, rag_chunks}` |

**SearchRequest schema:**
```json
{
  "city":           "Delhi",
  "vibes":          ["mountains", "adventure"],
  "days":           5,
  "budget_per_day": 3000,
  "group_type":     "couple",
  "query":          "snow mountains",
  "travel_month":   4,
  "top_k":          30
}
```

**GenerateRequest schema:**
```json
{
  "destination_id": "manali",
  "days":           5,
  "budget_per_day": 3000,
  "group_type":     "couple",
  "vibes":          ["mountains", "adventure"],
  "query":          ""
}
```

**SSE stream format:**
```
data: # Travel Plan: Manali\n*5-day trip for couple*\n\n
data: ## Day-by-Day Itinerary\n\n
data: **Day 1:** Arrive in Manali...
data: [DONE]
```

---

#### Technology Stack

| Layer | Technology | Reason |
|---|---|---|
| Web Framework | FastAPI (Python) | Async, native SSE, auto OpenAPI docs |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) | Free, local, 384-dim, fast |
| Vector Store | ChromaDB (persistent) | No separate server, cosine distance, metadata filters |
| Full-text Search | Custom minsearch (inverted index) | Lightweight, field-level boosting, no external dependency |
| LLM (primary) | Groq llama-3.1-8b-instant | Free tier, ~200 tokens/sec, OpenAI-compatible |
| LLM (secondary) | Google Gemini 1.5 Flash | Free tier, multimodal-ready for future |
| HTTP Client | httpx | Sync + async, streaming, used for Wikipedia + LLM |
| Data Format | JSON | Human-readable, easy to extend |
| Frontend | Vanilla JS + CSS | No build step, instant open-in-browser |

---

## 2. Questions

**Q1. Does the design clearly separate requirements from design from implementation?**

Yes. Requirements (what the system must do) live in the destination data schema and API contract. Design decisions (how it achieves them) are captured in the scoring algorithm and RAG pipeline architecture above. Implementation details (Python class names, file paths) are in the source code but not repeated here. The composite scoring algorithm, for example, is a design decision — the choice of 7 factors and their weights is justified by the travel domain, not by the programming language.

**Q2. Is the high-level design sufficiently complete? Are all major system components identified?**

The component diagram identifies six subsystems: query processing, hybrid retrieval (minsearch + embedder), composite ranker, RAG corpus builder, ChromaDB vector store, and LLM generator. External dependencies (Wikipedia, HuggingFace, Groq/Gemini) are explicitly named. The one component not yet implemented is a Google Search/SerpAPI integration for live destination data — this is planned for Prototype 2 and intentionally absent from Prototype 1.

**Q3. Is the low-level design sufficient to guide implementation?**

The four core algorithms (composite scoring, TF-IDF inverted index, RAG query construction, section-aware chunking) are each specified in pseudocode with clear inputs, outputs, and decision rules. The ChromaDB schema specifies collection name, distance metric, document format, metadata fields, and ID format. The API contract specifies all endpoints with request/response shapes.

**Q4. Are the key design trade-offs identified and justified?**

- **Hybrid search vs. pure vector search:** Vector search alone misses exact name/state matches ("Goa" has low semantic distance from "beach" but a user searching "Goa" should get Goa first). Keyword search alone misses semantic intent. Hybrid gives precision + recall.

- **ChromaDB vs. Qdrant vs. Pinecone:** ChromaDB runs in-process with no separate server, which is correct for a local-first prototype. Qdrant would be better at scale (>100k chunks) but adds operational overhead.

- **Fixed weights vs. learned weights:** The 7-factor weights (vibe 30%, semantic 25%, etc.) are set by domain reasoning, not trained. This is intentional for Prototype 1 — explainable and easy to tune. A future version could learn weights from user feedback (click-through rate as signal).

- **Section-aware chunking vs. fixed-size chunking:** Fixed-size chunks (e.g., 256 tokens) fragment sentences and mix sections. Section-aware chunks align with retrieval queries: "food in Manali" retrieves the Food section, not a mixture. The trade-off is that sections vary in size (19–100 words), which is acceptable for 62 destinations.

**Q5. Are scalability and failure modes addressed?**

- **No API key:** Generator falls back to formatted chunk display. The system always returns useful output.
- **Wikipedia unavailable:** `corpus_builder` catches all HTTP exceptions and falls back to the curated JSON description.
- **ChromaDB empty:** `vector_store.query_chunks` returns `[]`; the generator displays an instructional message to run `ingest.py`.
- **sentence-transformers unavailable:** `embedder._get_model()` returns `None`; semantic scoring is skipped and keyword search alone is used.
- **Scalability:** The current in-memory TF-IDF index and numpy cosine similarity are appropriate for 62 destinations. At 10,000+ destinations, both would need replacement (Elasticsearch for TF-IDF, Qdrant for vectors).

---

## 3. Comments

- **Prototype roadmap:** This document describes the final intended system. Prototype 1 (built) covers search + ranking. Prototype 2 will add GPS-based distance scoring and Google Search integration for live data. Prototype 3 adds LLM generation as currently designed. Prototype 4 introduces a cost minimization layer (greedy transport + accommodation optimizer).

- **LLM prompt design:** The current prompt instructs the LLM to use *only* the retrieved context, not its general knowledge. This is intentional — it grounds the output in real, structured data and prevents hallucination of incorrect prices, distances, or transport routes.

- **The vibe taxonomy** (mountains, beach, heritage, adventure, wildlife, spiritual, offbeat, desert, backwaters, nature, honeymoon, trekking) was chosen to cover the major Indian travel archetypes. The synonym map in `scorer.py` handles common synonyms ("hill station" → mountains, "rafting" → adventure).

- **Field boost values** in minsearch (name=4, vibes=3.5, state=2.5, highlights=2, description=1.5) were set by reasoning: a match in the destination name is more precise than a match in its description. These are tunable without code changes.

- **The 62-destination dataset** was curated to cover all major Indian travel categories across all regions. Each entry includes lat/lon for future GPS distance integration, and `distance_from_delhi_km` as a proxy until GPS is added.
