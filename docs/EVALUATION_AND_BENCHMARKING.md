# Evaluation and Benchmarking Documentation

## Overview

The evaluation system provides comprehensive metrics for comparing PDF extraction methods and building ground truth datasets for quality assessment.

## Metrics

### Character Error Rate (CER)

**File:** `src/evaluation/metrics.py`

CER measures character-level differences between predicted and reference text.

**Formula:**
```
CER = (Insertions + Deletions + Substitutions) / Total Characters in Reference
```

**Implementation:**
```python
from src.evaluation.metrics import calculate_cer

cer = calculate_cer(
    prediction="Bug 12345 reported by John",
    reference="Bug 12345 reported by John"
)
print(f"CER: {cer:.2%}")  # 0.00%
```

**Interpretation:**
- 0%: Perfect match
- 1-5%: Excellent (minor typos)
- 5-15%: Good (some errors)
- 15-30%: Fair (noticeable errors)
- >30%: Poor (significant differences)

### Word Error Rate (WER)

**File:** `src/evaluation/metrics.py`

WER measures word-level differences using Levenshtein distance.

**Formula:**
```
WER = (Insertions + Deletions + Substitutions) / Total Words in Reference
```

**Implementation:**
```python
from src.evaluation.metrics import calculate_wer

wer = calculate_wer(
    prediction="Bug reported by john",
    reference="Bug 12345 reported by John"
)
print(f"WER: {wer:.2%}")  # 40.00% (missing "12345")
```

**Interpretation:**
- 0%: Perfect match
- 1-10%: Excellent
- 10-25%: Good
- 25-50%: Fair
- >50%: Poor

### Text Similarity

**File:** `src/evaluation/metrics.py`

Sequence matching similarity using Python's difflib.

**Implementation:**
```python
from src.evaluation.metrics import text_similarity

similarity = text_similarity(
    text1="Bug 12345 reported",
    text2="Bug 12345 reported by John"
)
print(f"Similarity: {similarity:.2%}")  # 75.00%
```

## Benchmark Framework

**File:** `src/evaluation/benchmark.py`

### Ablation Studies

The benchmark system supports three ablation configurations:

#### E1: Native Only
Extract text using native PDF parsing only.

```bash
python3 -m src.cli benchmark data/batch3/MOZILLA \
  --ablation E1 \
  --output benchmark_e1.json
```

#### E2: OCR Only
Extract text using GLM-OCR only.

```bash
python3 -m src.cli benchmark data/batch3/MOZILLA \
  --ablation E2 \
  --output benchmark_e2.json
```

#### E3: Hybrid (Native + OCR)
Extract using both methods, compare, and select best based on coverage.

```bash
python3 -m src.cli benchmark data/batch3/MOZILLA \
  --ablation E3 \
  --output benchmark_e3.json
```

### Benchmark Results Format

```json
{
  "ablation": "E3",
  "pdfs_processed": 10,
  "results": [
    {
      "pdf": "MOZILLA-123456-0.pdf",
      "pages": 4,
      "native": {
        "text": "...",
        "coverage": 0.0654,
        "time_ms": 150
      },
      "ocr": {
        "text": "...",
        "time_ms": 78000
      },
      "metrics": {
        "cer": 0.12,
        "wer": 0.25,
        "similarity": 0.85
      },
      "native_selected": true,
      "reason": "Higher coverage"
    }
  ],
  "summary": {
    "native_selected_count": 7,
    "ocr_selected_count": 3,
    "avg_native_coverage": 0.084,
    "avg_processing_time": 85000
  }
}
```

### Programmatic Benchmark

```python
from src.evaluation.benchmark import Benchmark

benchmark = Benchmark(
    output_dir="benchmark_results",
    max_pages=5,
    parallel_workers=3
)

results = benchmark.run_ablation(
    pdf_paths=["file1.pdf", "file2.pdf"],
    ablation_type="E3",  # or "E1", "E2"
    extract_fn=None  # Use default
)

print(f"Native selected: {results['native_selected_count']}")
print(f"OCR selected: {results['ocr_selected_count']}")
```

## Ground Truth Annotation Tool

**File:** `src/evaluation/ground_truth_tool.py`

### Launching

```bash
source venv/bin/activate
streamlit run src/evaluation/ground_truth_tool.py
```

