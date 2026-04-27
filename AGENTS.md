# AGENTS.md

Instructions for AI assistants working on the Paper Trail codebase.

---

## Project Identity

**Paper Trail** — CSE 573 (Semantic Web Mining), Group 30, Arizona State University.

A hybrid PDF/OCR extraction pipeline that processes 22,000+ open-source bug reports (Mozilla Firefox, Ghostscript, Apache Tika, LibreOffice, OpenOffice, pdf.js), builds a Neo4j knowledge graph via LLM entity extraction, and exposes a hybrid RAG retriever (BM25 + ChromaDB vector + Neo4j graph) with multi-provider LLM synthesis.

---

## Architecture

```
PDF Corpus (22K docs)
    ↓
Hybrid Extraction
├── Native (pdfplumber) → fast path
└── OCR (GLM-OCR via mlx-vlm on macOS / vLLM on Sol)
    ↓
Knowledge Graph (Neo4j)
└── LLM entity/relation extraction + classical IE (spaCy)
    ↓
Hybrid RAG Retriever
├── BM25 (rank-bm25)
├── ChromaDB vector (all-MiniLM-L6-v2)
└── Neo4j graph traversal (2-hop expansion)
    ↓
LLM Synthesis → Gradio chatbot / CLI / FastAPI
```

---

## Critical Constraints

1. **Never modify `src/` unless explicitly asked.** Read-only for research. Scripts under `scripts/` and config under `config/` are the extension points.
2. **Never modify evaluation data** (`eval_results/`, `training_data.json`). Read and aggregate only.
3. **Never commit generated outputs** — `presentation/`, `data/processed/` large artifacts, `.env` secrets. All are gitignored.
4. **Always activate venv before running Python:** `source venv/bin/activate`
5. **Never run `git commit`, `git push`, or destructive git operations** without explicit user confirmation.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Extraction | `pdfplumber`, `pypdfium2`, `GLM-OCR` (mlx-vlm / vLLM) |
| OCR Server | `mlx_vlm.server` (macOS) or `vllm serve` (Sol GPU) |
| Graph DB | Neo4j 5.x Community (Docker / Apptainer) |
| Vector DB | ChromaDB (`chromadb-client`) |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` |
| LLM Client | ABC-based multi-provider (Ollama, Claude, OpenAI, Gemini) |
| Web UI | Gradio (`src/web/server.py`) |
| Evaluation | Custom CER/WER, Recall@K, MRR, Entity/Relation F1 |

---

## Key Data Layout

```
data/
├── batch2/          # GhostScript + Apache TIKA bug reports
├── batch3/MOZILLA/  # Mozilla Firefox bug reports
├── batch4/          # LibreOffice, OpenOffice, pdf.js
└── processed/
    └── <project>/
        ├── checkpoint.json
        ├── images/<pdf_name>/        # 200 DPI PNGs
        └── results/<pdf_name>_results.json

eval_results/
├── extract_ghost_E1.json
├── rag_retrieval_tiers_synthetic_v2.json
├── entity_relation_f1.json
├── kg_stats.txt
└── rag_stats.txt

training_data.json      # 86 ground-truth annotations (per-page CER/WER)
presentation/           # Generated figures (gitignored)
```

---

## Common Commands

**Single PDF extraction:**
```bash
python3 -m src.cli extract <pdf_path> --method hybrid --output result.json --preview
```

**Batch with checkpoint/resume:**
```bash
python3 -m src.cli extract-batch <dir> \
  --limit 10 --max-pages 20 --parallel 3 \
  --output-dir data/processed/mozilla \
  --checkpoint data/processed/mozilla/checkpoint.json \
  --project-name mozilla_batch
```

**Knowledge graph:**
```bash
python3 -m src.cli kg init
python3 scripts/build_knowledge_graph.py --all
python3 -m src.cli kg stats
```

**RAG:**
```bash
python3 -m src.cli rag index
python3 -m src.cli rag query "your question"
python3 -m src.cli rag chat      # Gradio UI
```

**Evaluation:**
```bash
python3 -m src.cli benchmark data/batch3/MOZILLA --ablation E3
python3 -m src.cli rag eval --tiers --output data/evaluation/rag_ablation.json
python3 -m src.cli eval entity-report
```

---

## Configuration

All YAML configs live in `config/`:
- `extraction.yaml` — `native_threshold: 0.8`, `pdf_dpi: 200`
- `llm.yaml` — provider toggles, model names, API key env vars
- `neo4j.yaml` — URI, credentials (`NEO4J_PASSWORD` env var)
- `rag.yaml` — chunk size, top-K, embedding model, system prompt

Copy from `.example` files:
```bash
cp config/llm.yaml.example config/llm.yaml
cp config/neo4j.yaml.example config/neo4j.yaml
```

---

## External Services

1. **GLM-OCR Server** (macOS): `mlx_vlm.server --trust-remote-code` on localhost:8080
2. **Neo4j**: `docker-compose up -d neo4j` (local) or Apptainer (Sol)
3. **Python env**: `venv/bin/activate` + `pip install -r requirements.txt`

---

## ASU Sol Supercomputer Notes

- Log in with X11 forwarding: `ssh -X your-asurite@sol.asu.edu`
- Use `module load mamba/latest && source activate paper_trail_env`
- No `mlx` packages on Sol; OCR runs via `vllm serve zai-org/GLM-OCR` on GPU
- Neo4j via Apptainer: `apptainer run docker://neo4j:5-community`
- Scratch path: `/scratch/$USER/` — ephemeral, clean up after jobs
- Submit via `sbatch` or interactive `salloc --partition=fpga --gres=gpu:a30:1`
- Full documentation: [https://docs.rc.asu.edu/](https://docs.rc.asu.edu/)

---

## Code Style

- Python 3.10+, type hints encouraged
- CLI entry point: `python3 -m src.cli <command>`
- Add new scripts to `scripts/`, not inline in `src/`
- Evaluation data is read-only; aggregation logic belongs in figure/report scripts

---

## Contact

Built by Group 30 for CSE 573 — Semantic Web Mining at Arizona State University.
