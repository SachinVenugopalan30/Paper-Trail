# Extraction Pipeline Documentation

## Overview

The extraction pipeline provides three methods for extracting text from PDF bug reports:

1. **Native (E1)**: Uses pdfplumber for text extraction
2. **OCR (E2)**: Uses GLM-OCR Visual Language Model for OCR
3. **Hybrid (E3)**: Automatically routes based on text coverage analysis

## Architecture

```
PDF Input
    ↓
[Native Extraction] ──┐
    ↓                 │
[Text Coverage]       │
    ↓                 │
> 80% coverage? ──YES─┼──→ Use Native
    │                 │
   NO                 │
    ↓                 │
[OCR Extraction] ─────┘
    ↓
[Combined Result]
```

## Native Extraction (E1)

**File:** `src/extraction/native.py`

### Key Functions

#### `extract_native(pdf_path: str) -> Dict`

Extracts text, tables, and metadata from PDF using pdfplumber with per-page granularity.

**Returns:**
```python
{
    "pages": [
        {
            "text": str,           # Page text
            "tables": [...],       # Tables on this page
            "coverage": float,     # Page-level coverage (0.0-1.0)
            "word_count": int,
            "char_count": int
        }
    ],
    "metadata": {...},           # PDF metadata
    "total_pages": int,
    "overall_coverage": float     # Average of all pages
}
```

**Example:**
```python
from src.extraction import extract_native

result = extract_native("bug_report.pdf")
print(f"Pages: {result['total_pages']}")
print(f"Page 1 text: {result['pages'][0]['text'][:100]}")
print(f"Coverage: {result['pages'][0]['coverage']:.2%}")
```

#### `extract_tables_from_pdf(pdf_path: str) -> List[List[List[str]]]`

Extracts all tables from PDF as list of row lists.

**Example:**
```python
tables = extract_tables_from_pdf("report.pdf")
for table in tables:
    for row in table:
        print(row)  # ['Header1', 'Header2', ...]
```

### Coverage Calculation

Coverage estimates the percentage of page area containing text:

```python
def _calculate_page_coverage(page, char_count: int) -> float:
    page_area = page.width * page.height
    estimated_char_area = char_count * 20  # 20 square units per char
    coverage = min(estimated_char_area / page_area, 1.0)
    return coverage
```

**Interpretation:**
- 0-30%: Low coverage (scanned document or sparse text)
- 30-70%: Medium coverage (mixed content)
- 70-100%: High coverage (text-dense document)

## OCR Extraction (E2)

**File:** `src/extraction/ocr.py`

### Key Functions

#### `extract_ocr(image_path: str, max_tokens: int = 4096) -> str`

Extracts text from image using GLM-OCR HTTP API.

**Parameters:**
- `image_path`: Path to PNG image
- `max_tokens`: Maximum tokens to generate (default: 4096)
- `timeout`: HTTP timeout in seconds (default: 300)

**Returns:**
Extracted text as string

**Example:**
```python
from src.extraction import extract_ocr

text = extract_ocr("page_001.png", max_tokens=4096)
print(text)
```

#### `GLMOCRClient` Class

Wrapper for GLM-OCR HTTP API with retry logic.

```python
from src.extraction.ocr import GLMOCRClient

client = GLMOCRClient(
    base_url="http://localhost:8080",
    model="mlx-community/GLM-OCR-bf16"
)

text = client.extract_text("page.png", max_tokens=4096)
```

**Features:**
- Automatic retry with exponential backoff
- Base64 image encoding
- Streaming response handling
- Error logging

### Setting Up GLM-OCR Server

**macOS (Apple Silicon):**
```bash
# Install dependencies
pip install mlx-lm mlx-vlm

# Clone and setup GLM-OCR
git clone https://github.com/your-org/glm-ocr-server.git
cd glm-ocr-server
python3 server.py

# Server runs on http://localhost:8080
```

**Configuration:**
Edit `config/extraction.yaml`:
```yaml
api_host: "localhost:8080"
model: "mlx-community/GLM-OCR-bf16"
```

## Hybrid Routing (E3)

**File:** `src/extraction/router.py`

### Key Functions

#### `route_extraction(pdf_path: str, threshold: float = 0.8) -> str`

Determines which extraction method to use based on coverage.

**Parameters:**
- `pdf_path`: Path to PDF
- `threshold`: Coverage threshold (default: 0.8)

