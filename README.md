# Paper Trail

A hybrid PDF/OCR extraction pipeline that processes open-source bug reports, builds a Neo4j knowledge graph of entities and relationships, and enables natural language querying via a RAG chatbot combining BM25, vector search, and graph traversal.

Built for **CSE 573 — Semantic Web Mining** — Group 30.

**Supported Platforms**: macOS (Apple Silicon), Linux, Windows (WSL2), Docker, ASU Sol Supercomputer

---

## Overview

This project implements a complete pipeline for extracting structured knowledge from large-scale technical PDF corpora:

1. **Hybrid PDF Extraction** — Native `pdfplumber` for digital PDFs, GLM-OCR fallback for scanned/image-heavy pages
2. **Knowledge Graph Construction** — LLM-powered entity/relation extraction into Neo4j (157K+ nodes, 160K+ relations)
3. **Hybrid RAG Retrieval** — BM25 + ChromaDB vector search + Neo4j graph traversal
4. **Conversational Interface** — Multi-provider LLM synthesis (Ollama, Claude, OpenAI, Gemini)

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
  └── LLM entity extraction → 157,257 nodes, 160,563 relations
        ↓
  Hybrid RAG Retriever
  ├── BM25 keyword search
  ├── ChromaDB vector search (all-MiniLM-L6-v2)
  └── Neo4j graph traversal
        ↓
  LLM Synthesis → Web UI / CLI
```

---

## Quick Start

### macOS (Local Development + Apple Silicon)

```bash
# 1. Clone and enter repository
cd paper-trail

# 2. Create virtual environment
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt -r requirements-macos.txt

# 3. Install system dependency
brew install poppler

# 4. Download spaCy model (for classical IE baseline)
python -m spacy download en_core_web_sm

# 5. Configure credentials
cp config/llm.yaml.example config/llm.yaml
cp config/neo4j.yaml.example config/neo4j.yaml

# 6. Start Neo4j
docker-compose up -d neo4j

# 7. Start GLM-OCR server (optional — for scanned PDFs)
conda create -n mlx-env python=3.12 -y && conda activate mlx-env
pip install git+https://github.com/Blaizzy/mlx-vlm.git
mlx_vlm.server --trust-remote-code   # localhost:8080
```

### ASU Sol Supercomputer

Sol is the primary compute environment for large-scale batch processing of the full 22K-document corpus.

> **Reference:** [ASU Research Computing Documentation](https://docs.rc.asu.edu/) — general Sol usage, SLURM, storage, and GPU allocation.

#### 1. Pre-configured Environment

```bash
# Log in to Sol
ssh -X your-asurite@sol.asu.edu

# Load the pre-built conda environment
module load mamba/latest
source activate paper_trail_env

# Verify
python3 -V   # Python 3.10+
python3 -c "import src; print('OK')"
```

> **Note:** The Sol environment has all dependencies pre-installed **except** macOS-only packages (`mlx`, `mlx-vlm`). OCR on Sol runs via vLLM + GLM-OCR on GPU, not mlx-vlm.

#### 2. Start Services on Sol

```bash
# Start Neo4j via Apptainer (once per session)
apptainer run --rm -p 7474:7474 -p 7687:7687 \
    -e NEO4J_AUTH=neo4j/password \
    docker://neo4j:5-community

# Start GLM-OCR via vLLM (GPU node)
vllm serve zai-org/GLM-OCR --host 127.0.0.1 --port 8080 \
    --served-model-name glm-ocr --trust-remote-code
```

#### 3. Run Pipeline Steps Manually

```bash
# 1) Batch extraction with checkpoint/resume
python3 -m src.cli extract-batch data/batch3/MOZILLA \
    --method ocr --parallel 8 \
    --output-dir data/processed/mozilla \
    --checkpoint data/processed/mozilla/checkpoint.json

# 2) Build knowledge graph
python3 -m src.cli kg init
python3 scripts/build_knowledge_graph.py --all --resume

# 3) Build RAG index
python3 -m src.cli rag index

