"""
Minsearch: Minimal in-memory full-text search with field boosting.
Inspired by the GROQ/LLM-RAG project approach.
"""
import re
import math
from collections import defaultdict


def tokenize(text: str) -> list[str]:
    """Lowercase, remove punctuation, split on whitespace."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return [t for t in text.split() if len(t) > 1]


class Index:
    """
    Inverted index with TF-IDF scoring and field-level boosting.

    Example:
        idx = Index(text_fields=["name","description","vibes"], keyword_fields=["state"])
        idx.fit(documents)
        results = idx.search("mountains adventure", boost={"name": 3, "vibes": 2}, top_k=30)
    """

    def __init__(self, text_fields: list[str], keyword_fields: list[str] = None):
        self.text_fields = text_fields
        self.keyword_fields = keyword_fields or []
        self.docs: list[dict] = []
        # inverted index: field -> token -> [doc_indices]
        self._index: dict[str, dict[str, list[int]]] = {}
        # term frequency per doc per field
        self._tf: dict[str, list[dict[str, float]]] = {}
        # document frequency per field per token
        self._df: dict[str, dict[str, int]] = {}

    def fit(self, documents: list[dict]) -> "Index":
        self.docs = documents
        for field in self.text_fields:
            inv: dict[str, list[int]] = defaultdict(list)
            tf_list: list[dict[str, float]] = []
            df: dict[str, int] = defaultdict(int)
            for i, doc in enumerate(documents):
                text = str(doc.get(field, ""))
                # flatten lists to string
                if isinstance(doc.get(field), list):
                    text = " ".join(str(x) for x in doc[field])
                tokens = tokenize(text)
                counts: dict[str, int] = defaultdict(int)
                for t in tokens:
                    counts[t] += 1
                    inv[t].append(i)
                # TF = count / total_tokens (log-normalised)
                total = len(tokens) or 1
                tf_list.append({t: (1 + math.log(c)) / (1 + math.log(total))
                                 for t, c in counts.items()})
                for t in counts:
                    df[t] += 1
            self._index[field] = dict(inv)
            self._tf[field] = tf_list
            self._df[field] = dict(df)
        return self

    def search(
        self,
        query: str,
        filter_dict: dict = None,
        boost: dict[str, float] = None,
        top_k: int = 50,
    ) -> list[dict]:
        """
        Returns top_k documents sorted by TF-IDF score with field boosting.
        filter_dict: {field: value} hard equality filters (keyword fields).
        boost: {field: multiplier} boost factors per field.
        """
        boost = boost or {f: 1.0 for f in self.text_fields}
        query_tokens = tokenize(query)
        if not query_tokens:
            return self.docs[:top_k]

        n = len(self.docs)
        scores: dict[int, float] = defaultdict(float)

        for field in self.text_fields:
            b = boost.get(field, 1.0)
            field_inv = self._index.get(field, {})
            field_tf = self._tf.get(field, [])
            field_df = self._df.get(field, {})
            for token in query_tokens:
                if token not in field_inv:
                    continue
                # IDF
                df_t = field_df.get(token, 1)
                idf = math.log((n - df_t + 0.5) / (df_t + 0.5) + 1)
                for doc_idx in field_inv[token]:
                    tf = field_tf[doc_idx].get(token, 0)
                    scores[doc_idx] += b * tf * idf

        # Keyword field exact-match bonus
        for field in self.keyword_fields:
            for token in query_tokens:
                for i, doc in enumerate(self.docs):
                    val = str(doc.get(field, "")).lower()
                    if token in val:
                        scores[i] += 2.0  # hard bonus

        # Apply filters
        if filter_dict:
            for i in list(scores.keys()):
                doc = self.docs[i]
                for field, value in filter_dict.items():
                    doc_val = doc.get(field)
                    if isinstance(doc_val, list):
                        if value not in doc_val:
                            del scores[i]
                            break
                    elif str(doc_val).lower() != str(value).lower():
                        del scores[i]
                        break

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [self.docs[i] for i, _ in ranked[:top_k]]
