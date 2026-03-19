"""
Evaluation framework for PDF text extraction quality assessment.

This package provides tools for:
- Metrics calculation (CER, WER, text similarity)
- Benchmarking extraction methods (Native, OCR, Hybrid)
- Ground truth annotation via web interface

Example:
    >>> from src.evaluation.metrics import calculate_cer, calculate_wer
    >>> from src.evaluation.benchmark import Benchmark
    >>> 
    >>> # Calculate metrics
    >>> cer = calculate_cer("predicted text", "ground truth text")
    >>> wer = calculate_wer("predicted text", "ground truth text")
    >>>
    >>> # Run benchmark
    >>> benchmark = Benchmark()
    >>> results = benchmark.run_ablation(pdf_paths, "hybrid", extract_fn)

Modules:
    metrics: CER, WER, and text similarity calculations
    benchmark: Ablation experiments and method comparison
    ground_truth_tool: Web interface for manual annotation
"""

from src.evaluation.metrics import (
    calculate_cer,
    calculate_wer,
    text_similarity,
    calculate_all_metrics,
)

from src.evaluation.benchmark import (
    Benchmark,
    BenchmarkResult,
    ComparisonReport,
    print_comparison_table,
)

__all__ = [
    # Metrics
    'calculate_cer',
    'calculate_wer',
    'text_similarity',
    'calculate_all_metrics',
    # Benchmark
    'Benchmark',
    'BenchmarkResult',
    'ComparisonReport',
    'print_comparison_table',
]
