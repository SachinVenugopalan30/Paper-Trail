"""BM25Okapi implementation for keyword-based retrieval.

Manual implementation to avoid adding rank_bm25 as a new dependency.
"""

import json
import math
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> List[str]:
    return text.lower().split()


class BM25Index:
    """BM25Okapi index over TextChunk objects."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._corpus: List[List[str]] = []
        self._metadata: List[Dict[str, Any]] = []  # chunk_id, text, metadata per doc
        self._idf: Dict[str, float] = {}
        self._doc_lengths: List[int] = []
        self._avgdl: float = 0.0
        self._built = False

    # ------------------------------------------------------------------
    # Building
    # ------------------------------------------------------------------

    def add_chunks_no_build(self, chunks) -> None:
        """Add TextChunk objects without rebuilding the index (for batch streaming)."""
        for c in chunks:
            tokens = _tokenize(c.text)
            self._corpus.append(tokens)
            self._metadata.append(
                {
                    "chunk_id": c.chunk_id,
                    "text": c.text,
                    "metadata": {
                        "document_id": c.document_id,
                        "page_number": c.page_number,
                        "source_file": c.source_file,
                        **c.metadata,
                    },
                }
            )

    def build(self) -> None:
        """Rebuild the inverted index after all chunks have been added."""
        self._build()

    def add_chunks(self, chunks) -> None:
        """Add TextChunk objects and rebuild the index immediately (convenience)."""
        self.add_chunks_no_build(chunks)
        self._build()

    def _build(self):
        N = len(self._corpus)
        if N == 0:
            return
        self._doc_lengths = [len(doc) for doc in self._corpus]
        self._avgdl = sum(self._doc_lengths) / N

        # Document frequency per term
        df: Dict[str, int] = {}
        for doc in self._corpus:
            for term in set(doc):
                df[term] = df.get(term, 0) + 1

        # IDF (BM25 variant): log((N - df + 0.5) / (df + 0.5) + 1)
        self._idf = {
            term: math.log((N - freq + 0.5) / (freq + 0.5) + 1)
            for term, freq in df.items()
        }
        self._built = True

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def query(self, query_text: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Return top-k results as {chunk_id, text, score, metadata}."""
        if not self._built or not self._corpus:
            return []

        query_tokens = _tokenize(query_text)
        scores = self._score_all(query_tokens)

        # Sort descending
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        results = []
        for idx, score in ranked[:top_k]:
            if score <= 0:
                break
            entry = self._metadata[idx]
            results.append(
                {
                    "chunk_id": entry["chunk_id"],
                    "text": entry["text"],
                    "score": float(score),
                    "metadata": entry["metadata"],
                }
            )
        return results

    def _score_all(self, query_tokens: List[str]) -> List[float]:
        scores = [0.0] * len(self._corpus)
        k1, b, avgdl = self.k1, self.b, self._avgdl

        for term in query_tokens:
            idf = self._idf.get(term, 0.0)
            if idf == 0:
                continue
            for i, doc in enumerate(self._corpus):
                tf = doc.count(term)
                if tf == 0:
                    continue
                dl = self._doc_lengths[i]
                numerator = tf * (k1 + 1)
                denominator = tf + k1 * (1 - b + b * dl / avgdl)
                scores[i] += idf * numerator / denominator
        return scores

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str) -> None:
        """Persist corpus + metadata to JSON."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        data = {
            "k1": self.k1,
            "b": self.b,
            "corpus": self._corpus,
            "metadata": self._metadata,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        logger.info(f"BM25 index saved to {path} ({len(self._corpus)} docs)")

    def load(self, path: str) -> bool:
        """Load from JSON. Returns True on success."""
        p = Path(path)
        if not p.exists():
            return False
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.k1 = data["k1"]
            self.b = data["b"]
            self._corpus = data["corpus"]
            self._metadata = data["metadata"]
            self._build()
            logger.info(f"BM25 index loaded from {path} ({len(self._corpus)} docs)")
            return True
        except Exception as e:
            logger.error(f"Failed to load BM25 index: {e}")
            return False

    def count(self) -> int:
        return len(self._corpus)
