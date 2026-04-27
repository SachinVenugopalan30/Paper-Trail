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

#### 1. Pre-configured Environment

```bash
# Log in to Sol
ssh your-asurite@solsrv.eas.asu.edu

# Load the pre-built conda environment
module load mamba/latest
source activate paper_trail_env

# Verify
python3 -V   # Python 3.10+
python3 -c "import src; print('OK')"
```

> **Note:** The Sol environment has all dependencies pre-installed **except** macOS-only packages (`mlx`, `mlx-vlm`). OCR on Sol runs via vLLM + GLM-OCR on GPU, not mlx-vlm.

#### 2. Update `sol_pipeline.sh`

Edit these variables in `sol_pipeline.sh` before running:

```bash
WORKDIR="/scratch/your-asurite/paper-trail"   # your scratch directory
NEO4J_PASSWORD="your-secure-password"
CONDA_ENV="paper_trail_env"
```

#### 3. Submit the SLURM Job

```bash
# Copy data to Sol scratch (one-time)
scp -r data/ your-asurite@solsrv.eas.asu.edu:/scratch/your-asurite/paper-trail/

# Submit the full pipeline job
sbatch sol_pipeline.sh

# Monitor job status
squeue -u your-asurite

# Watch live logs
tail -f paper_trail_full_*.out
```

The pipeline (`sol_pipeline.sh`) runs all stages automatically:
1. **PDF Extraction** — Batch processes all corpora with checkpoint/resume
2. **Knowledge Graph** — Extracts entities/relations and imports to Neo4j
3. **RAG Indexing** — Builds ChromaDB + BM25 indexes
4. **Export** — Packages results for transfer back to your laptop

#### 4. Resource Configuration

Default resources in `sol_pipeline.sh`:

| Resource | Value | Notes |
|----------|-------|-------|
| Partition | `fpga` | GPU-enabled nodes |
| CPUs | 16 | Parallel extraction workers |
| Memory | 160 GB | Neo4j + vLLM + batch processing |
| GPU | 1 × A30 | For GLM-OCR vLLM inference |
| Time | 12 hours | Full corpus (~22K PDFs) |

Adjust `--time`, `--mem`, and `--gres` for smaller runs:

```bash
# Quick test on 100 PDFs
EXTRACT_METHOD=native PDF_LIMIT=100 sbatch --time=01:00:00 sol_pipeline.sh
```

#### 5. Transfer Results Back

```bash
# From your laptop
rsync -avz your-asurite@solsrv.eas.asu.edu:/scratch/your-asurite/paper-trail/export/ ./export/

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

### Step 4 — Query

```bash
# One-shot CLI query
python3 -m src.cli rag query "What types of bugs are in the GhostScript corpus?"

# Launch Gradio chatbot
python3 -m src.cli rag chat     # http://localhost:7860
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
├── sol_pipeline.sh             # SLURM batch script for ASU Sol
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
