"""Hybrid retriever: RRF fusion of BM25, vector, and graph results."""

import logging
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    chunk_id: str
    text: str
    score: float
    source: str       # "bm25" | "vector" | "graph"
    metadata: Dict[str, Any]


def _rrf_fuse(result_lists: List[List[Dict[str, Any]]], k: int = 60) -> List[Dict[str, Any]]:
    """Reciprocal Rank Fusion across multiple ranked lists.

    Each list item must have a 'chunk_id' key.
    Returns a merged, re-ranked list sorted by RRF score descending.
    """
    rrf_scores: Dict[str, float] = {}
    best_doc: Dict[str, Dict[str, Any]] = {}

    for result_list in result_lists:
        for rank, doc in enumerate(result_list):
            cid = doc["chunk_id"]
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
            if cid not in best_doc:
                best_doc[cid] = doc

    ranked = sorted(rrf_scores.items(), key=lambda x: -x[1])
    fused = []
    for cid, rrf_score in ranked:
        entry = dict(best_doc[cid])
        entry["rrf_score"] = rrf_score
        fused.append(entry)
    return fused


class HybridRetriever:
    """Combines BM25, vector, and graph retrievers with RRF fusion."""

    def __init__(self, vector_store, bm25_index, graph_retriever, config: Optional[Dict[str, Any]] = None):
        self.vector_store = vector_store
        self.bm25_index = bm25_index
        self.graph_retriever = graph_retriever
        cfg = config or {}
        ret = cfg.get("retrieval", {})
        self.top_k: int = ret.get("top_k", 10)
        self.final_top_k: int = ret.get("final_top_k", 8)
        self.rrf_k: int = ret.get("rrf_k", 60)

    def retrieve(self, query: str) -> List[RetrievalResult]:
        """Run all three retrievers and fuse with RRF."""
        bm25_results = []
        vector_results = []
        graph_results = []

        # BM25
        try:
            bm25_results = self.bm25_index.query(query, top_k=self.top_k)
            for r in bm25_results:
                r.setdefault("source", "bm25")
        except Exception as e:
            logger.warning(f"BM25 retrieval failed: {e}")

        # Vector
        try:
            vector_results = self.vector_store.query(query, top_k=self.top_k)
            for r in vector_results:
                r.setdefault("source", "vector")
        except Exception as e:
            logger.warning(f"Vector retrieval failed: {e}")

        # Graph
        if self.graph_retriever is not None:
            try:
                graph_results = self.graph_retriever.retrieve(query, top_k=self.top_k)
                for r in graph_results:
                    r.setdefault("source", "graph")
            except Exception as e:
                logger.warning(f"Graph retrieval failed: {e}")

        fused = _rrf_fuse([bm25_results, vector_results, graph_results], k=self.rrf_k)

        results = []
        for entry in fused[: self.final_top_k]:
            results.append(
                RetrievalResult(
                    chunk_id=entry["chunk_id"],
                    text=entry.get("text", ""),
                    score=entry["rrf_score"],
                    source=entry.get("source", "unknown"),
                    metadata=entry.get("metadata", {}),
                )
            )
        return results
