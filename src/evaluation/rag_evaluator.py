"""Recall@K and MRR Evaluation for the RAG Retrieval Pipeline.

Evaluates retrieval quality against a curated query set with known relevant documents.
Supports per-tier ablation (E7-E10 from the proposal):
  E7: BM25 only
  E8: Vector only
  E9: Hybrid lexical + vector (no graph)
  E10: Hybrid + graph-aware expansion

Usage:
    python3 -m src.cli rag eval --queries data/evaluation/rag_eval_queries.json
    python3 -m src.cli rag eval --queries data/evaluation/rag_eval_queries.json --tiers --output report.json
"""

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class RAGEvalQuery:
    query_id: str
    question: str
    relevant_document_ids: List[str]
    relevant_chunk_ids: List[str] = field(default_factory=list)
    expected_entities: List[str] = field(default_factory=list)
    category: str = "single-hop"   # "single-hop" | "multi-hop"
    difficulty: str = "medium"     # "easy" | "medium" | "hard"
    notes: str = ""


@dataclass
class RAGEvalResult:
    query_id: str
    question: str
    recall_at_k: Dict[int, float]     # {1: 0.0, 3: 0.5, 5: 1.0, 10: 1.0}
    mrr: float
    retrieved_ids: List[str]          # document_ids of top-K retrieved chunks
    relevant_ids: List[str]
    source_breakdown: Dict[str, int]  # {"bm25": 3, "vector": 4, "graph": 1}
    latency_ms: float = 0.0


@dataclass
class RAGEvalReport:
    tier: str                          # "hybrid" | "bm25" | "vector" | "graph"
    results: List[RAGEvalResult] = field(default_factory=list)
    mean_recall_at_k: Dict[int, float] = field(default_factory=dict)
    mean_mrr: float = 0.0
    mean_latency_ms: float = 0.0
    per_category_mrr: Dict[str, float] = field(default_factory=dict)
    total_queries: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def print_report(self):
        print(f"\n{'='*60}")
        print(f"RAG Evaluation Report — Tier: {self.tier.upper()}")
        print(f"Generated: {self.timestamp}")
        print(f"{'='*60}")
        print(f"Total queries: {self.total_queries}")
        print(f"Mean MRR:      {self.mean_mrr:.4f}")
        print(f"Mean latency:  {self.mean_latency_ms:.1f} ms")
        print(f"\nRecall@K:")
        for k, v in sorted(self.mean_recall_at_k.items()):
            print(f"  @{k:<4} {v:.4f}")
        if self.per_category_mrr:
            print(f"\nMRR by category:")
            for cat, mrr in sorted(self.per_category_mrr.items()):
                print(f"  {cat:<15} {mrr:.4f}")
        print(f"{'='*60}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tier": self.tier,
            "timestamp": self.timestamp,
            "total_queries": self.total_queries,
            "mean_mrr": self.mean_mrr,
            "mean_latency_ms": self.mean_latency_ms,
            "mean_recall_at_k": {str(k): v for k, v in self.mean_recall_at_k.items()},
            "per_category_mrr": self.per_category_mrr,
            "results": [
                {
                    "query_id": r.query_id,
                    "question": r.question,
                    "mrr": r.mrr,
                    "recall_at_k": {str(k): v for k, v in r.recall_at_k.items()},
                    "latency_ms": r.latency_ms,
                    "source_breakdown": r.source_breakdown,
                    "retrieved_ids": r.retrieved_ids,
                    "relevant_ids": r.relevant_ids,
                }
                for r in self.results
            ],
        }


# ── Metric helpers ─────────────────────────────────────────────────────────────

def load_eval_queries(path: str) -> List[RAGEvalQuery]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [RAGEvalQuery(**q) for q in data]


