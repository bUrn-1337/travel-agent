"""
Semantic embedder using sentence-transformers.
Embeds destination descriptions at startup; cosine similarity at query time.
This is the RAG retrieval component — no LLM generation in Prototype 1.
"""
import numpy as np
from typing import Optional
import logging

logger = logging.getLogger(__name__)

_model = None
_destination_embeddings: Optional[np.ndarray] = None
_destination_ids: list[str] = []


def _get_model():
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading sentence-transformers model...")
            _model = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("Model loaded.")
        except ImportError:
            logger.warning(
                "sentence-transformers not installed. Semantic scoring disabled. "
                "Run: pip install sentence-transformers"
            )
            _model = None
    return _model


def build_destination_text(dest: dict) -> str:
    """Create a rich text blob from a destination dict for embedding."""
    parts = [
        dest.get("name", ""),
        dest.get("state", ""),
        dest.get("description", ""),
        " ".join(dest.get("vibes", [])),
        " ".join(dest.get("highlights", [])),
        " ".join(dest.get("food_specialties", [])),
    ]
    return " ".join(p for p in parts if p)


def build_index(destinations: list[dict]) -> None:
    """Pre-compute embeddings for all destinations. Call at startup."""
    global _destination_embeddings, _destination_ids
    model = _get_model()
    if model is None:
        _destination_embeddings = None
        return
    texts = [build_destination_text(d) for d in destinations]
    _destination_ids = [d["id"] for d in destinations]
    logger.info(f"Embedding {len(texts)} destinations...")
    _destination_embeddings = model.encode(texts, batch_size=32, show_progress_bar=False)
    # L2-normalise so cosine = dot product
    norms = np.linalg.norm(_destination_embeddings, axis=1, keepdims=True)
    _destination_embeddings = _destination_embeddings / np.maximum(norms, 1e-9)
    logger.info("Destination embeddings built.")


def semantic_scores(query: str, destination_ids: list[str]) -> dict[str, float]:
    """
    Returns a dict {destination_id: cosine_similarity} for the given ids.
    Scores are in [0, 1] (after clipping).
    Returns empty dict if embeddings unavailable.
    """
    global _destination_embeddings, _destination_ids
    model = _get_model()
    if model is None or _destination_embeddings is None:
        return {}

    # Embed query
    q_vec = model.encode([query], show_progress_bar=False)[0]
    norm = np.linalg.norm(q_vec)
    if norm < 1e-9:
        return {}
    q_vec = q_vec / norm

    # Build index map
    id_to_idx = {did: i for i, did in enumerate(_destination_ids)}

    result = {}
    for did in destination_ids:
        idx = id_to_idx.get(did)
        if idx is None:
            continue
        sim = float(np.dot(q_vec, _destination_embeddings[idx]))
        result[did] = max(0.0, min(1.0, (sim + 1) / 2))  # map [-1,1] → [0,1]
    return result
