# CLI Reference Guide

Complete reference for the PDF/OCR Extraction and Knowledge Graph Pipeline command-line interface.

---

## Table of Contents

1. [CLI Overview](#cli-overview)
2. [Extraction Commands](#extraction-commands)
3. [Evaluation Commands](#evaluation-commands)
4. [Knowledge Graph Commands](#knowledge-graph-commands)
5. [Usage Examples](#usage-examples)
6. [Common Options](#common-options)
7. [Exit Codes](#exit-codes)
8. [Tips and Best Practices](#tips-and-best-practices)

---

## CLI Overview

### Entry Point

The CLI is accessed through `src/cli.py` using Python's module execution:

```bash
python3 -m src.cli [command] [options]
```

### Main Command Structure

```
src.cli
├── extract          # Single PDF extraction
├── extract-batch    # Batch PDF processing
├── benchmark        # Ablation studies
├── evaluate         # Calculate metrics
└── kg               # Knowledge Graph operations
    ├── init         # Initialize Neo4j schema
    ├── extract      # Extract entities from documents
    ├── import       # Import to Neo4j
    └── stats        # Show statistics
```

### Help System

Get help for any command:

```bash
# General help
python3 -m src.cli --help

# Command-specific help
python3 -m src.cli extract --help
python3 -m src.cli extract-batch --help
python3 -m src.cli benchmark --help
python3 -m src.cli kg --help
python3 -m src.cli kg extract --help
```

---

## Extraction Commands

### extract - Single PDF Extraction

Extract text from a single PDF using native, OCR, or hybrid methods.

**Syntax:**
```bash
python3 -m src.cli extract <pdf_path> [options]
```

**Options:**

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--method` | - | Extraction method: `native`, `ocr`, `hybrid` | `hybrid` |
| `--output` | `-o` | Output JSON file path | - |
| `--threshold` | - | Coverage threshold for hybrid routing (0.0-1.0) | `0.8` |
| `--max-tokens` | - | Max tokens for OCR processing | `4096` |
| `--preview` | - | Show text preview in console | `False` |

**Examples:**

```bash
# Extract using hybrid method (default)
python3 -m src.cli extract document.pdf

# Use native extraction only
python3 -m src.cli extract document.pdf --method native

# Use OCR extraction with output file
python3 -m src.cli extract scanned.pdf --method ocr --output result.json

# Hybrid with custom threshold and preview
python3 -m src.cli extract document.pdf --threshold 0.75 --preview
```

**Output JSON Structure:**
```json
{
  "text": "Extracted text content...",
  "coverage": 0.92,
  "method": "native",
  "images": ["/path/to/page1.png", "/path/to/page2.png"]
}
```

---

### extract-batch - Batch Processing

Process multiple PDFs with both native and OCR extraction, saving detailed results.

**Syntax:**
```bash
python3 -m src.cli extract-batch <directory> [options]
```

**Options:**

| Option | Description | Default |
|--------|-------------|---------|
| `--limit` | Max number of PDFs to process | - |
| `--limit-pages` | Limit each PDF to first N pages | - |
| `--max-pages` | Skip PDFs with more than N pages | `20` |
| `--parallel` | Number of parallel workers | `3` |
| `--save-images` | Save converted PNG images | `True` |
| `--output-dir` | Output directory for results | `data/processed/mozilla` |
| `--checkpoint` | Checkpoint file path | `data/processed/mozilla/checkpoint.json` |
| `--project-name` | Project identifier for checkpointing | `mozilla_batch` |
| `--ocr-dpi` | DPI for OCR image conversion | `200` |
| `--ocr-timeout` | OCR request timeout in seconds | `300` |

**Examples:**

```bash
# Basic batch processing
python3 -m src.cli extract-batch data/pdfs/

# Process with limits for testing
python3 -m src.cli extract-batch data/pdfs/ --limit 10 --max-pages 5

# Full production run with parallel processing
python3 -m src.cli extract-batch data/batch3/MOZILLA \
  --limit 100 \
  --max-pages 20 \
  --parallel 4 \
  --save-images \
  --output-dir data/processed/mozilla \
  --project-name mozilla_production

# Resume from checkpoint
python3 -m src.cli extract-batch data/pdfs/ \
  --checkpoint data/processed/mozilla/checkpoint.json
```

**Output Structure:**
```
data/processed/mozilla/
├── results/
│   ├── document1.json      # Extraction results per PDF
│   └── document2.json
└── images/
    ├── document1_page1.png   # Converted images (if --save-images)
    └── document1_page2.png
```

---

## Evaluation Commands

### benchmark - Ablation Studies

Run systematic ablation experiments comparing extraction methods (E1, E2, E3).

**Syntax:**
```bash
python3 -m src.cli benchmark <directory> --ablation E1|E2|E3 [options]
```

**Options:**

| Option | Description | Required |
|--------|-------------|----------|
| `--ablation` | Experiment type: `E1` (native), `E2` (ocr), `E3` (hybrid) | Yes |
| `--output` | Output JSON file for results | No |

**Ablation Types:**

| Ablation | Description | Use Case |
|----------|-------------|----------|
| `E1` | Native PDF extraction only | Fast, good for clean PDFs |
| `E2` | OCR extraction only | Accurate for scanned documents |
| `E3` | Hybrid routing (adaptive) | Best for mixed document types |

**Examples:**

```bash
# Run native-only benchmark (E1)
python3 -m src.cli benchmark data/batch3/ --ablation E1 --output e1_results.json

# Run OCR benchmark (E2)
python3 -m src.cli benchmark data/batch3/ --ablation E2 --output e2_results.json

# Run hybrid benchmark (E3)
python3 -m src.cli benchmark data/batch3/ --ablation E3 --output e3_results.json
```

---

### evaluate - Calculate Metrics

Compare extraction results against ground truth to calculate quality metrics.

**Syntax:**
```bash
python3 -m src.cli evaluate --predictions <file> --ground-truth <file> [options]
```

**Options:**

| Option | Description | Required |
|--------|-------------|----------|
| `--predictions` | Path to predictions JSON file | Yes |
| `--ground-truth` | Path to ground truth JSON file | Yes |
| `--output` | Output metrics JSON file | No |

**Metrics Calculated:**

| Metric | Description |
|--------|-------------|
| CER | Character Error Rate |
| WER | Word Error Rate |
| Similarity | Text similarity score |

**Examples:**

```bash
# Basic evaluation
python3 -m src.cli evaluate \
  --predictions output/predictions.json \
  --ground-truth data/ground_truth.json

# With output file
python3 -m src.cli evaluate \
  --predictions output/predictions.json \
  --ground-truth data/ground_truth.json \
  --output metrics.json
```

**Sample Output:**
```
Evaluation Results:
================================================================================
Character Error Rate (CER): 2.34%
Word Error Rate (WER):      3.12%
Text Similarity:            96.88%
```

---

## Knowledge Graph Commands

### kg init - Initialize Neo4j Schema

Set up the Neo4j database schema with constraints and indexes.

**Syntax:**
```bash
python3 -m src.cli kg init
```

**Prerequisites:**
- Neo4j database must be running
- Connection configured in environment or config

**Example:**
```bash
# Initialize schema
python3 -m src.cli kg init

# Sample output:
# Initializing Neo4j knowledge graph...
# Connected to Neo4j
# Schema initialized successfully
#   - Created constraints for unique IDs
#   - Created indexes for performance
```

---

### kg extract - Extract Entities

Extract entities and relations from documents using LLM and import to Neo4j.

**Syntax:**
```bash
python3 -m src.cli kg extract <input> [options]
```

**Options:**

| Option | Description | Default |
|--------|-------------|---------|
| `--provider` | LLM provider: `ollama`, `claude`, `openai`, `gemini` | Config default |
| `--min-confidence` | Minimum confidence threshold (0.0-1.0) | `0.7` |
| `--batch-size` | Batch size for Neo4j imports | `1000` |
| `--max-pages` | Max pages to process per PDF | `5` |
| `--output` | Output stats file path | - |

**Examples:**

```bash
# Extract from single PDF using default provider
python3 -m src.cli kg extract document.pdf

# Extract with Claude provider
python3 -m src.cli kg extract document.pdf --provider claude

# Extract from directory with custom settings
python3 -m src.cli kg extract data/documents/ \
  --provider openai \
  --min-confidence 0.8 \
  --max-pages 3 \
  --output kg_stats.json

# Process with local Ollama
python3 -m src.cli kg extract document.pdf --provider ollama
```

---

### kg import - Import to Neo4j

Import pre-extracted entity data from JSON files to Neo4j.

**Syntax:**
```bash
python3 -m src.cli kg import <input> [options]
```

**Options:**

| Option | Description | Default |
|--------|-------------|---------|
| `--pattern` | File pattern for directory import | `*.json` |
| `--batch-size` | Batch size for imports | `1000` |
| `--verbose` | Show detailed error output | `False` |

**Examples:**

```bash
# Import single extraction result
python3 -m src.cli kg import extraction_result.json

# Import all JSON files from directory
python3 -m src.cli kg import data/extractions/ --pattern "*.json"

# Import with verbose error reporting
python3 -m src.cli kg import data/extractions/ --verbose
```

---

### kg stats - Show Statistics

Display current Neo4j knowledge graph statistics.

**Syntax:**
```bash
python3 -m src.cli kg stats
```

**Example:**
```bash
python3 -m src.cli kg stats

# Sample output:
# Neo4j Knowledge Graph Statistics
# ================================================================================
# 
# Node Counts by Label:
#   Document: 150
#   Person: 45
#   Organization: 32
#   Location: 28
# 
# Relation Counts by Type:
#   MENTIONS: 234
#   LOCATED_IN: 28
#   WORKS_FOR: 12
# 
# Total: 255 nodes, 274 relations
```

---

## Usage Examples

### Extract Single PDF

```bash
# Basic hybrid extraction
python3 -m src.cli extract report.pdf

# With output and preview
python3 -m src.cli extract report.pdf --output result.json --preview

# OCR only for scanned documents
python3 -m src.cli extract scanned_doc.pdf --method ocr --output extracted.json
```

### Process Batch with Checkpoint

```bash
# Start batch processing
python3 -m src.cli extract-batch data/batch3/MOZILLA \
  --limit 100 \
  --max-pages 20 \
  --parallel 3 \
  --checkpoint data/processed/checkpoint.json \
  --project-name mozilla_batch

# Resume if interrupted (same command uses checkpoint automatically)
python3 -m src.cli extract-batch data/batch3/MOZILLA \
  --checkpoint data/processed/checkpoint.json \
  --project-name mozilla_batch
```

### Run Ablation E3 (Hybrid)

```bash
# Full hybrid benchmark
python3 -m src.cli benchmark data/batch3/ --ablation E3 --output benchmark_e3.json

# Quick test on small subset
python3 -m src.cli extract-batch data/test/ --limit 5
python3 -m src.cli benchmark data/test/ --ablation E3
```

### Build Knowledge Graph

```bash
# Step 1: Initialize Neo4j
python3 -m src.cli kg init

# Step 2: Extract entities from documents
python3 -m src.cli kg extract data/documents/ \
  --provider claude \
  --max-pages 5 \
  --min-confidence 0.75

# Step 3: Verify import
python3 -m src.cli kg stats

# Alternative: Import pre-extracted data
python3 -m src.cli kg import data/extractions/ --pattern "*.json"
```

### Initialize Neo4j

```bash
# Check Neo4j is running
curl http://localhost:7474

# Initialize schema
python3 -m src.cli kg init

# Verify
python3 -m src.cli kg stats
```

---

## Common Options

### Universal Help Option

Every command supports `--help`:

```bash
python3 -m src.cli --help
python3 -m src.cli extract --help
python3 -m src.cli kg extract --help
```

### Environment Setup

**Virtual Environment:**
```bash
# Activate before running any commands
source venv/bin/activate  # Linux/Mac
# OR
venv\Scripts\activate     # Windows
```

**Environment Variables:**
```bash
# Neo4j connection
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="your-password"

# LLM API keys (if using cloud providers)
export ANTHROPIC_API_KEY="your-key"
export OPENAI_API_KEY="your-key"
export GOOGLE_API_KEY="your-key"
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success - command completed successfully |
| `1` | Error - general error occurred |
| `2` | Misuse of command-line arguments |

Common error scenarios:
- File not found
- Invalid method or provider specified
- Neo4j connection failed
- Invalid JSON format
- Missing required arguments

---

## Tips and Best Practices

### Use Checkpoints for Large Batches

Always use checkpoints when processing large batches to enable resumption:

```bash
python3 -m src.cli extract-batch data/large_batch/ \
  --checkpoint data/processed/checkpoint.json \
  --project-name large_batch_001
```

### Start with --limit for Testing

Test your configuration on a small subset first:

```bash
# Test with 5 files
python3 -m src.cli extract-batch data/batch/ --limit 5 --max-pages 3

# If successful, run full batch
python3 -m src.cli extract-batch data/batch/
```

### Activate Virtual Environment

Always activate the virtual environment before running commands:

```bash
source venv/bin/activate
python3 -m src.cli [command]
```

### Check Neo4j for KG Commands

Before running knowledge graph commands, verify Neo4j is accessible:

```bash
# Check if Neo4j is running
curl http://localhost:7474

# Or check with the stats command
python3 -m src.cli kg stats
```

### Use Appropriate Extraction Methods

| Document Type | Recommended Method |
|---------------|-------------------|
| Clean digital PDFs | `native` or `hybrid` |
| Scanned documents | `ocr` or `hybrid` |
| Mixed quality batch | `hybrid` (default) |
| Quick testing | `native` (fastest) |

### Monitor Resource Usage

For large batches, consider:
- Adjusting `--parallel` based on CPU cores
- Using `--max-pages` to limit processing time
- Monitoring disk space for `--save-images`

### Naming Conventions

Use descriptive project names for checkpoints:
```bash
--project-name "batch3_mozilla_2024_03"
```

---

## Quick Reference Card

```bash
# Extraction
python3 -m src.cli extract <pdf> [--method native|ocr|hybrid] [--output file.json]
python3 -m src.cli extract-batch <dir> [--limit N] [--parallel N] [--checkpoint file]

# Evaluation
python3 -m src.cli benchmark <dir> --ablation E1|E2|E3 [--output file.json]
python3 -m src.cli evaluate --predictions <file> --ground-truth <file>

# Knowledge Graph
python3 -m src.cli kg init
python3 -m src.cli kg extract <file|dir> [--provider claude|openai|ollama|gemini]
python3 -m src.cli kg import <file|dir> [--pattern *.json]
python3 -m src.cli kg stats
```

---

*For more information, see the project documentation in `/Users/sachin/Desktop/Uni Courses/CSE 573 - SWM/2Project/docs/`.*
