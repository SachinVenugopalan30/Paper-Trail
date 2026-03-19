# PDF/OCR Extraction and Knowledge Graph Pipeline

## Project Overview

A comprehensive system for extracting text from bug report PDFs, evaluating extraction quality, building a Neo4j knowledge graph with LLM-powered entity extraction, and supporting RAG-based chatbot queries.

## Project Goals

The system implements a complete pipeline across four phases:

### Phase 1: Extraction Pipeline ✓
- Native PDF text extraction using pdfplumber
- OCR extraction using GLM-OCR (Visual Language Model)
- Hybrid routing based on text coverage analysis
- Batch processing with checkpoint/resume

### Phase 2: Benchmarking & Evaluation ✓
- Character Error Rate (CER) and Word Error Rate (WER) metrics
- Ablation framework for method comparison (E1/E2/E3)
- Ground truth annotation tool with Streamlit UI
- Training data generation for quality assessment

### Phase 3: Knowledge Graph ✓
- Neo4j graph database for structured knowledge
- 10 entity types: BugReport, Component, Technology, Severity, Status, Person, Organization, CodeReference, ErrorMessage, Feature
- 15 relation types: HAS_COMPONENT, RELATED_TO, MENTIONS, etc.
- LLM-powered entity extraction with confidence scoring
- Bulk import pipeline with parallel processing

