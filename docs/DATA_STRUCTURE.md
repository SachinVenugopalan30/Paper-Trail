# Data Structure Documentation

Complete documentation of data organization, formats, and schemas used throughout the pipeline.

## Table of Contents

- [Batch Organization](#batch-organization)
- [Processed Output Format](#processed-output-format)
- [Result JSON Schema](#result-json-schema)
- [Checkpoint Format](#checkpoint-format)
- [Training Data Format](#training-data-format)
- [Image Folder Structure](#image-folder-structure)

---

## Batch Organization

The project uses a three-batch structure for organizing source PDFs.

### Directory Structure

```
data/
├── batch2/                    # GhostScript + Apache TIKA bug reports
│   ├── GHOSTSCRIPT/          # GhostScript bug reports (~1245 PDFs)
│   └── TIKA/                 # Apache TIKA bug reports (~1211 PDFs)
├── batch3/                    # Mozilla Firefox bug reports
│   └── MOZILLA/              # Mozilla bugzilla reports (~6835 PDFs)
└── batch4/                    # LibreOffice + OpenOffice + pdf.js
    ├── LIBRE_OFFICE/         # LibreOffice bug reports (~456 PDFs)
    ├── OOO/                  # OpenOffice bug reports (~512 PDFs)
    └── pdf.js/               # pdf.js bug reports (~455 PDFs)
```

### Batch Details

| Batch | Name | Document Types | Approx. Count | Source |
|-------|------|----------------|---------------|--------|
| 2 | Legacy Tools | GHOSTSCRIPT, TIKA | ~2,456 | GhostScript + Apache TIKA bugzilla |
| 3 | Mozilla | MOZILLA | ~6,835 | Firefox/Mozilla bug reports |
| 4 | Office Tools | LIBRE_OFFICE, OOO, pdf.js | ~1,423 | LibreOffice ecosystem |

### File Naming Convention

PDFs follow a consistent naming pattern:

```
{BATCH}-{DOCUMENT_ID}-{PAGE_NUMBER}.pdf

Examples:
  MOZILLA-1000230-0.pdf
  GHOSTSCRIPT-687900-0.pdf
  LIBRE_OFFICE-12345-0.pdf
```

Where:
- `{BATCH}`: Source batch identifier (e.g., MOZILLA, GHOSTSCRIPT)
- `{DOCUMENT_ID}`: Unique bug report ID
- `{PAGE_NUMBER}`: Always 0 (multi-page PDFs)

### Document Type Extraction

Document type is determined from the parent folder name:

```python
def get_pdf_type(pdf_path: str) -> Tuple[str, str]:
    """Extract batch and document type from PDF path."""
    path_str = str(pdf_path)
    
    # Determine batch
    if 'batch2' in path_str:
        batch = 'batch2'
    elif 'batch3' in path_str:
        batch = 'batch3'
    elif 'batch4' in path_str:
        batch = 'batch4'
    
    # Determine type from parent folder
    pdf_path_obj = Path(pdf_path)
    parent = pdf_path_obj.parent.name
    if parent not in ['batch2', 'batch3', 'batch4']:
        doc_type = parent
    else:
        # Fallback to filename prefix
        filename = pdf_path_obj.name
        doc_type = filename.split('-')[0] if '-' in filename else 'unknown'
    
    return batch, doc_type
```

---

## Processed Output Format

After processing, results are organized hierarchically by batch and document type.

### Output Directory Structure

```
data/processed/
├── batch2/
│   ├── GHOSTSCRIPT/
│   │   ├── checkpoint.json          # Processing checkpoint
│   │   ├── images/                   # Converted PNG images
│   │   │   ├── GHOSTSCRIPT-687900-0/
│   │   │   │   ├── GHOSTSCRIPT-687900-0_page_0001.png
│   │   │   │   ├── GHOSTSCRIPT-687900-0_page_0002.png
│   │   │   │   └── ...
│   │   │   └── ...
│   │   └── results/                  # Extraction results
│   │       ├── GHOSTSCRIPT-687900-0_results.json
│   │       └── ...
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

### Output Directories

| Directory | Purpose | Retention |
|-----------|---------|-----------|
| `checkpoint.json` | Resume processing state | Permanent |
| `images/` | Converted PNGs from PDF pages | Permanent (for annotation) |
| `results/` | JSON extraction results | Permanent |

---

## Result JSON Schema

Each processed PDF generates a result JSON file with per-page extraction data.

### File Location

```
data/processed/{batch}/{type}/results/{BATCH}-{ID}-{PAGE}_results.json

Example:
data/processed/batch3/MOZILLA/results/MOZILLA-1000230-0_results.json
```

### JSON Schema

```json
{
  "source_pdf": "string",           // Original PDF path
  "total_pages": "integer",         // Total number of pages
  "pages": [                        // Array of page results
    {
      "page_number": "integer",     // Page number (1-indexed)
      "native": {                   // Native extraction results
        "text": "string",           // Extracted text
        "tables": [                   // Tables on this page
          [
            ["cell1", "cell2"],
            ["cell3", "cell4"]
          ]
        ],
        "coverage": "float",        // Text coverage (0.0-1.0)
        "word_count": "integer",    // Number of words
        "char_count": "integer",    // Number of characters
        "success": "boolean",       // Extraction succeeded
        "error": "string|null",     // Error message if failed
        "processing_time_ms": "integer"  // Processing time
      },
      "ocr": {                      // OCR extraction results
        "text": "string",           // Extracted text
        "success": "boolean",       // OCR succeeded
        "error": "string|null",     // Error message if failed
        "image_path": "string|null", // Path to saved PNG
        "processing_time_ms": "integer"  // Processing time
      }
    }
  ],
  "summary": {                      // Aggregate statistics
    "native_success_rate": "string",    // e.g., "15/15"
    "ocr_success_rate": "string",       // e.g., "14/15"
    "average_native_coverage": "float",   // Average coverage
    "ocr_failed_pages": ["integer"],    // List of failed page numbers
    "native_failed_pages": ["integer"], // List of failed page numbers
    "total_processing_time_seconds": "float",
    "extracted_at": "string"            // ISO timestamp
  },
  "status": "string",               // "complete", "skipped", "error"
  "result_file": "string",          // Path to this result file
  "summary.error": "string|null"    // Overall error if any
}
```

### Example Result File

```json
{
  "source_pdf": "data/batch3/MOZILLA/MOZILLA-1000230-0.pdf",
  "total_pages": 3,
  "pages": [
    {
      "page_number": 1,
      "native": {
        "text": "Bug 1000230 - Firefox crashes on startup\n\nDescription: When launching Firefox...",
        "tables": [],
        "coverage": 0.95,
        "word_count": 245,
        "char_count": 1847,
        "success": true,
        "error": null,
        "processing_time_ms": 45
      },
      "ocr": {
        "text": "Bug 1000230 - Firefox crashes on startup\n\nDescription: When launching Firefox...",
        "success": true,
        "error": null,
        "image_path": "data/processed/batch3/MOZILLA/images/MOZILLA-1000230-0/MOZILLA-1000230-0_page_0001.png",
        "processing_time_ms": 84520
      }
    },
    {
      "page_number": 2,
      "native": {
        "text": "Steps to Reproduce:\n1. Open Firefox\n2. Navigate to...",
        "tables": [],
        "coverage": 0.88,
        "word_count": 156,
        "char_count": 1092,
        "success": true,
        "error": null,
        "processing_time_ms": 38
      },
      "ocr": {
        "text": "Steps to Reproduce:\n1. Open Firefox\n2. Navigate to...",
        "success": true,
        "error": null,
        "image_path": "data/processed/batch3/MOZILLA/images/MOZILLA-1000230-0/MOZILLA-1000230-0_page_0002.png",
        "processing_time_ms": 82340
      }
    }
  ],
  "summary": {
    "native_success_rate": "3/3",
    "ocr_success_rate": "3/3",
    "average_native_coverage": 0.915,
    "ocr_failed_pages": [],
    "native_failed_pages": [],
    "total_processing_time_seconds": 167.4,
    "extracted_at": "2026-03-18T10:30:00"
  },
  "status": "complete",
  "result_file": "data/processed/batch3/MOZILLA/results/MOZILLA-1000230-0_results.json"
}
```

### Status Values

| Status | Description |
|--------|-------------|
| `complete` | Successfully processed all pages |
| `skipped` | PDF skipped (e.g., too many pages) |
| `error` | Processing failed with error |
| `already_processed` | File was already in checkpoint |

---

## Checkpoint Format

Checkpoints track processing progress and enable resume capability.

### File Location

```
data/processed/{batch}/{type}/checkpoint.json

Example:
data/processed/batch3/MOZILLA/checkpoint.json
```

### Checkpoint Schema

```json
{
  "project": "string",              // Project name
  "started_at": "string",           // ISO timestamp
  "last_updated": "string",          // ISO timestamp
  "processed_files": {               // Successfully completed
    "filename.pdf": {
      "status": "complete",
      "total_pages": "integer",
      "completed_at": "string"
    }
  },
  "failed_files": {                  // Failed with errors
    "filename.pdf": {
      "error": "string",
      "stage": "string",
      "failed_at": "string"
    }
  },
  "skipped_files": {                 // Intentionally skipped
    "filename.pdf": {
      "reason": "string",
      "skipped_at": "string",
      "page_count": "integer"  // Optional
    }
  },
  "in_progress_files": {              // Currently processing
    "filename.pdf": {
      "total_pages": "integer",
      "pages_done": "integer",
      "last_page": "integer",
      "started_at": "string"
    }
  }
}
```

### Example Checkpoint

```json
{
  "project": "mozilla_batch",
  "started_at": "2026-03-18T09:00:00",
  "last_updated": "2026-03-18T14:30:00",
  "processed_files": {
    "MOZILLA-1000230-0.pdf": {
      "status": "complete",
      "total_pages": 3,
      "completed_at": "2026-03-18T09:02:47"
    },
    "MOZILLA-1001080-0.pdf": {
      "status": "complete",
      "total_pages": 5,
      "completed_at": "2026-03-18T09:15:32"
    }
  },
  "failed_files": {
    "MOZILLA-1005000-0.pdf": {
      "error": "PDF conversion failed: poppler error",
      "stage": "conversion",
      "failed_at": "2026-03-18T09:20:15"
    }
  },
  "skipped_files": {
    "MOZILLA-1009999-0.pdf": {
      "reason": "Too many pages: 45",
      "skipped_at": "2026-03-18T09:25:00",
      "page_count": 45
    }
  },
  "in_progress_files": {}
}
```

### Checkpoint Stages

When a file fails, the `stage` field indicates where the failure occurred:

| Stage | Description |
|-------|-------------|
| `page_count` | Failed to get page count |
| `conversion` | PDF to image conversion failed |
| `native` | Native text extraction failed |
| `ocr` | OCR extraction failed |
| `processing` | General processing error |
| `unknown` | Unspecified error |

### Checkpoint Operations

```python
from src.extraction import CheckpointManager

# Initialize checkpoint
checkpoint = CheckpointManager(
    checkpoint_path="data/processed/checkpoint.json",
    project_name="my_batch"
)

# Check if file processed
if checkpoint.is_processed("document.pdf"):
    print("Already processed")

# Mark operations
checkpoint.mark_file_complete("document.pdf")
checkpoint.mark_file_failed("document.pdf", "Error message", "ocr")
checkpoint.mark_file_skipped("document.pdf", "Too many pages")

# Get statistics
stats = checkpoint.get_stats()
print(f"Processed: {stats['processed']}")

# Reset operations
checkpoint.reset_file("document.pdf")  # Reset single file
checkpoint.reset_all()                   # Reset all (use with caution!)
```

---

## Training Data Format

Training data is generated from ground truth annotations for model evaluation.

### File Location

```
training_data.json
# or
ground_truth_annotations.json
```

### Training Data Schema

```json
{
  "metadata": {
    "created_at": "string",
    "total_annotations": "integer",
    "source": "string"
  },
  "annotations": [
    {
      "id": "string",               // Unique annotation ID
      "pdf_path": "string",         // Source PDF path
      "page_number": "integer",     // Page number (1-indexed)
      
      // Extraction results
      "native_text": "string",      // Native extraction text
      "ocr_text": "string",         // OCR extraction text
      
      // Annotation
      "selected_method": "string",   // "native", "ocr", or "hybrid"
      "edited_text": "string",      // Corrected ground truth text
      
      // Quality metrics
      "cer_native": "float",        // CER for native vs ground truth
      "cer_ocr": "float",           // CER for OCR vs ground truth
      
      // Additional info
      "native_coverage": "float",   // Native text coverage
      "ocr_success": "boolean",     // OCR succeeded
      
      // Timestamps
      "created_at": "string",
      "updated_at": "string"
    }
  ],
  "statistics": {
    "method_distribution": {
      "native": "integer",
      "ocr": "integer",
      "hybrid": "integer"
    },
    "average_cer_native": "float",
    "average_cer_ocr": "float",
    "ocr_failure_rate": "float"
  }
}
```

### Example Training Data Entry

```json
{
  "id": "MOZILLA-1000230-0_page_1",
  "pdf_path": "data/batch3/MOZILLA/MOZILLA-1000230-0.pdf",
  "page_number": 1,
  "native_text": "Bug 1000230 - Firefox crashes on startup...",
  "ocr_text": "Bug 1000230 - Firefox crashes on startup...",
  "selected_method": "ocr",
  "edited_text": "Bug 1000230 - Firefox crashes on startup when loading...",
  "cer_native": 0.15,
  "cer_ocr": 0.05,
  "native_coverage": 0.95,
  "ocr_success": true,
  "created_at": "2026-03-18T10:30:00",
  "updated_at": "2026-03-18T10:30:00"
}
```

### Statistics Section

```json
{
  "statistics": {
    "method_distribution": {
      "native": 24,
      "ocr": 62,
      "hybrid": 0
    },
    "average_cer_native": 0.184,
    "average_cer_ocr": 0.142,
    "ocr_failure_rate": 0.05
  }
}
```

### Using Training Data

```python
import json

# Load training data
with open("training_data.json") as f:
    data = json.load(f)

# Access annotations
for annotation in data["annotations"]:
    print(f"PDF: {annotation['pdf_path']}")
    print(f"Selected: {annotation['selected_method']}")
    print(f"CER - Native: {annotation['cer_native']:.3f}, OCR: {annotation['cer_ocr']:.3f}")

# Get statistics
stats = data["statistics"]
print(f"Total annotations: {stats['total_annotations']}")
print(f"Native preferred: {stats['method_distribution']['native']}")
print(f"OCR preferred: {stats['method_distribution']['ocr']}")
```

---

## Image Folder Structure

Converted PNG images are organized for annotation and debugging.

### Directory Structure

```
data/processed/{batch}/{type}/images/
└── {BATCH}-{ID}-{PAGE}/              # One folder per PDF
    ├── {BATCH}-{ID}-{PAGE}_page_0001.png
    ├── {BATCH}-{ID}-{PAGE}_page_0002.png
    ├── {BATCH}-{ID}-{PAGE}_page_0003.png
    └── ...
```

### Example

```
data/processed/batch3/MOZILLA/images/
└── MOZILLA-1000230-0/
    ├── MOZILLA-1000230-0_page_0001.png
    ├── MOZILLA-1000230-0_page_0002.png
    └── MOZILLA-1000230-0_page_0003.png
```

### Image Specifications

| Property | Value | Description |
|----------|-------|-------------|
| Format | PNG | Portable Network Graphics |
| DPI | 200 (default) | Dots per inch |
| Color | RGB | 24-bit color |
| Size | Varies | Depends on PDF page size |

### Image Naming Convention

```
{BATCH}-{ID}-{PAGE}_page_{NUMBER:04d}.png

Example:
  MOZILLA-1000230-0_page_0001.png
  MOZILLA-1000230-0_page_0002.png
```

### Configuration

DPI can be adjusted in `BatchProcessor`:

```python
from src.extraction import BatchProcessor

processor = BatchProcessor(
    output_dir="data/processed",
    checkpoint_path="data/processed/checkpoint.json",
    project_name="my_batch",
    ocr_dpi=150  # Lower DPI = smaller files, faster processing
)
```

Or in `config/extraction.yaml`:

```yaml
extraction:
  pdf_dpi: 200  # 150-300 recommended
```

### Image Retention Policy

Images are kept permanently for:
1. **Ground truth annotation** - Visual comparison with extracted text
2. **Debugging** - Verify OCR quality
3. **Training** - Potential ML training data

To skip image saving (faster processing, less storage):

```bash
# CLI
python3 -m src.cli extract-batch ... --no-images

# Python
processor = BatchProcessor(
    ...,
    save_images=False  # Don't save PNGs
)
```

### Storage Estimates

| PDF Pages | DPI 200 | DPI 150 | DPI 300 |
|-----------|---------|---------|---------|
| 1 page | ~500KB | ~300KB | ~1MB |
| 5 pages | ~2.5MB | ~1.5MB | ~5MB |
| 10 pages | ~5MB | ~3MB | ~10MB |
| 100 PDFs avg 5 pages | ~250MB | ~150MB | ~500MB |

### Accessing Images

```python
from pathlib import Path

# Get image paths for a PDF
pdf_name = "MOZILLA-1000230-0"
image_dir = Path(f"data/processed/batch3/MOZILLA/images/{pdf_name}")

image_paths = sorted(image_dir.glob("*.png"))
for img_path in image_paths:
    print(f"Page {img_path.stem}: {img_path}")
```

### In Annotation Tool

The Streamlit annotation tool automatically loads images from the `images/` directory:

```python
# In ground_truth_tool.py
image_path = f"{images_dir}/{pdf_name}/{pdf_name}_page_{page_num:04d}.png"
if Path(image_path).exists():
    st.image(image_path, caption=f"Page {page_num}")
```

---

## Summary

### Quick Reference

| Data Type | Location | Format | Key Fields |
|-----------|----------|--------|------------|
| Source PDFs | `data/batch*/` | PDF | `{BATCH}-{ID}-{PAGE}.pdf` |
| Results | `data/processed/*/*/results/` | JSON | `source_pdf`, `pages[]`, `summary` |
| Checkpoints | `data/processed/*/*/` | JSON | `processed_files`, `failed_files` |
| Images | `data/processed/*/*/images/` | PNG | `{BATCH}-{ID}-{PAGE}_page_{NUM}.png` |
| Training Data | `training_data.json` | JSON | `annotations[]`, `statistics` |

### Data Flow

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Source PDFs │────▶│  Processing  │────▶│   Results    │
│  (batch*/ )  │     │  (BatchProc) │     │  (JSON)     │
└──────────────┘     └──────────────┘     └──────────────┘
                                                  │
                                                  ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Training    │◀────│  Annotation  │◀────│   Images    │
│   Data       │     │   (Streamlit)│     │   (PNG)     │
└──────────────┘     └──────────────┘     └──────────────┘
```

### File Sizes (Typical)

| File Type | Average Size | 1000 Files |
|-----------|--------------|------------|
| Source PDF | 150KB | 150MB |
| Result JSON | 50KB | 50MB |
| Images (200 DPI) | 2.5MB (5 pages) | 2.5GB |
| Checkpoint | 10KB | 10KB |
| Training Data | 100KB | 100KB |

---

**Version:** 1.0  
**Last Updated:** March 18, 2026
