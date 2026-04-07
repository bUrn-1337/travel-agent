"""
RAG Pipeline — ties Retrieve + Generate together.

Public functions:
  stream_travel_plan()   → Generator[str]  (SSE streaming, markdown)
  get_travel_plan_json() → dict            (blocking, structured JSON)

P2: Google Custom Search live snippets injected into LLM context.
P3: structured JSON path added.
"""
import logging
from typing import Generator

from rag.retriever import retrieve_for_plan
from rag.generator import generate_plan, generate_plan_json
from search.google_search import search_destination

logger = logging.getLogger(__name__)


def stream_travel_plan(
    destination: dict,
    days: int,
    budget_per_day: float,
    group_type: str,
    vibes: list[str],
    extra_query: str = "",
    n_retrieve: int = 10,
) -> Generator[str, None, None]:
    """
    Full RAG pipeline (P2):
      1. ChromaDB retrieve — static knowledge base chunks
      2. Google Search    — live web snippets (if API configured)
      3. LLM generate     — uses both sources

    destination: full destination dict from destinations.json
    """
    dest_id   = destination["id"]
    dest_name = destination["name"]
    state     = destination["state"]

    # ── Step 1: ChromaDB Retrieve ───────────────────────────────────────────
    logger.info(f"RAG retrieve: dest={dest_id}, days={days}, group={group_type}")
    chunks = retrieve_for_plan(
        destination_id=dest_id,
        user_query=extra_query,
        days=days,
        group_type=group_type,
        vibes=vibes,
        n_results=n_retrieve,
    )
    logger.info(f"Retrieved {len(chunks)} static chunks for {dest_name}")

    # ── Step 2: Google Search (live context) ────────────────────────────────
    live_snippets = search_destination(
        destination_name=dest_name,
        state=state,
        vibes=vibes,
        days=days,
        group_type=group_type,
    )
    if live_snippets:
        logger.info(f"Google Search: {len(live_snippets)} live snippets for {dest_name}")
    else:
        logger.info(f"Google Search: no results (not configured or rate limited)")

    # ── Step 3: Generate ────────────────────────────────────────────────────
    yield from generate_plan(
        destination_name=dest_name,
        state=state,
        chunks=chunks,
        days=days,
        budget_per_day=budget_per_day,
        group_type=group_type,
        vibes=vibes,
        extra_query=extra_query,
        live_snippets=live_snippets,
    )


def get_travel_plan_json(
    destination: dict,
    days: int,
    budget_per_day: float,
    group_type: str,
    vibes: list[str],
    extra_query: str = "",
    n_retrieve: int = 10,
) -> dict:
    """
    Blocking structured JSON plan (P3).
    Returns a plan dict; never raises — falls back to chunk-formatted data.
    """
    dest_id   = destination["id"]
    dest_name = destination["name"]
    state     = destination["state"]

    chunks = retrieve_for_plan(
        destination_id=dest_id,
        user_query=extra_query,
        days=days,
        group_type=group_type,
        vibes=vibes,
        n_results=n_retrieve,
    )

    live_snippets = search_destination(
        destination_name=dest_name,
        state=state,
        vibes=vibes,
        days=days,
        group_type=group_type,
    )

    return generate_plan_json(
        destination_name=dest_name,
        state=state,
        chunks=chunks,
        days=days,
        budget_per_day=budget_per_day,
        group_type=group_type,
        vibes=vibes,
        extra_query=extra_query,
        live_snippets=live_snippets,
    )
