# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CSE573 Group 30 research project: a PDF/OCR extraction pipeline for Firefox bug reports, with a Neo4j knowledge graph and planned RAG chatbot. Processes PDFs using a hybrid native/OCR routing strategy, extracts entities with LLMs, and stores them in a graph database.

## Setup & External Services

Three external services are required:

1. **GLM-OCR Server** (macOS Apple Silicon):
   ```bash
   conda create -n mlx-env python=3.12 -y && conda activate mlx-env
   pip install git+https://github.com/Blaizzy/mlx-vlm.git
   mlx_vlm.server --trust-remote-code   # starts on localhost:8080
   ```
   For Linux/Windows: see `SETUP_NON_MAC.md`

2. **Neo4j** (via Docker):
   ```bash
   docker-compose up -d neo4j   # localhost:7474 browser, bolt://localhost:7687
   ```

3. **Python environment**:
   ```bash
   python3 -m venv venv && source venv/bin/activate
   pip install -r requirements.txt
   brew install poppler   # macOS; apt-get install poppler-utils on Linux
   ```

## Common Commands

All commands use `python3 -m src.cli` as the entry point.

**Single PDF extraction:**
```bash
python3 -m src.cli extract <pdf_path> --method hybrid --output result.json --preview
python3 -m src.cli extract <pdf_path> --method native
python3 -m src.cli extract <pdf_path> --method ocr
```

**Batch processing with checkpoint/resume:**
```bash
python3 -m src.cli extract-batch <dir> \
  --limit 10 --max-pages 20 --parallel 3 \
  --output-dir data/processed/mozilla \
  --checkpoint data/processed/mozilla/checkpoint.json \
  --project-name mozilla_batch
```

**Ablation benchmarks (E1=native-only, E2=OCR-only, E3=hybrid):**
```bash
python3 -m src.cli benchmark data/batch3/MOZILLA --ablation E3 --output results_e3.json
```

**Ground truth annotation UI:**
```bash
streamlit run src/evaluation/ground_truth_tool.py   # http://localhost:8501
```

**Knowledge graph:**
```bash
python3 -m src.cli kg init                          # initialize Neo4j schema
python3 -m src.cli kg extract input.pdf --provider claude --min-confidence 0.7
python3 -m src.cli kg import extraction.json --batch-size 1000
python3 -m src.cli kg stats
```

**KG builder script (with checkpoint/resume):**
```bash
python3 scripts/build_knowledge_graph.py --all
python3 scripts/build_knowledge_graph.py --all --resume
python3 scripts/build_knowledge_graph.py --test result.json
```

## Architecture

```
PDF Input → Extraction Layer → Evaluation Layer → Knowledge Graph → RAG (planned)
```

### Hybrid Extraction Routing (`src/extraction/router.py`)

Native extraction (pdfplumber) runs first. If text coverage ≥ 0.8 threshold → use native (fast: 10–50 pps). If coverage < threshold → fall back to GLM-OCR (slow: 1–2 pps but handles scanned/image PDFs). Batch processor runs both methods in parallel to support ground truth comparison.

### Batch Processing with Checkpoint/Resume (`src/extraction/batch_processor.py`, `src/extraction/checkpoint.py`)

ThreadPoolExecutor with N workers (default: 3). `CheckpointManager` tracks processed/failed/skipped/in-progress files with thread-safe atomic writes. Crash-safe: resume by re-running the same command with `--checkpoint`.

### Per-Page Result JSON Structure

Each PDF produces one JSON file in `data/processed/<project>/results/`. Structure: `{ source_pdf, total_pages, pages: [{ page_number, native: { text, coverage, word_count, success }, ocr: { text, success, image_path } }], summary }`. Ground truth annotations go to `training_data.json`.

### Multi-Provider LLM Client (`src/llm/client.py`)

Unified interface (ABC) with runtime provider switching. Supports: Ollama (default, local llama3.2:3b), Anthropic Claude, OpenAI, Google Gemini. Provider selected via `config/llm.yaml` or `--provider` CLI flag. Uses LangChain chains with Pydantic-structured output and confidence scoring.

### Knowledge Graph Schema (`src/kg/schema.py`)

10 entity types: `BugReport, Component, Technology, Severity, Status, Person, Organization, CodeReference, ErrorMessage, Feature`

15 relation types: `HAS_COMPONENT, HAS_SEVERITY, HAS_STATUS, MENTIONS, RELATED_TO, REPORTED_BY, ASSIGNED_TO, DEPENDS_ON, RESOLVED_BY, AFFECTS, IMPACTS, CAUSED_BY, DERIVED_FROM, PART_OF, IMPLEMENTS`

## Configuration

All config in `config/` (YAML):
- `extraction.yaml`: `native_threshold` (0.8), `pdf_dpi` (200), `parallel_workers`, OCR server host/port/timeouts
- `llm.yaml`: provider enable/disable, models, API key env vars (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`)
- `neo4j.yaml`: connection URI, credentials (`NEO4J_PASSWORD` env var, default: `password`)

## Data Layout

```
data/
├── batch2/          # GhostScript + Apache TIKA bug reports
├── batch3/MOZILLA/  # Mozilla Firefox bug reports
├── batch4/          # LibreOffice, OpenOffice, pdf.js
└── processed/
    └── <project>/
        ├── checkpoint.json
        ├── images/<pdf_name>/  # 200 DPI PNGs
        └── results/<pdf_name>_results.json
training_data.json   # 86 ground truth annotations
```

## Implementation Status

- **Complete**: Native extraction, OCR, hybrid routing, batch+checkpoint, CER/WER metrics, Streamlit annotation tool, Neo4j KG, LLM entity extraction, multi-provider client, bulk import, CLI
- **Planned (Phase 4)**: Hybrid RAG retriever (BM25 + Vector + Graph), conversational chatbot (Gradio)

## Notes

- No tests exist (`tests/` is empty); validation is done via scripts and the Streamlit annotation tool
- `src/rag/` and `src/web/` are placeholder directories for Phase 4
- 176 PDFs processed (83% success rate); 993 Neo4j nodes, 70 relations as of last run