def compute_recall_at_k(
    retrieved_ids: List[str],
    relevant_ids: List[str],
    k_values: List[int],
) -> Dict[int, float]:
    """Fraction of relevant docs found in top-K retrieved results."""
    relevant_set = set(relevant_ids)
    recall = {}
    for k in k_values:
        top_k = set(retrieved_ids[:k])
        found = len(top_k & relevant_set)
        recall[k] = found / len(relevant_set) if relevant_set else 0.0
    return recall


def compute_mrr(retrieved_ids: List[str], relevant_ids: List[str]) -> float:
    """1 / rank of the first relevant result (0 if none found)."""
    relevant_set = set(relevant_ids)
    for rank, doc_id in enumerate(retrieved_ids, start=1):
        if doc_id in relevant_set:
            return 1.0 / rank
    return 0.0


def compute_recall_at_k_hits(hits: List[bool], k_values: List[int]) -> Dict[int, float]:
    """Recall@K when ground truth is a single relevant item (binary hit per rank)."""
    recall = {}
    for k in k_values:
        recall[k] = 1.0 if any(hits[:k]) else 0.0
    return recall


def compute_mrr_hits(hits: List[bool]) -> float:
    """MRR from a per-rank boolean hit list."""
    for rank, hit in enumerate(hits, start=1):
        if hit:
            return 1.0 / rank
    return 0.0


def _extract_doc_id(result) -> str:
    """Extract document_id from a RetrievalResult (metadata or chunk_id prefix)."""
    meta = getattr(result, "metadata", {}) or {}
    if "document_id" in meta:
        return meta["document_id"]
    # Fall back: strip trailing _chunk_N from chunk_id
    chunk_id = getattr(result, "chunk_id", "")
    parts = chunk_id.rsplit("_chunk_", 1)
    return parts[0] if len(parts) == 2 else chunk_id


# ── Tier adapters ──────────────────────────────────────────────────────────────

class _BM25TierRetriever:
    """Wraps BM25Index to match the HybridRetriever.retrieve() signature."""
    def __init__(self, bm25_index, top_k: int = 10):
        self.bm25 = bm25_index
        self.top_k = top_k

    def retrieve(self, query: str):
        from src.rag.hybrid import RetrievalResult
        results = self.bm25.query(query, top_k=self.top_k)
        return [
            RetrievalResult(
                chunk_id=r["chunk_id"],
                text=r.get("text", ""),
                score=r.get("score", 0.0),
                source="bm25",
                metadata=r.get("metadata", {}),
            )
            for r in results
        ]


class _VectorTierRetriever:
    """Wraps VectorStore to match the HybridRetriever.retrieve() signature."""
    def __init__(self, vector_store, top_k: int = 10):
        self.vs = vector_store
        self.top_k = top_k

    def retrieve(self, query: str):
        from src.rag.hybrid import RetrievalResult
        results = self.vs.query(query, top_k=self.top_k)
        return [
            RetrievalResult(
                chunk_id=r["chunk_id"],
                text=r.get("text", ""),
                score=r.get("score", 0.0),
                source="vector",
                metadata=r.get("metadata", {}),
            )
            for r in results
        ]


class _HybridNoGraphRetriever:
    """Hybrid BM25 + vector only (no graph) — corresponds to E9."""
    def __init__(self, vector_store, bm25_index, top_k: int = 10, final_top_k: int = 8):
        from src.rag.hybrid import HybridRetriever
        self._inner = HybridRetriever(
            vector_store=vector_store,
            bm25_index=bm25_index,
            graph_retriever=None,
            config={"retrieval": {"top_k": top_k, "final_top_k": final_top_k}},
        )

    def retrieve(self, query: str):
        return self._inner.retrieve(query)


# ── Evaluator ──────────────────────────────────────────────────────────────────

