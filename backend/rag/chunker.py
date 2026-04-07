"""
Section-aware text chunker.

Strategy:
  1. Split document on "## " headings → one chunk per section
  2. If a section exceeds MAX_WORDS, split further at paragraph boundaries
  3. Each chunk carries: text, section_label, chunk_index

This produces semantically coherent chunks (a "Food" chunk, a "Transport" chunk, etc.)
rather than arbitrary fixed-size slices — much better for targeted RAG retrieval.
"""
import re

MAX_WORDS    = 250   # hard cap per chunk before sub-splitting
OVERLAP_SENT = 1     # carry N sentences of overlap between sub-chunks (future)

# Map heading text → canonical section_type tag
SECTION_TYPE_MAP: dict[str, str] = {
    "overview":             "overview",
    "highlights":           "highlights",
    "attractions":          "highlights",
    "food":                 "food",
    "cuisine":              "food",
    "getting there":        "transport",
    "local transport":      "transport",
    "where to stay":        "accommodation",
    "accommodation":        "accommodation",
    "best time":            "season",
    "who should":           "suitability",
    "itinerary":            "itinerary",
    "budget":               "budget",
    "tips":                 "tips",
}


def _section_type(heading: str) -> str:
    h = heading.lower()
    for key, tag in SECTION_TYPE_MAP.items():
        if key in h:
            return tag
    return "general"


def _split_paragraphs(text: str, max_words: int) -> list[str]:
    """Split a long section into paragraph-sized sub-chunks."""
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_words = 0
    for para in paragraphs:
        wc = len(para.split())
        if current_words + wc > max_words and current:
            chunks.append("\n\n".join(current))
            current = []
            current_words = 0
        current.append(para)
        current_words += wc
    if current:
        chunks.append("\n\n".join(current))
    return chunks or [text]


def chunk_document(document: str, destination_id: str, destination_name: str) -> list[dict]:
    """
    Split a destination document into retrieval-ready chunks.

    Returns list of dicts:
    {
        "text":             str,        # the actual chunk content
        "destination_id":   str,
        "destination_name": str,
        "section_type":     str,        # food / transport / itinerary / …
        "chunk_id":         str,        # unique ID for ChromaDB
    }
    """
    chunks: list[dict] = []

    # Split on ## headings (keep the heading with its section body)
    # Pattern: "## Heading\n...content..." or "# Title\n...content..."
    parts = re.split(r"(?=^#{1,2} )", document, flags=re.MULTILINE)

    chunk_idx = 0
    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Extract heading text (first line)
        lines       = part.splitlines()
        heading     = lines[0].lstrip("# ").strip()
        body        = "\n".join(lines[1:]).strip()
        section_tag = _section_type(heading)

        # Combine heading + body for embedding context
        full_text = f"{heading}\n{body}" if body else heading
        word_count = len(full_text.split())

        if word_count <= MAX_WORDS:
            sub_chunks = [full_text]
        else:
            # Sub-split large sections (e.g. a long Wikipedia overview)
            sub_chunks = _split_paragraphs(full_text, MAX_WORDS)

        for i, sc in enumerate(sub_chunks):
            sc = sc.strip()
            if len(sc.split()) < 10:   # skip tiny fragments
                continue
            chunks.append({
                "text":             sc,
                "destination_id":   destination_id,
                "destination_name": destination_name,
                "section_type":     section_tag,
                "chunk_id":         f"{destination_id}_{section_tag}_{chunk_idx}_{i}",
            })
        chunk_idx += 1

    return chunks