### Phase 4: RAG Chatbot (Planned)
- Hybrid retrieval: BM25 (25%) + Vector embeddings (50%) + Graph traversal (25%)
- Conversational chain with streaming responses
- Provider switching (Ollama/Claude/OpenAI/Gemini) with token tracking
- Web interface for interactive querying

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         INPUT LAYER                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐               │
│  │  Batch 2    │  │  Batch 3    │  │  Batch 4    │               │
│  │  GHOSTSCRIPT│  │  MOZILLA    │  │  LIBRE_OFFICE│              │
│  │  TIKA       │  │             │  │  OOO         │              │
│  │  (5596 PDFs)│  │  (6835 PDFs)│  │  pdf.js      │              │
│  └─────────────┘  └─────────────┘  └─────────────┘               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                     EXTRACTION LAYER                             │
│  ┌─────────────────┐    ┌─────────────────┐                     │
│  │  Native (E1)    │    │  OCR (E2)        │                     │
│  │  pdfplumber     │    │  GLM-OCR         │                     │
│  │  Per-page text  │    │  Per-page images │                     │
│  │  + tables       │    │  + VLM inference │                     │
│  └─────────────────┘    └─────────────────┘                     │
│           ↓                        ↓                              │
│  ┌─────────────────────────────────────────┐                    │
│  │     Hybrid Router (E3)                   │                    │
│  │     Coverage threshold: 0.8             │                    │
│  │     Route: Native, OCR, or Both         │                    │
│  └─────────────────────────────────────────┘                    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                   EVALUATION LAYER                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ CER Metrics  │  │ WER Metrics  │  │ Annotation   │          │
│  │ Similarity   │  │ Benchmarks   │  │ Tool (UI)    │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                KNOWLEDGE GRAPH LAYER                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ LLM Entity   │  │ Neo4j Schema │  │ Bulk Import  │          │
│  │ Extraction   │  │ 10 Entities  │  │ Parallel     │          │
│  │ Per-page     │  │ 15 Relations │  │ 3 Workers    │          │
│  │ Confidence   │  │ Constraints  │  │ Checkpoint   │          │
│  │ 0.6          │  │ Indexes      │  │ Resume       │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                     RAG LAYER (Planned)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ BM25         │  │ Vector Store │  │ Graph        │          │
│  │ Keyword      │  │ Embeddings   │  │ Traversal    │          │
│  │ Search       │  │ Similarity   │  │ Relations    │          │
│  │ (25%)        │  │ (50%)        │  │ (25%)        │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                              ↓                                  │
│  ┌─────────────────────────────────────────────┐               │
│  │   Conversational Chain with Streaming       │               │
│  │   Provider: Ollama/Claude/OpenAI/Gemini    │               │
│  │   Token Tracking + Source Attribution       │               │
│  └─────────────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────────────┘
```

## Technology Stack

### Core PDF Processing
- **pdfplumber**: Native text extraction with layout preservation
- **pdf2image**: PDF to PNG conversion
- **Poppler**: PDF rendering backend

### OCR & Vision
- **GLM-OCR**: Visual Language Model for OCR (mlx-community/GLM-OCR-bf16)
- **MLX**: Apple Silicon optimized inference
- **GLM-4.6**: Cloud-based alternative

### LLM Providers (Multi-Provider Support)
- **Ollama** (default): llama3.2:3b, local inference
- **Claude**: claude-3-sonnet-20240229 (cloud API)
- **OpenAI**: gpt-4-turbo-preview (cloud API)
- **Gemini**: gemini-pro (cloud API)

### LangChain Integration
- **langchain**: Orchestration framework
- **langchain-ollama**: Ollama provider
- **langchain-anthropic**: Claude provider
- **langchain-openai**: OpenAI provider
- **langchain-google-genai**: Gemini provider

### Knowledge Graph
- **Neo4j 5 Community**: Graph database
- **APOC**: Graph algorithms plugin
- **neo4j-python-driver**: Python client

### Web & UI
- **Streamlit**: Annotation tool interface
- **Gradio** (planned): Chatbot interface

### Metrics & Evaluation
- **rapidfuzz**: Fast string matching for CER/WER
- **difflib**: Sequence matching

## Current Status

### Completed ✅

**Extraction Pipeline:**
- 176 PDFs processed across 3 batches
- Per-page native + OCR extraction
- 86 annotations created for ground truth
- Training data exported (62 OCR preferred, 24 Native preferred)

**Knowledge Graph:**
- Neo4j running in Docker
- 993 nodes, 70 relations
- 145 PDFs successfully imported
- Entity types: BugReport (128), Component (310), Organization (157), Person (144), Technology (130)

**Codebase:**
- 15 Python modules totaling ~4,500 lines
- CLI with 12 commands
- 2 utility scripts
- Comprehensive test coverage

### In Progress 🔄
- Documentation (this project)

### Planned 📋
- Hybrid RAG retriever
- Conversational chatbot with streaming
- Provider switching UI
- Token usage tracking

## Project Structure

```
├── config/              # Configuration files
├── data/               # Raw and processed data
│   ├── batch2/         # GHOSTSCRIPT, TIKA
│   ├── batch3/         # MOZILLA
│   ├── batch4/         # LIBRE_OFFICE, OOO, pdf.js
│   └── processed/      # Extraction results
├── docs/               # Documentation (this folder)
├── scripts/            # Utility scripts
├── src/                # Source code
│   ├── cli.py          # CLI entry point
│   ├── extraction/     # PDF extraction modules
│   ├── evaluation/     # Benchmarking & metrics
│   ├── kg/             # Knowledge graph
│   ├── llm/            # Multi-provider LLM client
│   ├── rag/            # Retrieval pipeline (placeholder)
│   └── web/            # Chatbot interface (placeholder)
├── docker-compose.yml  # Neo4j Docker setup
├── requirements.txt    # Dependencies
└── README.md          # Main readme
```

## Key Metrics

| Metric | Value |
|--------|-------|
| PDFs Processed | 176 |
| Annotations Created | 86 |
| Training Data | 86 samples |
| Neo4j Nodes | 993 |
| Neo4j Relations | 70 |
| Entity Types | 10 |
| Relation Types | 15 |
| Processing Time | ~5 hours (100 PDFs) |
| Success Rate | 83% (145/176) |

## Next Steps

1. **Complete Documentation**: Create all 15 markdown files in docs/
2. **RAG Implementation**: Build hybrid retriever and chatbot
3. **Evaluation**: Test chatbot quality with sample queries
4. **Deployment**: Production-ready setup guide

## License

This project is developed as part of CSE 573 - Software Engineering coursework.

## Contact

For questions or issues, refer to the troubleshooting guide or open an issue in the project repository.

---

**Last Updated:** March 18, 2026
**Status:** Phase 3 Complete, Phase 4 In Planning
**Version:** 1.0