**Opens:** http://localhost:8501

### Features

#### 3-Column Layout
1. **Left:** Original PDF page image
2. **Middle:** Native extraction text
3. **Right:** OCR extraction text

#### Workflow
1. **Select PDF** from dropdown (auto-discovers all batch/type folders)
2. **Navigate pages** with arrow buttons
3. **Compare** Native vs OCR side-by-side
4. **Vote:**
   - "Native Better" - Native extraction is more accurate
   - "OCR Better" - OCR extraction is more accurate
   - "OCR Failed" - OCR completely failed
5. **Edit text** directly in editor for perfect ground truth
6. **Save annotation** - Stores with CER/WER metrics
7. **Export for training** - Saves to `training_data.json`

### Annotation Data Format

**Storage:** `data/processed/ground_truth_annotations.json`

```json
{
  "annotations": [
    {
      "pdf_path": "data/batch3/MOZILLA/MOZILLA-123456-0.pdf",
      "page_number": 1,
      "native_text": "Bug 123456...",
      "ocr_text": "Bug 123456...",
      "native_success": true,
      "ocr_success": true,
      "ocr_error": null,
      "selected_method": "ocr",
      "edited_text": "Bug 123456 reported by John Smith",
      "cer_native": 0.15,
      "cer_ocr": 0.05,
      "wer_native": 0.20,
      "wer_ocr": 0.10,
      "timestamp": "2026-03-18T10:30:00",
      "notes": "OCR captured email better"
    }
  ]
}
```

### Export for Training

Click "Export for Training" button to generate:

**File:** `training_data.json`

```json
[
  {
    "pdf_path": "...",
    "page_number": 1,
    "ground_truth": "Bug 123456 reported by John Smith",
    "native_raw": "Bug 123456...",
    "ocr_raw": "Bug 123456...",
    "native_success": true,
    "ocr_success": true,
    "selected_method": "ocr",
    "metrics": {
      "cer_native": 0.15,
      "cer_ocr": 0.05,
      "wer_native": 0.20,
      "wer_ocr": 0.10
    }
  }
]
```

## Current Results

### Training Dataset

**Created:** 86 annotations
- **OCR preferred:** 62 (72%)
- **Native preferred:** 24 (28%)

This confirms OCR performs better for scanned bug report PDFs.

### Annotation Distribution by Batch

```
batch2/GHOSTSCRIPT: 33 PDFs
batch2/TIKA: 3 PDFs
batch3/MOZILLA: 57 PDFs
batch4/LIBRE_OFFICE: 45 PDFs
batch4/OOO: 14 PDFs
batch4/pdf.js: 13 PDFs
```

## Quality Thresholds

Based on training data analysis:

| Metric | Excellent | Good | Fair | Poor |
|--------|-----------|------|------|------|
| CER | < 5% | 5-15% | 15-30% | > 30% |
| WER | < 10% | 10-25% | 25-50% | > 50% |
| Similarity | > 90% | 70-90% | 50-70% | < 50% |

## Best Practices

### For Benchmarking

1. **Use representative sample:** 10-20 PDFs from each batch
2. **Include variety:** Single-page and multi-page documents
3. **Set max_pages:** Limit to 5 pages for faster testing
4. **Save results:** Store benchmark JSON for comparison

### For Annotation

1. **Annotate diverse types:** Don't just annotate one batch
2. **Check both methods:** Sometimes native is better for text PDFs
3. **Edit ground truth:** Use editor for perfect text when both methods fail
4. **Add notes:** Document why you chose a particular method
5. **Export regularly:** Save training data periodically

### For Evaluation

1. **Compare methods:** Look at both CER and WER
2. **Consider context:** Some errors matter more than others
3. **Track coverage:** Low coverage often means OCR is needed
4. **Monitor time:** OCR is 50-100x slower than native

## Next Steps

1. **Knowledge Graph:** See KNOWLEDGE_GRAPH.md for entity extraction
2. **RAG:** Use training data to evaluate RAG quality
3. **Improvement:** Use metrics to tune extraction thresholds

---

**See Also:**
- `src/evaluation/__init__.py` - Public API
- `src/evaluation/metrics.py` - Metric implementations
- `src/evaluation/benchmark.py` - Benchmark framework
- `src/evaluation/ground_truth_tool.py` - Streamlit UI
