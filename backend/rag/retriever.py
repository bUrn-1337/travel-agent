"""
Retriever: embeds a query and pulls relevant chunks from ChromaDB.

Two retrieval modes:
  1. Targeted   — destination_id known, retrieve all section types
                  (used when generating a full travel plan for one destination)
  2. Broad      — no destination_id, open retrieval
                  (used for cross-destination questions)

Returns a deduplicated, ranked list of chunks with similarity scores.
"""
import logging
from typing import Optional

from rag.embedder import _get_model          # reuse the same model instance
from rag.vector_store import query_chunks

logger = logging.getLogger(__name__)

# Ordered section types — ensures itinerary + highlights come before misc
PRIORITY_SECTIONS = ["itinerary", "highlights", "overview", "food", "transport",
                     "accommodation", "season", "suitability", "budget", "general"]


def _embed(text: str) -> list[float] | None:
    model = _get_model()
    if model is None:
        return None
    vec = model.encode([text], show_progress_bar=False)[0]
    return vec.tolist()


def retrieve(
    query: str,
    destination_id: Optional[str] = None,
    section_types: Optional[list[str]] = None,
    n_results: int = 8,
) -> list[dict]:
    """
    Embed query and retrieve top-n relevant chunks.

    Returns chunks sorted by: section priority first, similarity second.
    Each chunk dict: {text, destination_id, destination_name, section_type, similarity}
    """
    vec = _embed(query)
    if vec is None:
        logger.warning("Embedder unavailable — returning empty retrieval.")
        return []

    raw = query_chunks(
        query_embedding=vec,
        destination_id=destination_id,
        section_types=section_types,
        n_results=n_results,
    )

    # Deduplicate by chunk text (safety net for duplicate upserts)
    seen: set[str] = set()
    unique: list[dict] = []
    for c in raw:
        key = c["text"][:100]
        if key not in seen:
            seen.add(key)
            unique.append(c)

    # Sort: higher similarity first, but keep section priority as secondary
    def _sort_key(c: dict):
        try:
            priority = PRIORITY_SECTIONS.index(c["section_type"])
        except ValueError:
            priority = len(PRIORITY_SECTIONS)
        return (-c["similarity"], priority)

    unique.sort(key=_sort_key)
    return unique


def retrieve_for_plan(
    destination_id: str,
    user_query: str,
    days: int,
    group_type: str,
    vibes: list[str],
    n_results: int = 10,
) -> list[dict]:
    """
    Retrieve chunks specifically for generating a travel plan.

    Builds a rich query string that captures what the user cares about,
    then retrieves all section types for the destination.
    """
    vibe_str = " ".join(vibes) if vibes else ""
    rich_query = (
        f"{user_query} {vibe_str} {days} days {group_type} "
        f"itinerary food accommodation transport best time"
    ).strip()

    return retrieve(
        query=rich_query,
        destination_id=destination_id,
        n_results=n_results,
    )