def evaluate_retriever(
    retriever,
    queries: List[RAGEvalQuery],
    k_values: List[int] = None,
    tier_name: str = "hybrid",
) -> RAGEvalReport:
    """Evaluate a retriever against the curated query set."""
    if k_values is None:
        k_values = [1, 3, 5, 10]

    report = RAGEvalReport(tier=tier_name)
    category_mrrs: Dict[str, List[float]] = {}

    for query in queries:
        t0 = time.perf_counter()
        try:
            raw_results = retriever.retrieve(query.question)
        except Exception as e:
            raw_results = []
        latency_ms = (time.perf_counter() - t0) * 1000

        retrieved_doc_ids = [_extract_doc_id(r) for r in raw_results]
        retrieved_chunk_ids = [getattr(r, "chunk_id", "") for r in raw_results]

        # Match per rank: a result is a hit if EITHER its doc_id OR chunk_id is in
        # the relevant set. Doc-level matching automatically gives credit for any
        # chunk from the source doc — works for both broad (doc-level GT) and
        # strict (chunk-level GT) eval queries.
        relevant_set = set(query.relevant_document_ids) | set(query.relevant_chunk_ids)
        relevant_ids = sorted(relevant_set)
        hits = [
            (doc_id in relevant_set) or (chunk_id in relevant_set)
            for doc_id, chunk_id in zip(retrieved_doc_ids, retrieved_chunk_ids)
        ]
        recall = compute_recall_at_k_hits(hits, k_values)
        mrr = compute_mrr_hits(hits)

        source_breakdown: Dict[str, int] = {}
        for r in raw_results:
            src = getattr(r, "source", "unknown")
            source_breakdown[src] = source_breakdown.get(src, 0) + 1

        result = RAGEvalResult(
            query_id=query.query_id,
            question=query.question,
            recall_at_k=recall,
            mrr=mrr,
            retrieved_ids=retrieved_doc_ids,
            relevant_ids=relevant_ids,
            source_breakdown=source_breakdown,
            latency_ms=latency_ms,
        )
        report.results.append(result)

        cat = query.category or "unspecified"
        category_mrrs.setdefault(cat, []).append(mrr)

    # Aggregate
    report.total_queries = len(queries)
    if report.results:
        report.mean_mrr = round(sum(r.mrr for r in report.results) / len(report.results), 4)
        report.mean_latency_ms = round(sum(r.latency_ms for r in report.results) / len(report.results), 2)
        for k in k_values:
            vals = [r.recall_at_k.get(k, 0.0) for r in report.results]
            report.mean_recall_at_k[k] = round(sum(vals) / len(vals), 4)
    report.per_category_mrr = {
        cat: round(sum(vals) / len(vals), 4)
        for cat, vals in category_mrrs.items()
    }
    return report


def evaluate_all_tiers(
    vector_store,
    bm25_index,
    graph_retriever,
    hybrid_retriever,
    queries: List[RAGEvalQuery],
    k_values: List[int] = None,
) -> Dict[str, RAGEvalReport]:
    """Formal ablation E7-E10:
      E7: BM25 only
      E8: Vector only
      E9: Hybrid lexical + vector (no graph)
      E10: Hybrid + graph-aware (full pipeline)
    """
    if k_values is None:
        k_values = [1, 3, 5, 10]

    print("Running E7: BM25-only...")
    e7 = evaluate_retriever(_BM25TierRetriever(bm25_index), queries, k_values, tier_name="bm25")

    print("Running E8: Vector-only...")
    e8 = evaluate_retriever(_VectorTierRetriever(vector_store), queries, k_values, tier_name="vector")

    print("Running E9: Hybrid (BM25 + vector, no graph)...")
    e9 = evaluate_retriever(_HybridNoGraphRetriever(vector_store, bm25_index), queries, k_values, tier_name="hybrid_no_graph")

    print("Running E10: Hybrid + graph...")
    e10 = evaluate_retriever(hybrid_retriever, queries, k_values, tier_name="hybrid_graph")

    return {"bm25": e7, "vector": e8, "hybrid_no_graph": e9, "hybrid_graph": e10}