**Returns:** One of:
- `"native"`: Use native extraction only
- `"ocr"`: Use OCR only
- `"both"`: Extract with both for comparison

**Logic:**
```python
if native_coverage >= threshold:
    return "native"
else:
    return "ocr"
```

#### `extract_with_routing(pdf_path: str, threshold: float = 0.8) -> Dict`

Extracts text using the routed method.

**Example:**
```python
from src.extraction.router import extract_with_routing

result = extract_with_routing("bug.pdf", threshold=0.8)
print(result["method"])  # "native" or "ocr"
print(result["text"][:100])
```

#### `extract_both_methods(pdf_path: str) -> Dict`

Extracts with BOTH methods for comparison.

**Returns:**
```python
{
    "native": {
        "text": str,
        "coverage": float,
        "time_ms": float
    },
    "ocr": {
        "text": str,
        "time_ms": float
    },
    "native_selected": bool,  # Which was better
    "cer": float,  # Character Error Rate
    "wer": float   # Word Error Rate
}
```

## Batch Processing

**File:** `src/extraction/batch_processor.py`

### `BatchProcessor` Class

Processes multiple PDFs in parallel with checkpoint support.

#### Initialization

```python
from src.extraction import BatchProcessor

processor = BatchProcessor(
    output_dir="data/processed/mozilla",
    checkpoint_path="data/processed/mozilla/checkpoint.json",
    project_name="mozilla_batch",
    max_pages=5,
    parallel_workers=3,
    save_images=True,
    ocr_dpi=200,
    ocr_timeout=300
)
```

#### Processing

```python
# Process batch
results = processor.process_batch(
    pdf_paths=["file1.pdf", "file2.pdf", ...],
    limit=10,  # Process first 10 PDFs
    limit_pages_per_pdf=5  # Max 5 pages per PDF
)
```

### Checkpoint System

**File:** `src/extraction/checkpoint.py`

#### `CheckpointManager` Class

Tracks processing state across sessions.

```python
from src.extraction import CheckpointManager

checkpoint = CheckpointManager(
    checkpoint_path="data/processed/checkpoint.json",
    project_name="my_batch"
)

# Check if file is processed
if checkpoint.is_processed("file.pdf"):
    print("Already done, skipping")

# Mark complete
checkpoint.mark_file_complete("file.pdf")

# Mark failed
checkpoint.mark_file_failed("file.pdf", "OCR timeout", "extraction")

# Get stats
stats = checkpoint.get_stats()
print(f"Processed: {stats['processed']}, Failed: {stats['failed']}")
```

**Checkpoint States:**
- `processed_files`: Successfully completed
- `failed_files`: Failed with error message
- `skipped_files`: Skipped (e.g., too many pages)
- `in_progress_files`: Currently processing (resumable)

## PDF to Image Conversion

**File:** `src/extraction/pdf_converter.py`

#### `convert_pdf_to_images(pdf_path: str, output_dir: str, dpi: int = 200) -> List[str]`

Converts PDF pages to PNG images.

**Parameters:**
- `pdf_path`: PDF file path
- `output_dir`: Directory for output images
- `dpi`: Resolution (default: 200)
- `limit_pages`: Maximum pages to convert

**Returns:** List of image file paths

**Example:**
```python
from src.extraction.pdf_converter import convert_pdf_to_images

images = convert_pdf_to_images(
    "report.pdf",
    "output/images",
    dpi=200,
    limit_pages=5
)
print(f"Created {len(images)} images")
```

#### `get_page_count(pdf_path: str) -> int`

Gets total number of pages in PDF.

```python
from src.extraction.pdf_converter import get_page_count

pages = get_page_count("document.pdf")
print(f"Total pages: {pages}")
```

## Output Format

### Result JSON Structure

Each processed PDF produces a `*_results.json` file:

```json
{
  "source_pdf": "data/batch3/MOZILLA/MOZILLA-123456-0.pdf",
  "total_pages": 4,
  "pages": [
    {
      "page_number": 1,
      "native": {
        "text": "Bug 123456...",
        "tables": [],
        "coverage": 0.0654,
        "word_count": 150,
        "char_count": 850,
        "success": true,
        "error": null,
        "processing_time_ms": 45
      },
      "ocr": {
        "text": "Bug 123456...",
        "success": true,
        "error": null,
        "image_path": ".../MOZILLA-123456-0_page_0001.png",
        "processing_time_ms": 77992
      }
    }
  ],
  "summary": {
    "native_success_rate": "4/4",
    "ocr_success_rate": "4/4",
    "average_native_coverage": 0.0608,
    "ocr_failed_pages": [],
    "native_failed_pages": [],
    "total_processing_time_seconds": 287.45,
    "extracted_at": "2026-03-17T19:34:22.831116"
  }
}
```

