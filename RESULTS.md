# Paper Trail — Results Summary

CSE573 Group 30 | Last updated: 2026-04-01

---

## Corpus Coverage

| Corpus | Batch | PDFs Processed |
|--------|-------|---------------:|
| GhostScript | batch2 | 49 |
| Apache Tika | batch2 | 3 |
| Mozilla Firefox | batch3 | 53 |
| LibreOffice | batch4 | 44 |
| OpenOffice | batch4 | 14 |
| pdf.js | batch4 | 13 |
| Mozilla (initial test set) | — | 5 |
| **Total** | | **182** |

---

## Gold Set A — Extraction Quality (E1 / E2 / E3)

**86 manually annotated pages** from the GhostScript corpus (scanned PDFs — worst case for native extraction).

| Method | Avg CER ↓ | Avg WER ↓ |
|--------|----------:|----------:|
| E1 — Native (pdfplumber) | 1.2691 | 0.8895 |
| E2 — OCR (GLM-OCR) | **0.6053** | **0.5509** |

> **Key finding:** OCR reduces CER by ~52% and WER by ~38% on scanned documents. The hybrid router selects OCR on 62 of 86 annotated pages (72%), confirming native extraction degrades badly on image-heavy PDFs.

E3 (hybrid) numbers pending — requires running the benchmark on the annotated set:
```bash
python3 -m src.cli benchmark data/batch2/GHOSTSCRIPT --ablation E3 --output results_e3.json
```

---

## Knowledge Graph (Full Laptop Run — Completed)

Built from **104 PDFs** using `--method both` (LLM + classical spaCy per document). Runtime: 183.3 minutes.

| Metric | Value |
|--------|------:|
| PDFs processed | 104 |
| Extractor runs completed | 186 (2 extractors × ~104, minus skipped) |
| Failed | 0 |
| Entities extracted (this run) | 6,420 |
| Relations extracted (this run) | 5,215 |

### Neo4j Graph — Final Node Counts

| Label | Nodes |
|-------|------:|
| Reference | 2,610 |
| Organization | 1,479 |
| Person | 1,083 |
| Technology | 1,047 |
| Location | 447 |
| Document | 344 |
| Topic | 332 |
| Process | 1 |
| **Total nodes** | **7,343** |
| **Total relations** | **8,575** |

> Full-scale graph (all 22,000+ docs) is being built on Sol supercomputer. These counts will grow significantly after import.

---

## Gold Set B — Entity Extraction Quality (E4 / E5 / E6)

Extraction files generated for **52 LLM docs** and **54 classical docs** (overlap from `--method both` run).

| Method | Total Entities | Total Relations | Avg Entities/Doc | Avg Relations/Doc |
|--------|---------------:|----------------:|-----------------:|------------------:|
| E4 — LLM (Ollama/Gemma3) | 1,196 | 653 | 23.0 | 12.6 |
| E5 — Classical (spaCy NER) | 2,209 | 2,141 | 40.9 | 39.6 |

> **Note:** Classical produces more raw entities/relations because spaCy fires on every NER token and the rule-based extractor emits a Document→Entity relation for each entity found. Raw count is not a quality metric — precision/recall from manual annotation (Gold Set B) is required to compare fairly.
>
> Annotate using: `streamlit run src/evaluation/entity_annotation_tool.py`
> Then run: `python3 -m src.cli eval entity-report --output data/evaluation/gold_set_b_report.json`

---

## RAG Index (Built from Subset)

| Component | Size | Chunks |
|-----------|-----:|-------:|
| BM25 index (keyword) | 4.8 MB | 2,368 |
| ChromaDB (vector, all-MiniLM-L6-v2) | 21.2 MB | 2,368 |

> Full-scale index will be exported from Sol and loaded here for the final demo.

---

## RAG Evaluation (E7 / E8 / E9 / E10)

**Pending** — requires filling `relevant_document_ids` in `data/evaluation/rag_eval_queries.json` and running:

```bash
python3 -m src.cli rag eval --tiers --output data/evaluation/rag_ablation.json
```

10 evaluation queries are prepared across:
- Single-hop retrieval (easy/medium)
- Multi-hop graph traversal (medium/hard)

Expected metrics: Recall@1, Recall@3, Recall@5, Recall@10, MRR, latency (ms).

---

## Pending Work

| Task | Status |
|------|--------|
| Sol full-corpus extraction + KG build | Running |
| Sol RAG index build + export | Queued after KG |
| Gold Set A — E3 hybrid benchmark | To do |
| Gold Set B — manual annotation | To do |
| RAG eval E7-E10 | Blocked on Sol export |
| Entity canonicalization (post-import) | To do after Sol export |
| Gradio chatbot demo | Ready to run after Sol export |
