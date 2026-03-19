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

---

## Setup

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd paper-trail

python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# macOS
brew install poppler

# Linux
sudo apt-get install poppler-utils
```

### 2. Configure credentials

```bash
# Copy example configs
cp config/llm.yaml.example config/llm.yaml
cp config/neo4j.yaml.example config/neo4j.yaml
```

Edit `config/llm.yaml` to enable your preferred LLM provider:

- **Ollama (free, local, recommended)**: install Ollama and run `ollama pull gemma3` — no API key needed
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
# Single PDF
python3 -m src.cli extract data/batch3/MOZILLA/bug_report.pdf --method hybrid --preview

# Batch (with checkpoint/resume)
python3 -m src.cli extract-batch data/batch3/MOZILLA \
  --limit 10 --max-pages 20 --parallel 3 \
  --output-dir data/processed/mozilla \
  --checkpoint data/processed/mozilla/checkpoint.json
```

Results are saved to `data/processed/<project>/results/*_results.json`.

### Step 2 — Build the Knowledge Graph

```bash
# Initialize Neo4j schema (run once)
python3 -m src.cli kg init

# Extract entities from processed results and import to Neo4j
python3 scripts/build_knowledge_graph.py --all

# Resume if interrupted
python3 scripts/build_knowledge_graph.py --all --resume

# Check graph stats
python3 -m src.cli kg stats
```

### Step 3 — Build the RAG Index

```bash
# Chunks all result JSONs → populates ChromaDB + BM25 index
python3 -m src.cli rag index

# Check index stats
python3 -m src.cli rag stats
```

### Step 4 — Query

```bash
# One-shot CLI query
python3 -m src.cli rag query "What types of bugs are in the GhostScript corpus?"

# Launch the Gradio chatbot (http://localhost:7860)
python3 -m src.cli rag chat
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

RAG:
  rag index         Build/rebuild the ChromaDB + BM25 index
  rag stats         Show index statistics
  rag query <q>     One-shot query (no UI)
  rag chat          Launch Gradio chatbot UI
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
│   └── rag/                    # ChromaDB + BM25 index
├── src/
│   ├── extraction/             # Native, OCR, hybrid routing, batch processor
│   ├── evaluation/             # CER/WER metrics, benchmark, Streamlit annotation tool
│   ├── kg/                     # Neo4j client, schema, entity extractor, bulk importer
│   ├── llm/                    # Unified LLM client (Ollama, Claude, OpenAI, Gemini)
│   ├── rag/                    # Indexer, VectorStore, BM25, GraphRetriever, HybridRetriever, RAGChain
│   └── web/                    # Gradio chatbot UI
├── scripts/
│   └── build_knowledge_graph.py
├── docker-compose.yml
├── requirements.txt
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

## Benchmarking

```bash
# E1: native-only, E2: OCR-only, E3: hybrid
python3 -m src.cli benchmark data/batch3/MOZILLA --ablation E3 --output results_e3.json

# Ground truth annotation UI
streamlit run src/evaluation/ground_truth_tool.py   # http://localhost:8501
```

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