### Key Fields

- `source_pdf`: Original PDF path
- `total_pages`: Number of pages in PDF
- `pages`: Array of page results
  - `page_number`: 1-indexed page number
  - `native`: Native extraction results
  - `ocr`: OCR extraction results
- `summary`: Aggregated statistics

## Usage Examples

### Single PDF Extraction

```python
from src.extraction import extract_native, extract_ocr, route_extraction

# Method 1: Native only
native_result = extract_native("bug.pdf")
print(native_result["pages"][0]["text"])

# Method 2: OCR only (requires image conversion)
from src.extraction.pdf_converter import convert_pdf_to_images
images = convert_pdf_to_images("bug.pdf", "/tmp/images")
ocr_text = extract_ocr(images[0])
print(ocr_text)

# Method 3: Hybrid (recommended)
method = route_extraction("bug.pdf", threshold=0.8)
print(f"Using: {method}")
```

### Batch Extraction

```python
from src.extraction import BatchProcessor
import glob

# Find PDFs
pdfs = glob.glob("data/batch3/MOZILLA/*.pdf")

# Process
processor = BatchProcessor(
    output_dir="data/processed/mozilla",
    checkpoint_path="data/processed/mozilla/checkpoint.json",
    project_name="mozilla_batch",
    max_pages=5,
    parallel_workers=3,
    save_images=True
)

results = processor.process_batch(pdfs[:100])  # First 100
```

### CLI Commands

```bash
# Extract single PDF
python3 -m src.cli extract input.pdf --method hybrid --output result.json

# Extract batch
python3 -m src.cli extract-batch data/batch3/MOZILLA \
  --limit 10 \
  --max-pages 5 \
  --parallel 3 \
  --save-images \
  --output-dir data/processed/mozilla

# Benchmark ablation
python3 -m src.cli benchmark data/batch3 \
  --ablation E1 \
  --output benchmark.json
```

## Performance Considerations

### Processing Time

| Method | Speed | Quality | Use Case |
|--------|-------|---------|----------|
| Native | Fast (1-2s/page) | Good for text PDFs | High coverage documents |
| OCR | Slow (60-120s/page) | Excellent for scanned | Low coverage documents |
| Hybrid | Varies | Optimal | Mixed document types |

### Memory Usage

- Native: ~100MB per PDF
- OCR: ~500MB per PDF (image processing)
- Batch: Memory scales with `parallel_workers`

**Recommendations:**
- Use `--max-pages 5` for initial testing
- Reduce `--parallel 1` if memory issues
- Enable `--save-images` only if needed for annotation

## Troubleshooting

### Issue: Native extraction returns empty text

**Cause:** Scanned PDF with no embedded text

**Solution:** Use OCR or hybrid routing
```python
result = extract_with_routing("scanned.pdf", threshold=0.5)
```

### Issue: OCR timeout errors

**Cause:** Large images or slow GLM-OCR server

**Solutions:**
1. Reduce DPI: `ocr_dpi=150`
2. Increase timeout: `ocr_timeout=600`
3. Check GLM-OCR server is running

### Issue: Batch processing interrupted

**Solution:** Use checkpoint to resume
```python
# Will automatically skip already processed files
processor = BatchProcessor(
    checkpoint_path="data/processed/checkpoint.json",
    ...
)
results = processor.process_batch(pdfs)
```

### Issue: Out of memory

**Solutions:**
1. Reduce workers: `parallel_workers=1`
2. Limit pages: `max_pages=3`
3. Process in smaller batches

## Next Steps

1. **Evaluation:** See EVALUATION_AND_BENCHMARKING.md for metrics
2. **Knowledge Graph:** See KNOWLEDGE_GRAPH.md for entity extraction
3. **CLI Reference:** See CLI_REFERENCE.md for all commands

---

**See Also:**
- `src/extraction/__init__.py` - Public API exports
- `tests/` - Unit tests for extraction (when implemented)
- `notebooks/` - Jupyter examples (when implemented)
