# Evaluations

Summary of the core benchmark and evaluation results for Paper Trail. Raw data lives in [`eval_results/`](eval_results/).

---

## 1. Corpus Composition

**Source:** `data/batch*/` directories (22,930 PDFs total)

| Source | Count | Share |
|--------|------:|------:|
| Mozilla Firefox | 6,835 | 29.8 % |
| LibreOffice | 5,571 | 24.3 % |
| Ghostscript | 5,442 | 23.7 % |
| pdf.js | 2,368 | 10.3 % |
| OpenOffice | 1,560 | 6.8 % |
| Apache Tika | 154 | 0.7 % |

**Takeaway:** Mozilla dominates the corpus; retrieval and extraction metrics should be interpreted with this skew in mind.

---

## 2. Hybrid Extraction Quality

**Source:** `training_data.json` (86 hand-annotated pages, Gold Set A)

### 2a. Router Decisions

| Path | Pages | Share |
|------|------:|------:|
| Native (pdfplumber) | 24 | 27.9 % |
| OCR fallback (GLM-OCR) | 62 | 72.1 % |

### 2b. CER / WER Comparison

| Metric | Native | OCR |
|--------|-------:|----:|
| Mean CER | 0.00 | 0.79 |
| Mean WER | 0.00 | 0.30 |

**Takeaway:** Native extraction is near-perfect when it succeeds, but only ~28 % of pages meet the 0.8 coverage threshold. The majority require OCR fallback, validating the hybrid router design.

---

## 3. RAG Retrieval Performance

**Source:** `eval_results/rag_retrieval_tiers_synthetic_v2.json` (50 synthetic single-hop queries, doc-level matching)

### 3a. Mean Recall@K

| Tier | @1 | @3 | @5 | @10 |
|------|---:|---:|---:|----:|
| Vector | 0.24 | 0.36 | 0.42 | 0.48 |
| BM25 | **0.36** | **0.48** | **0.52** | **0.58** |
| Hybrid | **0.36** | 0.50 | 0.50 | 0.54 |
| Hybrid+Graph | **0.36** | 0.50 | 0.50 | 0.54 |

### 3b. Mean MRR vs Latency

| Tier | Mean MRR | Mean Latency (ms) |
|------|---------:|------------------:|
| Vector | 0.309 | 79.4 |
| BM25 | 0.431 | 452.2 |
| Hybrid | 0.419 | 477.3 |
| Hybrid+Graph | 0.419 | 508.7 |

**Takeaway:** BM25 is the dominant signal for single-hop factual lookup. Hybrid+Graph added ~31 ms latency without improving MRR or recall in this benchmark; the graph signal may only surface in multi-hop or entity-centric queries (future work).
