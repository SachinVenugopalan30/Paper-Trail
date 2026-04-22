# Paper Trail

A hybrid PDF/OCR extraction pipeline that processes open-source bug reports, builds a Neo4j knowledge graph of entities and relationships, and enables natural language querying via a RAG chatbot combining BM25, vector search, and graph traversal.

Built for CSE573 (Semantic Web Mining) — Group 30.

**Supported Platforms**: macOS (Apple Silicon), Linux, Windows (WSL2), Docker, Cloud

---

## Architecture

```
PDF Corpus (22,000+ docs)
        ↓
  Extraction Layer
  ├── Native (pdfplumber)   — fast path for digital PDFs
  └── OCR (GLM-OCR)         — fallback for scanned/image PDFs
        ↓
  Knowledge Graph (Neo4j)
  └── LLM entity extraction → 375,000+ entities, 275,000+ relationships
        ↓
  RAG Chatbot
  ├── BM25 keyword search
  ├── ChromaDB vector search (all-MiniLM-L6-v2)
  └── Neo4j graph traversal
        ↓
  Gradio Web UI
```

---

## Prerequisites

- Python 3.10+
- Docker (for Neo4j)
- [Ollama](https://ollama.com) (free, local LLM — recommended) **or** an API key for Claude/OpenAI/Gemini
- macOS Apple Silicon **or** Linux/Windows (see `SETUP_NON_MAC.md` for OCR alternatives)
- PDF corpus in `data/batch2/`, `data/batch3/MOZILLA/`, etc. — ask a team member for the dataset or download from the shared drive

---

## Setup

### 1. Clone and install dependencies

**macOS (local development + mlx-vlm OCR server):**
```bash
git clone <repo-url>
cd paper-trail

python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt -r requirements-macos.txt

brew install poppler

# Download spaCy model (required for classical IE baseline / E4-E6 ablation)
python -m spacy download en_core_web_sm
```

**ASU Sol supercomputer** — a ready-to-use conda environment is available:
```bash
module load mamba/latest
source activate paper_trail_env
# That's it — all dependencies are pre-installed (no mlx packages)
```

If you need to recreate the environment on Sol:
```bash
module load mamba/latest
conda create -n paper_trail_env python=3.10 -y
source activate paper_trail_env
pip install -r requirements.txt   # no mlx — those are macOS-only
sudo apt-get install poppler-utils || conda install -c conda-forge poppler
python -m spacy download en_core_web_sm
```

**Linux (other):**
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt   # no mlx packages needed

sudo apt-get install poppler-utils
python -m spacy download en_core_web_sm
```

### 2. Configure credentials

```bash
# Copy example configs
cp config/llm.yaml.example config/llm.yaml
cp config/neo4j.yaml.example config/neo4j.yaml
```

Edit `config/llm.yaml` to enable your preferred LLM provider:

- **Ollama (free, local, recommended)**:
  ```bash
  # Install Ollama from https://ollama.com, then pull the model:
  ollama pull gemma3
  ```
  No API key needed. The default config already points to Ollama.

- **Claude**: set `claude.enabled: true` and export your key:
  ```bash
  export ANTHROPIC_API_KEY=sk-ant-...
  ```
- **OpenAI**: set `openai.enabled: true` and export your key:
  ```bash
  export OPENAI_API_KEY=sk-...
  ```

Set the Neo4j password (default is `password`):
```bash
export NEO4J_PASSWORD=yourpassword
```

> **Tip**: Add these exports to your shell profile (`~/.zshrc`, `~/.bashrc`) or a local `.env` file (add `.env` to `.gitignore`) so you don't have to re-run them each session.

### 3. Start Neo4j

```bash
docker-compose up -d neo4j
# Neo4j browser: http://localhost:7474
# Bolt: bolt://localhost:7687
```

### 4. (Optional) Start GLM-OCR server — macOS only

Only needed if you want OCR extraction for scanned PDFs. Skip for native-only or RAG chatbot use.

```bash
conda create -n mlx-env python=3.12 -y && conda activate mlx-env
pip install git+https://github.com/Blaizzy/mlx-vlm.git
mlx_vlm.server --trust-remote-code   # starts on localhost:8080
```

For Linux/Windows alternatives, see `SETUP_NON_MAC.md`.

---

## End-to-End Pipeline

### Step 1 — Extract PDFs

```bash
# Single PDF (quick test)
python3 -m src.cli extract data/batch3/MOZILLA/MOZILLA-1000230-0.pdf --method hybrid --preview

# Batch — processes a full directory with checkpoint/resume support
python3 -m src.cli extract-batch data/batch3/MOZILLA \
  --limit 10 --max-pages 20 --parallel 3 \
  --output-dir data/processed/mozilla \
  --checkpoint data/processed/mozilla/checkpoint.json \
  --project-name mozilla_batch
```

Results are saved to `data/processed/<project>/results/*_results.json`. Each file contains per-page native and OCR text.

**Evaluate extraction quality (Gold Set A — CER/WER):**
```bash
# Run ablation benchmarks: E1=native-only, E2=OCR-only, E3=hybrid
python3 -m src.cli benchmark data/batch3/MOZILLA --ablation E3 --output results_e3.json

# Or annotate pages manually in the Streamlit UI to build ground truth
streamlit run src/evaluation/ground_truth_tool.py   # http://localhost:8501
```

### Step 2 — Build the Knowledge Graph

```bash
# Initialize Neo4j schema (run once per fresh database)
python3 -m src.cli kg init

# Extract entities from all processed results and import to Neo4j.
# This also saves per-document extraction JSONs to data/evaluation/extractions/
# (needed for Gold Set B annotation in Step 4).
python3 scripts/build_knowledge_graph.py --all

# Resume if interrupted
python3 scripts/build_knowledge_graph.py --all --resume

# Check graph stats
python3 -m src.cli kg stats
```

**Run classical IE baseline for E4-E6 ablation (spaCy NER, no LLM):**
```bash
# Classical-only extraction (fast, no LLM required)
python3 scripts/build_knowledge_graph.py --all --method classical

# Both LLM and classical (saves separate *_llm_extractions.json and *_classical_extractions.json)
python3 scripts/build_knowledge_graph.py --all --method both --max-pages 5
```

**Canonicalize duplicate entity nodes (run after import):**
```bash
# Dry-run — see what would be merged without writing
python3 scripts/canonicalize_entities.py --dry-run

# Merge duplicates with default 0.85 Levenshtein threshold
python3 scripts/canonicalize_entities.py --threshold 0.85

# Or via CLI
python3 -m src.cli kg canonicalize --threshold 0.85

# Restrict to one label for testing
python3 scripts/canonicalize_entities.py --label Organization --dry-run
```

**Evaluate graph quality (Graph Integrity):**
```bash
python3 -m src.cli kg integrity --output data/evaluation/integrity_report.json
```

### Step 3 — Build the RAG Index

```bash
# Chunks all result JSONs → populates ChromaDB + BM25 index
python3 -m src.cli rag index

# Check index stats
python3 -m src.cli rag stats
```

### Step 4 — Query

The graph retriever uses **2-hop traversal** by default: entities matched in the query are expanded up to 2 hops away in the Neo4j graph to find related documents. 2-hop results are scored at half the weight of 1-hop results (hop-penalty decay).

```bash
# One-shot CLI query
python3 -m src.cli rag query "What types of bugs are in the GhostScript corpus?"

# Launch the Gradio chatbot (http://localhost:7860)
python3 -m src.cli rag chat
```

**Evaluate retrieval quality (Recall@K & MRR):**

Before running, add `relevant_document_ids` to the query templates in `data/evaluation/rag_eval_queries.json`. Document IDs follow the pattern `{DOCNAME}_page_{N}` (e.g. `MOZILLA-1000230-0_page_1`). You can find valid IDs by checking the Neo4j browser or running:
```bash
python3 -m src.cli kg stats   # lists sample nodes with their doc_id values
```

Then run the evaluation:
```bash
# Full hybrid pipeline
python3 -m src.cli rag eval --output data/evaluation/rag_eval_report.json

# E7-E10 ablation: BM25-only, vector-only, hybrid, hybrid+graph
python3 -m src.cli rag eval --tiers --output data/evaluation/rag_ablation.json
```

### Step 5 — Annotate Entity/Relation Extractions (Gold Set B)

After Step 2, `data/evaluation/extractions/` contains one JSON per document. Launch the annotation UI:

```bash
streamlit run src/evaluation/entity_annotation_tool.py   # http://localhost:8501
# or
python3 -m src.cli eval entity-tool
```

For each page, judge each extracted entity and relation as **correct / partial / incorrect**, flag hallucinations, and add any entities/relations the LLM missed. Metrics are auto-computed on save.

Once annotated, print the aggregate report:
```bash
python3 -m src.cli eval entity-report --output data/evaluation/gold_set_b_report.json
```

---

## CLI Reference

```
python3 -m src.cli <command> [options]

Extraction:
  extract           Extract text from a single PDF
  extract-batch     Batch process a directory with checkpoint/resume

Benchmarking:
  benchmark         Run ablation studies (E1=native, E2=OCR, E3=hybrid)
  evaluate          Compare predictions against ground truth

Knowledge Graph:
  kg init           Initialize Neo4j schema
  kg extract        Extract entities from a PDF or directory
  kg import         Import a pre-extracted JSON into Neo4j
  kg stats          Show graph node/relation counts
  kg integrity      Run graph integrity checks (orphans, duplicates, provenance, …)
  kg canonicalize   Merge duplicate entity nodes via fuzzy name matching
                      --threshold 0.85   Levenshtein similarity threshold
                      --dry-run          Preview merges without writing
                      --label LABEL      Restrict to one entity label

RAG:
  rag index         Build/rebuild the ChromaDB + BM25 index
  rag stats         Show index statistics
  rag query <q>     One-shot query (no UI)
  rag chat          Launch Gradio chatbot UI
  rag eval          Evaluate retrieval quality (Recall@K, MRR, latency)
                      --queries FILE     path to eval queries JSON
                      --k-values 1,3,5,10
                      --tiers            run E7-E10 ablation
                      --output FILE      save report as JSON

Evaluation (Gold Set B):
  eval entity-tool    Launch entity/relation annotation Streamlit UI
  eval entity-report  Print aggregate Entity/Relation F1 from saved annotations
                        --output FILE    save report as JSON
```

---

## Project Structure

```
.
├── config/
│   ├── extraction.yaml         # PDF extraction settings
│   ├── llm.yaml                # LLM provider config (gitignored — copy from .example)
│   ├── llm.yaml.example
│   ├── neo4j.yaml              # Neo4j credentials (gitignored — copy from .example)
│   ├── neo4j.yaml.example
│   └── rag.yaml                # RAG chunking/retrieval/generation settings
├── data/                       # PDFs + processed results (gitignored)
│   ├── batch2/                 # GhostScript + Apache Tika
│   ├── batch3/                 # Mozilla Firefox
│   ├── batch4/                 # LibreOffice, OpenOffice, pdf.js
│   ├── processed/              # Extraction outputs + RAG indexes
│   ├── rag/                    # ChromaDB + BM25 index
│   └── evaluation/
│       ├── extractions/        # Per-doc extraction JSONs (generated by build_knowledge_graph.py)
│       ├── gold_set_b_annotations.json   # Entity/relation annotations (generated by annotation tool)
│       └── rag_eval_queries.json         # Curated retrieval evaluation queries
├── src/
│   ├── extraction/             # Native, OCR, hybrid routing, batch processor
│   │   └── classical_ie.py     # Classical IE baseline (spaCy NER + dependency rules)
│   ├── evaluation/
│   │   ├── metrics.py                  # CER/WER
│   │   ├── benchmark.py                # Ablation benchmark runner
│   │   ├── ground_truth_tool.py        # Gold Set A Streamlit annotation UI
│   │   ├── kg_integrity.py             # Graph integrity checks
│   │   ├── entity_metrics.py           # Entity/relation F1, hallucination rate
│   │   ├── entity_annotation_tool.py   # Gold Set B Streamlit annotation UI
│   │   └── rag_evaluator.py            # Recall@K, MRR, latency evaluation
│   ├── kg/                     # Neo4j client, schema, entity extractor, bulk importer
│   ├── llm/                    # Unified LLM client (Ollama, Claude, OpenAI, Gemini)
│   ├── rag/                    # Indexer, VectorStore, BM25, GraphRetriever, HybridRetriever, RAGChain
│   └── web/                    # Gradio chatbot UI
├── scripts/
│   ├── build_knowledge_graph.py
│   └── canonicalize_entities.py   # Post-import entity deduplication (fuzzy merge)
├── docker-compose.yml
├── requirements.txt            # all platforms (no mlx)
├── requirements-macos.txt      # macOS Apple Silicon only (mlx, mlx-vlm)
├── sol_pipeline.sh             # SLURM batch script for ASU Sol
└── training_data.json          # 86 ground truth annotations (gitignored)
```

---

## Configuration

| File | Purpose | Key settings |
|------|---------|-------------|
| `config/extraction.yaml` | PDF extraction | `native_threshold: 0.8`, `pdf_dpi: 200` |
| `config/llm.yaml` | LLM providers | provider enable/disable, models, API keys |
| `config/neo4j.yaml` | Graph database | URI, credentials |
| `config/rag.yaml` | RAG pipeline | chunk size, embedding model, top-K, system prompt |

---

## Troubleshooting

**Neo4j connection refused**
```bash
docker-compose up -d neo4j
# Wait ~10s for startup, then retry
```

**BM25 index not found when running `rag query`**
```bash
python3 -m src.cli rag index   # build the index first
```

**GLM-OCR server not responding**
```bash
curl http://localhost:8080/chat/completions -H "Content-Type: application/json" \
  -d '{"model": "mlx-community/GLM-OCR-bf16", "messages": [], "max_tokens": 10}'
# If down: conda activate mlx-env && mlx_vlm.server --trust-remote-code
```

**Out of memory during OCR**
- Reduce `--parallel` workers to 1
- Lower `pdf_dpi` to 150 in `config/extraction.yaml`

---

## Additional Documentation

- `mlx_vlm_README.md` — GLM-OCR server setup (macOS Apple Silicon)
- `SETUP_NON_MAC.md` — Linux, Windows, Docker, Cloud alternatives
- `IMPLEMENTATION_SUMMARY.md` — Technical implementation details

---

Built by Group 30 for CSE573 — Semantic Web Mining
