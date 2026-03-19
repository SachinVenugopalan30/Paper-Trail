# Scripts Guide

Complete documentation for utility scripts in the `scripts/` directory.

## Table of Contents

- [build_knowledge_graph.py](#build_knowledge_graphpy) - Knowledge graph construction
- [process_mixed_batch.py](#process_mixed_batchpy) - Mixed batch PDF processing

---

## build_knowledge_graph.py

Processes PDF extraction results and builds a Neo4j knowledge graph with entities and relationships extracted using LLM.

### Overview

This script:
1. Discovers all result files from `data/processed/*/*/results/`
2. Processes each PDF with per-page entity extraction (not combined)
3. Extracts entities and relations using LLM
4. Imports data into Neo4j with parallel processing
5. Provides checkpoint/resume capability
6. Tracks progress with detailed statistics

### Usage

#### Process All Result Files (Recommended)

```bash
# Process all result files (first 15 pages per PDF)
python3 scripts/build_knowledge_graph.py --all

# Process with custom page limit
python3 scripts/build_knowledge_graph.py --all --max-pages 10

# Use more workers for faster processing
python3 scripts/build_knowledge_graph.py --all --workers 5
```

#### Test Single PDF

```bash
# Test with a single PDF to verify setup
python3 scripts/build_knowledge_graph.py \
  --test data/processed/batch3/MOZILLA/results/XXX_results.json

# Test with custom page limit
python3 scripts/build_knowledge_graph.py \
  --test data/processed/batch3/MOZILLA/results/XXX_results.json \
  --max-pages 5
```

#### Resume from Checkpoint

```bash
# Resume interrupted processing
python3 scripts/build_knowledge_graph.py --all --resume

# Reset checkpoint and start fresh
python3 scripts/build_knowledge_graph.py --all --reset
```

### Command-Line Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--test` | str | None | Test with single PDF file |
| `--all` | flag | False | Process all result files |
| `--max-pages` | int | 15 | Maximum pages to process per PDF |
| `--workers` | int | 3 | Number of parallel workers |
| `--resume` | flag | False | Resume from checkpoint |
| `--reset` | flag | False | Reset checkpoint and start fresh |
| `--checkpoint` | str | `data/processed/kg_checkpoint.json` | Checkpoint file path |

### Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│  1. DISCOVER RESULT FILES                                        │
│     - Scan data/processed/*/*/results/*_results.json          │
│     - Collect all result files                                  │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│  2. INITIALIZE CLIENTS                                           │
│     - Connect to LLM (UnifiedLLMClient)                        │
│     - Connect to Neo4j (Neo4jClient)                           │
│     - Initialize EntityExtractionChain                           │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│  3. PROCESS PDFS IN PARALLEL                                     │
│     - Distribute files across workers (default: 3)             │
│     - For each PDF:                                              │
│       * Extract entities per-page (up to max-pages)          │
│       * Import to Neo4j immediately                             │
│       * Update checkpoint                                         │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│  4. GENERATE FINAL REPORT                                        │
│     - Total PDFs processed                                       │
│     - Entities and relations created                           │
│     - Neo4j database statistics                                   │
│     - Processing time                                            │
└─────────────────────────────────────────────────────────────────┘
```

### Processing Details

#### Per-Page Entity Extraction

For each PDF, the script:
1. Loads the result JSON with native and OCR text per page
2. Selects the best text (OCR if longer and available)
3. Extracts entities using LLM (EntityExtractionChain)
4. Imports entities and relations to Neo4j immediately
5. Skips pages with very short text (< 50 characters)
6. Limits text length for speed (first 8000 characters)

#### Text Selection Logic

```python
# Prefer OCR text if it's longer than native
native_text = page.get('native', {}).get('text', '')
ocr_text = page.get('ocr', {}).get('text', '')
text = ocr_text if len(ocr_text) > len(native_text) else native_text

# Skip very short pages
if len(text.strip()) < 50:
    continue
```

#### Checkpoint System

The script maintains a checkpoint at `data/processed/kg_checkpoint.json`:

```json
{
  "/path/to/pdf1_results.json": {
    "pdf_path": "/path/to/pdf1_results.json",
    "status": "completed",
    "pages_processed": 15,
    "total_pages": 15,
    "entities_created": 45,
    "relations_created": 12,
    "processed_at": "2026-03-18T10:30:00"
  },
  "/path/to/pdf2_results.json": {
    "pdf_path": "/path/to/pdf2_results.json",
    "status": "failed",
    "error_message": "Connection timeout"
  }
}
```

**Status values:**
- `pending`: Not yet processed
- `processing`: Currently being processed
- `completed`: Successfully processed
- `failed`: Processing failed
- `skipped`: Intentionally skipped

### Output

#### Console Output

```
======================================================================
Knowledge Graph Builder
======================================================================
Found 145 result files
Max pages per PDF: 15
Parallel workers: 3
Checkpoint: data/processed/kg_checkpoint.json

Starting processing...
======================================================================
Processing PDFs: 100%|████████████████████| 145/145 [2:34:12<00:00, entities=5234, relations=890]

======================================================================
FINAL RESULTS
======================================================================
Time: 154.2 minutes
PDFs processed: 145/145
Failed: 0
Total entities: 5234
Total relations: 890

Neo4j Database:
  BugReport: 128 nodes
  Component: 310 nodes
  Organization: 157 nodes
  Person: 144 nodes
  Technology: 130 nodes
  ...

  Total: 993 nodes, 70 relations

======================================================================
✓ Knowledge graph building complete!
======================================================================
```

#### Statistics Report

The script returns a dictionary with:

```python
{
    'total_pdfs': 145,
    'completed': 145,
    'failed': 0,
    'total_entities': 5234,
    'total_relations': 890,
    'db_stats': {
        'node_counts_by_label': {
            'BugReport': 128,
            'Component': 310,
            # ...
        },
        'relation_counts_by_type': {
            'HAS_COMPONENT': 45,
            'MENTIONS': 23,
            # ...
        }
    }
}
```

### Test Mode

Test mode processes a single PDF and shows detailed output:

```bash
python3 scripts/build_knowledge_graph.py \
  --test data/processed/batch3/MOZILLA/results/MOZILLA-1000230-0_results.json
```

**Output:**
```
======================================================================
Knowledge Graph Extraction - Single PDF Test
======================================================================

PDF: MOZILLA-1000230-0_results.json
Total pages: 15
Will process: 15 pages

======================================================================
✓ Connected to Neo4j

Processing page 1/15...
  Entities: 3
  Relations: 1

Processing page 2/15...
  Entities: 2
  Relations: 0

...

======================================================================
Results:
  Status: completed
  Entities: 45
  Relations: 12

Neo4j Database:
  BugReport: 1 nodes
  Component: 3 nodes
  Person: 2 nodes
  Technology: 1 nodes

======================================================================
✓ Test complete!
```

### Error Handling

The script handles common errors:

1. **Neo4j Connection Failure:**
   ```
   ERROR: Failed to connect to Neo4j
   ```
   - Check if Neo4j is running: `docker-compose ps neo4j`
   - Verify credentials in `config/neo4j.yaml`

2. **LLM Extraction Errors:**
   - Logs warning but continues with other pages
   - Tracks errors in checkpoint

3. **JSON Parse Errors:**
   - Skips corrupted result files
   - Logs error to checkpoint

4. **Memory Issues:**
   - Reduce `--max-pages` to process fewer pages
   - Reduce `--workers` to use less memory

### Performance Tips

1. **Increase workers for faster processing:**
   ```bash
   python3 scripts/build_knowledge_graph.py --all --workers 5
   ```

2. **Process fewer pages per PDF for quicker results:**
   ```bash
   python3 scripts/build_knowledge_graph.py --all --max-pages 5
   ```

3. **Use resume to avoid reprocessing:**
   ```bash
   python3 scripts/build_knowledge_graph.py --all --resume
   ```

4. **Monitor Neo4j memory:**
   - Default Docker config uses 2GB heap
   - Increase if processing large batches:
     ```yaml
     environment:
       - NEO4J_dbms_memory_heap_max__size=4G
     ```

---

## process_mixed_batch.py

Processes PDFs from multiple batches (batch2, batch3, batch4) with guaranteed diversity across document types. Automatically replaces skipped files to ensure target count is reached.

### Overview

This script:
1. Scans batch2, batch3, and batch4 directories for PDFs
2. Organizes PDFs by document type (batch + folder name)
3. Selects diverse PDFs ensuring minimum representation per type
4. Creates reserve pool for automatic replacement
5. Processes PDFs with checkpoint support
6. Replaces skipped/failed files from reserve pool

### Usage

#### Basic Usage (Process 100 PDFs)

```bash
# Process 100 PDFs with guaranteed type diversity
python3 scripts/process_mixed_batch.py --total 100
```

#### Ensure Minimum Per Type

```bash
# Ensure at least 5 files from each document type
python3 scripts/process_mixed_batch.py --total 100 --min-per-type 5

# Ensure at least 10 files from each type
python3 scripts/process_mixed_batch.py --total 100 --min-per-type 10
```

#### Preview Selection

```bash
# Preview which PDFs will be selected (without processing)
python3 scripts/process_mixed_batch.py --total 100 --preview

# Preview with custom minimum per type
python3 scripts/process_mixed_batch.py --total 100 --min-per-type 5 --preview
```

#### Custom Batch Distribution

```bash
# Explicitly set count from each batch
python3 scripts/process_mixed_batch.py --batch2 30 --batch3 35 --batch4 35

# Only process specific batches
python3 scripts/process_mixed_batch.py --batch2 50 --batch3 50
```

#### Process from Existing List

```bash
# Save list first
python3 scripts/process_mixed_batch.py --total 100 --save-list my_selection.txt

# Later, process from saved list
python3 scripts/process_mixed_batch.py --from-list my_selection.txt
```

#### Adjust Pool Size

```bash
# Default: 1.5x multiplier (150 PDFs for 100 target)
# Increase to 2.0x for more replacement candidates
python3 scripts/process_mixed_batch.py --total 100 --pool-size 2.0

# Decrease to 1.2x for smaller initial pool
python3 scripts/process_mixed_batch.py --total 100 --pool-size 1.2
```

### Command-Line Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--total` | int | 100 | Target number of PDFs to successfully process |
| `--min-per-type` | int | 2 | Minimum files to select from each document type |
| `--pool-size` | float | 1.5 | Multiplier for initial pool size |
| `--batch2` | int | None | Number of PDFs from batch2 (auto-distribute if not set) |
| `--batch3` | int | None | Number of PDFs from batch3 (auto-distribute if not set) |
| `--batch4` | int | None | Number of PDFs from batch4 (auto-distribute if not set) |
| `--from-list` | str | None | Process PDFs from existing list file |
| `--save-list` | str | `data/mixed_batch_selected.txt` | Save selected PDF list to this file |
| `--preview` | flag | False | Preview selection without processing |
| `--seed` | int | 42 | Random seed for reproducible selection |
| `--max-pages` | int | 5 | Maximum pages per PDF |
| `--workers` | int | 3 | Number of parallel workers |
| `--base-output-dir` | str | `data/processed` | Base output directory |
| `--no-images` | flag | False | Do not save images |

### Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│  1. SCAN BATCH DIRECTORIES                                       │
│     - batch2/: GHOSTSCRIPT, TIKA, etc.                          │
│     - batch3/: MOZILLA                                          │
│     - batch4/: LIBRE_OFFICE, OOO, pdf.js                        │
│     - Count PDFs per (batch, type) combination                  │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│  2. SELECT DIVERSE PDFS                                          │
│     - First pass: Minimum files from each type                  │
│       * Select min-per-type from each (batch, type) combo      │
│     - Second pass: Fill remaining slots randomly                │
│     - Third pass: Create reserve pool from remaining PDFs       │
│     - Shuffle primary selection                                   │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│  3. PROCESS WITH AUTO-REPLACEMENT                                │
│     - Group PDFs by (batch, type)                               │
│     - Process each group:                                         │
│       * Initialize BatchProcessor                                 │
│       * Process primary PDFs                                     │
│       * Track success/failure/skip                                │
│     - If target not reached:                                      │
│       * Replace from reserve pool                                │
│       * Continue until target reached or pool exhausted          │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│  4. GENERATE FINAL REPORT                                        │
│     - Total PDFs processed                                        │
│     - Skipped/failed counts                                       │
│     - Replacement count                                           │
│     - Type distribution                                           │
└─────────────────────────────────────────────────────────────────┘
```

### Selection Algorithm

#### Step 1: Minimum Guarantee

For each (batch, type) combination:
```python
min_per_type = 5  # From --min-per-type

for (batch, doc_type), pdfs in organized_pdfs.items():
    if len(pdfs) >= min_per_type:
        selected.extend(random.sample(pdfs, min_per_type))
    else:
        selected.extend(pdfs)  # Take all available
```

#### Step 2: Fill Remaining

Fill remaining slots from unused PDFs:
```python
remaining_slots = target_total - len(selected)
if remaining_slots > 0:
    unused_pdfs = [p for p in all_pdfs if p not in selected]
    additional = random.sample(unused_pdfs, remaining_slots)
    selected.extend(additional)
```

#### Step 3: Create Reserve Pool

Create pool for automatic replacement:
```python
reserve_size = target_total * (pool_multiplier - 1)
remaining_pdfs = [p for p in all_pdfs if p not in selected]
reserve = random.sample(remaining_pdfs, min(reserve_size, len(remaining_pdfs)))
```

### Output Structure

Results are organized hierarchically:

```
data/processed/
├── batch2/
│   ├── GHOSTSCRIPT/
│   │   ├── checkpoint.json
│   │   ├── images/
│   │   └── results/
│   └── TIKA/
│       ├── checkpoint.json
│       ├── images/
│       └── results/
├── batch3/
│   └── MOZILLA/
│       ├── checkpoint.json
│       ├── images/
│       └── results/
└── batch4/
    ├── LIBRE_OFFICE/
    │   ├── checkpoint.json
    │   ├── images/
    │   └── results/
    ├── OOO/
    └── pdf.js/
```

### Sample Output

#### Selection Phase

```
======================================================================
Mixed Batch PDF Processor - Diverse Selection
======================================================================
Target: 100 successful PDFs
Min per type: 2 files
Pool multiplier: 1.5x

Scanning batch directories...
  Found 2456 PDFs in batch2
  Found 6835 PDFs in batch3
  Found 1423 PDFs in batch4

Organizing by document type...
Found 12 document types:
  batch2/GHOSTSCRIPT: 1245 PDFs
  batch2/TIKA: 1211 PDFs
  batch3/MOZILLA: 6835 PDFs
  batch4/LIBRE_OFFICE: 456 PDFs
  batch4/OOO: 512 PDFs
  batch4/pdf.js: 455 PDFs

Selecting diverse PDFs...
  Ensuring minimum 2 files per type...
    batch2/GHOSTSCRIPT: 2 files
    batch2/TIKA: 2 files
    batch3/MOZILLA: 2 files
    ...

  Filling remaining 76 slots randomly...

Selected 100 primary + 50 reserve = 150 total

Type distribution in selection:
  batch2/GHOSTSCRIPT: 12 files
  batch2/TIKA: 10 files
  batch3/MOZILLA: 45 files
  batch4/LIBRE_OFFICE: 15 files
  batch4/OOO: 12 files
  batch4/pdf.js: 6 files

Process 100 PDFs with 50 replacements? [Y/n]:
```

#### Processing Phase

```
======================================================================
Processing with Auto-Replacement
Target: 100 successful PDFs
Primary pool: 100 PDFs
Reserve pool: 50 PDFs
======================================================================

======================================================================
Group: batch3/MOZILLA
PDFs in group: 45
======================================================================
Processing PDFs: 100%|██████████████| 45/45 [25:34<00:00, last=MOZILLA-... (complete)]
  Group results: 45 processed, 0 skipped, 0 failed

======================================================================
Group: batch2/GHOSTSCRIPT
PDFs in group: 12
======================================================================
Processing PDFs: 100%|██████████████| 12/12 [08:45<00:00, last=GHOSTSCRIPT-... (complete)]
  Group results: 57 processed, 0 skipped, 0 failed

...

======================================================================
FINAL RESULTS
======================================================================
  Successfully processed: 100 PDFs
    (Target was: 100)
  Skipped: 0 PDFs
  Failed: 0 PDFs
  Replaced: 0 PDFs from reserve

  Results saved to: data/processed/
  Organized by: batch/type/results/

  ✓ Target reached: 100 PDFs
```

### Preview Mode Output

```
======================================================================
PREVIEW MODE - Primary Selection:
======================================================================
  1. [batch3/MOZILLA] MOZILLA-1000230-0.pdf
  2. [batch3/MOZILLA] MOZILLA-1001080-0.pdf
  3. [batch2/GHOSTSCRIPT] GHOSTSCRIPT-687900-0.pdf
  4. [batch4/LIBRE_OFFICE] LIBRE_OFFICE-12345-0.pdf
  ...

Reserve pool: 50 PDFs ready for replacement

Use without --preview to process
```

### Replacement Logic

When files are skipped or fail:

```python
while len(processed_pdfs) < target_count and reserve_pdfs:
    needed = target_count - len(processed_pdfs)
    to_replace = min(needed, len(reserve_pdfs))
    
    replacements = reserve_pdfs[:to_replace]
    reserve_pdfs = reserve_pdfs[to_replace:]
    
    # Group replacements by type
    replacement_groups = group_by_type(replacements)
    
    # Process replacements
    for (batch, doc_type), group_pdfs in replacement_groups.items():
        results = processor.process_batch(group_pdfs)
        # Track results...
```

### Checkpoint Files

Each group maintains its own checkpoint:

```
data/processed/batch3/MOZILLA/checkpoint.json
data/processed/batch2/GHOSTSCRIPT/checkpoint.json
data/processed/batch4/LIBRE_OFFICE/checkpoint.json
```

This allows:
- Resuming individual groups
- Parallel processing of different groups
- Tracking per-type statistics

### Test Mode

Preview mode is useful for:
1. Verifying selection diversity
2. Checking PDF availability
3. Estimating processing time
4. Validating batch distribution

```bash
# Quick preview
python3 scripts/process_mixed_batch.py --total 100 --preview

# Preview with verbose output
python3 scripts/process_mixed_batch.py --total 100 --min-per-type 5 --preview
```

### Statistics Tracking

The script tracks detailed statistics:

```python
{
    'processed': int,      # Successfully processed
    'failed': int,         # Failed with errors
    'skipped': int,        # Skipped (too many pages, etc.)
    'replaced': int,       # Replaced from reserve
}
```

### Troubleshooting

#### "Not enough PDFs available"

```
Warning: Only 45 additional PDFs available
```

**Solution:**
- Reduce `--total` target
- Increase `--pool-size` for larger initial selection
- Check batch directories have PDFs

#### Replacement pool exhausted

```
⚠️  Warning: Only 95/100 PDFs processed successfully
```

**Solution:**
- Increase `--pool-size` (default 1.5x → try 2.0x)
- Reduce `--max-pages` to process more PDFs
- Check why files are being skipped

#### Checkpoint conflicts

If multiple instances run simultaneously:
```
Warning: Could not load checkpoint
```

**Solution:**
- Use different `--base-output-dir` for each instance
- Wait for other process to complete
- Delete checkpoint files if stuck

### Performance Tips

1. **Increase workers:**
   ```bash
   python3 scripts/process_mixed_batch.py --total 100 --workers 5
   ```

2. **Skip image saving for faster processing:**
   ```bash
   python3 scripts/process_mixed_batch.py --total 100 --no-images
   ```

3. **Increase page limit for more valid PDFs:**
   ```bash
   python3 scripts/process_mixed_batch.py --total 100 --max-pages 10
   ```

4. **Use reproducible selection:**
   ```bash
   python3 scripts/process_mixed_batch.py --total 100 --seed 12345
   ```

### Integration with Other Scripts

#### After Processing: Build Knowledge Graph

```bash
# 1. Process PDFs
python3 scripts/process_mixed_batch.py --total 100

# 2. Build knowledge graph from results
python3 scripts/build_knowledge_graph.py --all
```

#### Reproducible Research

```bash
# Save selection for reproducibility
python3 scripts/process_mixed_batch.py \
  --total 100 \
  --min-per-type 5 \
  --seed 42 \
  --save-list experiment_1_selection.txt

# Later, reprocess same PDFs
python3 scripts/process_mixed_batch.py \
  --from-list experiment_1_selection.txt
```

---

## Common Workflows

### Full Pipeline

```bash
# 1. Process diverse batch of PDFs
python3 scripts/process_mixed_batch.py --total 100 --min-per-type 5

# 2. Build knowledge graph from results
python3 scripts/build_knowledge_graph.py --all --max-pages 15

# 3. Verify Neo4j import
python3 -c "
from src.kg import get_client
client = get_client()
client.connect()
stats = client.get_stats()
print(f'Nodes: {sum(stats[\"node_counts_by_label\"].values())}')
print(f'Relations: {sum(stats[\"relation_counts_by_type\"].values())}')
client.close()
"
```

### Testing and Validation

```bash
# Preview selection before processing
python3 scripts/process_mixed_batch.py --total 20 --preview

# Test knowledge graph build on single file
python3 scripts/build_knowledge_graph.py \
  --test data/processed/batch3/MOZILLA/results/XXX_results.json

# Process small batch to verify end-to-end
python3 scripts/process_mixed_batch.py --total 10
python3 scripts/build_knowledge_graph.py --all --max-pages 5
```

---

**Version:** 1.0  
**Last Updated:** March 18, 2026