# 4) Export results
rsync -avz data/processed/ your-laptop:~/paper-trail/data/processed/
```

#### 4. Resource Guidelines for SLURM Jobs

| Resource | Suggested | Purpose |
|----------|-----------|---------|
| Partition | `fpga` or `general` | GPU needed only for OCR |
| CPUs | 8–16 | Parallel extraction workers |
| Memory | 64–160 GB | Scales with corpus size |
| GPU | 1 × A30 / A100 | For GLM-OCR vLLM inference |
| Time | 4–12 hours | Full corpus (~22K PDFs) |

Submit an interactive job for debugging:
```bash
salloc --partition=fpga --gres=gpu:a30:1 --cpus-per-task=8 --mem=64G --time=02:00:00
```

#### 5. Transfer Results Back

```bash
# From your laptop
rsync -avz your-asurite@sol.asu.edu:/scratch/your-asurite/paper-trail/data/processed/ ./data/processed/

# Restore Neo4j dump locally
docker-compose down
neo4j-admin database load neo4j --from-path=./export --overwrite-destination=true
docker-compose up -d neo4j
```

### Linux / Windows (WSL2)

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

sudo apt-get install poppler-utils
python -m spacy download en_core_web_sm
```

For Linux OCR alternatives to GLM-OCR, see `SETUP_NON_MAC.md`.

---

## Configuration

| File | Purpose | Key Settings |
|------|---------|-------------|
| `config/extraction.yaml` | PDF extraction | `native_threshold: 0.8`, `pdf_dpi: 200` |
| `config/llm.yaml` | LLM providers | Enable/disable providers, set models |
| `config/neo4j.yaml` | Graph database | URI, credentials |
| `config/rag.yaml` | RAG pipeline | Chunk size, embedding model, top-K |

Set API keys via environment:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export OPENAI_API_KEY=sk-...
export NEO4J_PASSWORD=yourpassword
```

---

## Running the Pipeline

### Step 1 — Extract PDFs

```bash
# Single PDF test
python3 -m src.cli extract data/batch3/MOZILLA/MOZILLA-1000230-0.pdf --method hybrid --preview

# Batch extraction with checkpoint/resume
python3 -m src.cli extract-batch data/batch3/MOZILLA \
  --limit 10 --max-pages 20 --parallel 3 \
  --output-dir data/processed/mozilla \
  --checkpoint data/processed/mozilla/checkpoint.json

# Ablation benchmarks (E1=native, E2=OCR, E3=hybrid)
python3 -m src.cli benchmark data/batch3/MOZILLA --ablation E3 --output results_e3.json
```

### Step 2 — Build Knowledge Graph

```bash
# Initialize schema (run once per fresh Neo4j instance)
python3 -m src.cli kg init

# Extract and import entities/relations
python3 scripts/build_knowledge_graph.py --all

# Resume if interrupted
python3 scripts/build_knowledge_graph.py --all --resume

# Check graph stats
python3 -m src.cli kg stats
```

### Step 3 — Build RAG Index

```bash
python3 -m src.cli rag index    # Build ChromaDB + BM25
python3 -m src.cli rag stats    # Verify index
```

### Step 4 — Launch the Web UI

The Paper Trail chat interface is a Gradio app that combines the hybrid retriever with multi-provider LLM synthesis.

```bash
# 1. Activate the Python environment
cd "/Users/sachin/Desktop/Uni Courses/CSE 573 - SWM/2Project"
source venv/bin/activate

# 2. Ensure Neo4j is running
docker-compose up -d neo4j

# 3. Start the Gradio chatbot
python3 -m src.cli rag chat
```

Open your browser at **http://127.0.0.1:7860**.

> **Note:** GLM-OCR is only needed when extracting new PDFs; it is **not** required to run the chat UI.

### One-shot CLI Query

```bash
python3 -m src.cli rag query "memory leak in firefox"
```

---

## Evaluations

Core benchmark results are summarized in [`EVALUATIONS.md`](EVALUATIONS.md). Raw evaluation data lives in [`eval_results/`](eval_results/).

| What | Source File |
|------|-------------|
| Extraction CER/WER | `training_data.json` (86 annotated pages) |
| RAG Recall@K / MRR / Latency | `eval_results/rag_retrieval_tiers_synthetic_v2.json` |

Run evaluations locally:
```bash
# E1-E3 extraction ablation
python3 -m src.cli benchmark data/batch3/MOZILLA --ablation E3

