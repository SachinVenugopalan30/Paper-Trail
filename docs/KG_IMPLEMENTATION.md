# Knowledge Graph Implementation

## Overview

Complete LangChain-based knowledge graph pipeline for extracting entities and relations from bug reports and importing them into Neo4j.

## Features

### LLM Client (src/llm/)
- **Unified Interface**: Support for Ollama, Claude, OpenAI, and Gemini
- **Runtime Provider Switching**: Change providers on-the-fly
- **Token Tracking**: Monitor token usage per request
- **Streaming**: Support for streaming responses

### Entity Extraction (src/llm/chains.py)
- **10 Entity Types**: BugReport, Component, Technology, Severity, Status, Person, Organization, CodeReference, ErrorMessage, Feature
- **15 Relation Types**: HAS_COMPONENT, HAS_SEVERITY, HAS_STATUS, MENTIONS, RELATED_TO, REPORTED_BY, ASSIGNED_TO, AFFECTS, etc.
- **Confidence Scoring**: 0.0-1.0 confidence per extraction
- **Fallback Extraction**: Rule-based fallback when LLM confidence < 0.7

### Neo4j Integration (src/kg/)
- **Schema Management**: Automated constraint and index creation
- **Bulk Import**: Efficient batch importing with progress tracking
- **Retry Logic**: Exponential backoff for failed operations
- **Statistics**: Query graph statistics and sample data

## Quick Start

### 1. Initialize Neo4j Schema

```bash
python3 -m src.cli kg init
```

This creates constraints and indexes in Neo4j.

### 2. Extract Entities from Documents

Extract from a single PDF:
```bash
python3 -m src.cli kg extract data/batch3/MOZILLA/123456.pdf \
  --provider ollama \
  --max-pages 5 \
  --output stats.json
```

Extract from a directory:
```bash
python3 -m src.cli kg extract data/batch3/MOZILLA/ \
  --provider claude \
  --min-confidence 0.8 \
  --max-pages 3
```

### 3. Import Existing Extraction Results

```bash
python3 -m src.cli kg import data/processed/mozilla/results/ \
  --pattern "*_results.json" \
  --batch-size 500
```

### 4. Check Graph Statistics

```bash
python3 -m src.cli kg stats
```

## Configuration

Edit `config/llm.yaml` to configure providers:

```yaml
providers:
  ollama:
    enabled: true
    base_url: http://localhost:11434
    model: llama3.2:3b
    max_tokens: 4096
    temperature: 0.1
  
  claude:
    enabled: false  # Set to true and add API key
    api_key: ${ANTHROPIC_API_KEY}
    model: claude-3-sonnet-20240229
    
default_provider: ollama
```

## Programmatic Usage

```python
from src.llm import get_client, EntityExtractionChain
from src.kg import get_client as get_kg_client, BulkImporter

# Initialize clients
llm_client = get_client()
llm_client.switch_provider("claude")  # Runtime switching

kg_client = get_kg_client()
kg_client.connect()
kg_client.init_schema()

# Extract entities
chain = EntityExtractionChain(llm_client)
result = chain.extract(text="Bug 123456 about Firefox crash...", document_id="bug123")

print(f"Found {len(result.entities)} entities")
print(f"Token usage: {result.processing_metadata['token_usage']}")

# Import to Neo4j
importer = BulkImporter(kg_client)
importer.import_extraction_result(result)

# Check stats
stats = kg_client.get_stats()
print(f"Total nodes: {sum(stats['node_counts_by_label'].values())}")
```

## Entity Types

1. **BugReport**: Software bug/issue with id, title, description, status, severity
2. **Component**: Software components/modules
3. **Technology**: Languages, frameworks, libraries
4. **Severity**: Bug severity levels (blocker, critical, major, normal, minor, trivial)
5. **Status**: Workflow status (NEW, ASSIGNED, RESOLVED, VERIFIED, CLOSED)
6. **Person**: Reporters, assignees, commenters
7. **Organization**: Companies/teams
8. **CodeReference**: File/function references
9. **ErrorMessage**: Error messages and stack traces
10. **Feature**: Product features

## Relation Types

- **HAS_COMPONENT**: Bug affects component
- **HAS_SEVERITY**: Bug severity level
- **HAS_STATUS**: Bug workflow status
- **MENTIONS**: Bug mentions entity
- **RELATED_TO**: Bug related to another bug
- **REPORTED_BY**: Bug reporter
- **ASSIGNED_TO**: Bug assignee
- **AFFECTS**: Bug affects technology
- **BLOCKS**: Bug blocks another
- **DUPLICATE_OF**: Bug is duplicate
- **DEPENDS_ON**: Bug depends on another
- Plus 4 more...

## Architecture

```
PDF/Text Input
    ↓
Extraction Chain (LLM with Pydantic)
    ↓
ExtractionResult (Entities + Relations)
    ↓
BulkImporter (Batch + Retry)
    ↓
Neo4jClient (MERGE operations)
    ↓
Neo4j Knowledge Graph
```

## Next Steps

Phase 4 (RAG Pipeline):
1. Build hybrid retriever (BM25 + Vector + Graph)
2. Conversational chain with streaming
3. Chatbot UI with provider switching controls
