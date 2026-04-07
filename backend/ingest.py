"""
Ingestion script — run once to build the RAG knowledge base.

What it does:
  1. Loads destinations.json
  2. For each destination:
       a. Fetches Wikipedia extract (optional, pass --no-wikipedia to skip)
       b. Builds a rich multi-section document
       c. Chunks it (section-aware)
       d. Embeds chunks with sentence-transformers
       e. Upserts into ChromaDB (idempotent)

Usage:
    python3 ingest.py                     # full ingest with Wikipedia
    python3 ingest.py --no-wikipedia      # fast ingest, no HTTP calls
    python3 ingest.py --dest manali,goa   # only re-ingest specific destinations

Requirements:
    pip install sentence-transformers chromadb httpx
"""
import sys
import json
import logging
import argparse
from pathlib import Path

# Make sure project root is on path
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Build the RAG knowledge base.")
    parser.add_argument("--no-wikipedia", action="store_true",
                        help="Skip Wikipedia fetching (faster, offline-safe)")
    parser.add_argument("--dest", type=str, default="",
                        help="Comma-separated destination IDs to (re-)ingest")
    parser.add_argument("--batch-size", type=int, default=16,
                        help="Embedding batch size")
    args = parser.parse_args()

    # ── Imports (late, so missing deps give a clear error) ──────────────────
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        logger.error("sentence-transformers not installed. Run:\n"
                     "  pip install sentence-transformers --break-system-packages")
        sys.exit(1)

    try:
        import chromadb  # noqa: F401
    except ImportError:
        logger.error("chromadb not installed. Run:\n"
                     "  pip install chromadb --break-system-packages")
        sys.exit(1)

    from rag.corpus_builder import build_document
    from rag.chunker        import chunk_document
    from rag.vector_store   import add_chunks, delete_destination, chunk_count

    # ── Load destinations ────────────────────────────────────────────────────
    data_path = Path(__file__).parent / "data" / "destinations.json"
    with open(data_path) as f:
        all_destinations: list[dict] = json.load(f)

    # Filter if --dest specified
    if args.dest:
        ids = {d.strip() for d in args.dest.split(",")}
        destinations = [d for d in all_destinations if d["id"] in ids]
        if not destinations:
            logger.error(f"No matching destinations found for: {ids}")
            sys.exit(1)
        logger.info(f"Ingesting only: {[d['id'] for d in destinations]}")
    else:
        destinations = all_destinations

    # ── Load embedding model ─────────────────────────────────────────────────
    logger.info("Loading sentence-transformers model (all-MiniLM-L6-v2)...")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    logger.info("Model ready.")

    use_wiki = not args.no_wikipedia
    if use_wiki:
        logger.info("Wikipedia fetching ENABLED (use --no-wikipedia to skip)")
    else:
        logger.info("Wikipedia fetching DISABLED")

    # ── Ingest loop ──────────────────────────────────────────────────────────
    total_chunks = 0
    for i, dest in enumerate(destinations, 1):
        dest_id   = dest["id"]
        dest_name = dest["name"]
        logger.info(f"[{i}/{len(destinations)}] Processing: {dest_name}")

        # Re-ingesting: delete old chunks first
        if args.dest:
            delete_destination(dest_id)

        # 1. Build document
        doc = build_document(dest, fetch_wikipedia=use_wiki)
        logger.debug(f"  Document length: {len(doc.split())} words")

        # 2. Chunk
        chunks = chunk_document(doc, dest_id, dest_name)
        logger.info(f"  → {len(chunks)} chunks created")

        # 3. Embed
        texts      = [c["text"] for c in chunks]
        embeddings = model.encode(
            texts,
            batch_size=args.batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,   # L2-normalize for cosine similarity
        ).tolist()

        # 4. Store
        add_chunks(chunks, embeddings)
        total_chunks += len(chunks)

    logger.info(
        f"\nIngestion complete. "
        f"{len(destinations)} destinations processed, "
        f"{total_chunks} chunks added. "
        f"Total in DB: {chunk_count()}"
    )


if __name__ == "__main__":
    main()