# RAG tier ablation (E7-E10)
python3 -m src.cli rag eval --tiers --output eval_results/rag_ablation.json
```

---

## CLI Reference

```
python3 -m src.cli <command> [options]

Extraction:
  extract           Single PDF extraction
  extract-batch     Batch processing with checkpoint/resume

Benchmarking:
  benchmark         Run E1-E3 ablation studies
  evaluate          Compare against ground truth

Knowledge Graph:
  kg init           Initialize Neo4j schema
  kg extract        Extract entities from PDFs
  kg import         Import JSON into Neo4j
  kg stats          Show node/relation counts
  kg integrity      Graph quality checks
  kg canonicalize   Merge duplicate entities (fuzzy matching)

RAG:
  rag index         Build ChromaDB + BM25 index
  rag stats         Show index statistics
  rag query <q>     One-shot query
  rag chat          Launch Gradio chatbot
  rag eval          Evaluate retrieval (Recall@K, MRR, latency)

Evaluation:
  eval entity-tool    Launch annotation UI (Streamlit)
  eval entity-report  Aggregate F1 / hallucination metrics
```

---

## Project Structure

```
.
├── config/                     # YAML configurations
├── data/
│   ├── batch2/                 # GhostScript + Apache Tika
│   ├── batch3/MOZILLA/         # Mozilla Firefox
│   ├── batch4/                 # LibreOffice, OpenOffice, pdf.js
│   ├── processed/              # Extraction outputs
│   ├── rag/                    # ChromaDB + BM25 index
│   └── evaluation/             # Evaluation queries + results
├── src/
│   ├── extraction/             # Native, OCR, hybrid routing
│   ├── evaluation/             # Metrics, benchmarks, annotation UIs
│   ├── kg/                     # Neo4j client, schema, importer
│   ├── llm/                    # Multi-provider LLM client
│   ├── rag/                    # Indexer, retrievers, RAG chain
│   └── web/                    # Gradio chatbot UI
├── scripts/
│   ├── build_knowledge_graph.py
│   └── canonicalize_entities.py
├── docker-compose.yml          # Neo4j container
├── requirements.txt            # Core dependencies
├── requirements-macos.txt      # Apple Silicon (mlx, mlx-vlm)
└── training_data.json          # 86 ground-truth annotations
```

---

## Troubleshooting

**Neo4j connection refused**
```bash
docker-compose up -d neo4j
# Wait ~10s for startup
```

**BM25 index not found**
```bash
python3 -m src.cli rag index
```

**GLM-OCR server not responding**
```bash
curl http://localhost:8080/chat/completions -H "Content-Type: application/json" \
  -d '{"model": "mlx-community/GLM-OCR-bf16", "messages": [], "max_tokens": 10}'
```

**Out of memory during OCR**
- Reduce `--parallel` to 1
- Lower `pdf_dpi` to 150 in `config/extraction.yaml`

---

## Documentation

| File | Contains |
|------|----------|
| `AGENTS.md` | AI assistant guide: constraints, commands, data layout |
| `CLAUDE.md` | Architecture overview, data layout, implementation status |
| `SETUP_NON_MAC.md` | Linux / Windows / Docker / Cloud OCR alternatives |
| `mlx_vlm_README.md` | GLM-OCR server setup (macOS Apple Silicon) |
| `docs/SETUP_AND_INSTALLATION.md` | Detailed platform-specific setup |
| `docs/CLI_REFERENCE.md` | Complete CLI command reference |
| `docs/KNOWLEDGE_GRAPH.md` | KG schema, extraction, canonicalization |
| `docs/EXTRACTION_PIPELINE.md` | Extraction architecture deep-dive |
| `docs/TROUBLESHOOTING.md` | Common errors and resolutions |

---

Built by **Group 30** for **CSE 573 — Semantic Web Mining** at Arizona State University.
