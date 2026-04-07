"""
ChromaDB vector store wrapper.

Single persistent collection: "travel_knowledge"
  - Stores all destination chunks
  - Metadata filters enable per-destination and per-section retrieval
  - Uses cosine distance (inner product on normalised vectors)
"""
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Persistent storage path (relative to this file's parent = backend/)
CHROMA_DIR = Path(__file__).parent.parent / "chroma_db"
COLLECTION_NAME = "travel_knowledge"

_client = None
_collection = None


def _get_collection():
    global _client, _collection
    if _collection is not None:
        return _collection
    try:
        import chromadb
        _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        _collection = _client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"ChromaDB collection ready: {_collection.count()} chunks stored.")
        return _collection
    except ImportError:
        logger.error("chromadb not installed. Run: pip install chromadb")
        return None
    except Exception as e:
        logger.error(f"ChromaDB init failed: {e}")
        return None


def add_chunks(chunks: list[dict], embeddings: list[list[float]]) -> None:
    """
    Insert chunks into ChromaDB.

    chunks: list of dicts from chunker.chunk_document()
    embeddings: parallel list of embedding vectors
    """
    col = _get_collection()
    if col is None:
        return

    ids       = [c["chunk_id"] for c in chunks]
    documents = [c["text"] for c in chunks]
    metadatas = [
        {
            "destination_id":   c["destination_id"],
            "destination_name": c["destination_name"],
            "section_type":     c["section_type"],
        }
        for c in chunks
    ]

    # ChromaDB upsert in batches of 500
    batch_size = 500
    for i in range(0, len(ids), batch_size):
        col.upsert(
            ids=ids[i:i+batch_size],
            documents=documents[i:i+batch_size],
            embeddings=embeddings[i:i+batch_size],
            metadatas=metadatas[i:i+batch_size],
        )
    logger.info(f"Upserted {len(ids)} chunks. Total: {col.count()}")


def query_chunks(
    query_embedding: list[float],
    destination_id: Optional[str] = None,
    section_types: Optional[list[str]] = None,
    n_results: int = 6,
) -> list[dict]:
    """
    Retrieve top-n chunks by cosine similarity.

    destination_id: if set, restrict to that destination (for detail generation)
    section_types:  if set, restrict to those section types  e.g. ["food","transport"]
    Returns list of {text, destination_id, destination_name, section_type, distance}
    """
    col = _get_collection()
    if col is None or col.count() == 0:
        return []

    # Build ChromaDB where filter
    where: Optional[dict] = None
    if destination_id and section_types:
        where = {
            "$and": [
                {"destination_id": {"$eq": destination_id}},
                {"section_type":   {"$in": section_types}},
            ]
        }
    elif destination_id:
        where = {"destination_id": {"$eq": destination_id}}
    elif section_types:
        where = {"section_type": {"$in": section_types}}

    try:
        kwargs: dict = {
            "query_embeddings": [query_embedding],
            "n_results":        min(n_results, col.count()),
            "include":          ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        results = col.query(**kwargs)
    except Exception as e:
        logger.error(f"ChromaDB query failed: {e}")
        return []

    out = []
    docs      = results.get("documents", [[]])[0]
    metas     = results.get("metadatas", [[]])[0]
    distances = results.get("distances",  [[]])[0]
    for doc, meta, dist in zip(docs, metas, distances):
        out.append({
            "text":             doc,
            "destination_id":   meta.get("destination_id", ""),
            "destination_name": meta.get("destination_name", ""),
            "section_type":     meta.get("section_type", ""),
            "similarity":       round(1 - dist, 4),   # cosine dist → similarity
        })
    return out


def chunk_count() -> int:
    col = _get_collection()
    return col.count() if col else 0


def delete_destination(destination_id: str) -> None:
    """Remove all chunks for a destination (useful for re-ingestion)."""
    col = _get_collection()
    if col is None:
        return
    col.delete(where={"destination_id": {"$eq": destination_id}})
    logger.info(f"Deleted chunks for '{destination_id}'")
