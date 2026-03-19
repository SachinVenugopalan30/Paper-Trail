"""
Benchmark framework for PDF text extraction methods.

This module provides comprehensive benchmarking capabilities for comparing
different extraction methods (Native, OCR, Hybrid) across multiple metrics:
- Speed (pages per second)
- Memory usage
- Character Error Rate (CER)
- Word Error Rate (WER)
"""

import json
import time
import tracemalloc
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class BenchmarkResult:
    """
    Container for single benchmark run results.
    
    Attributes:
        method: Extraction method used (e.g., 'native', 'ocr', 'hybrid')
        pdf_path: Path to the PDF file
        total_pages: Total number of pages processed
        processing_time: Time taken to process in seconds
        memory_peak: Peak memory usage in MB
        cer: Character Error Rate (if ground truth available)
        wer: Word Error Rate (if ground truth available)
        similarity: Text similarity score (if ground truth available)
        errors: List of any errors encountered
        metadata: Additional metadata about the run
    """
    method: str
    pdf_path: str
    total_pages: int
    processing_time: float
    memory_peak: float
    cer: Optional[float] = None
    wer: Optional[float] = None
    similarity: Optional[float] = None
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def pages_per_second(self) -> float:
        """Calculate processing speed in pages per second."""
        if self.processing_time > 0:
            return self.total_pages / self.processing_time
        return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for JSON serialization."""
        data = asdict(self)
        data['pages_per_second'] = self.pages_per_second
        return data


@dataclass
class ComparisonReport:
    """
    Container for method comparison results.
    
    Attributes:
        results: Dictionary mapping method names to lists of BenchmarkResults
        summary: Aggregated statistics for each method
        generated_at: Timestamp when report was generated
    """
    results: Dict[str, List[BenchmarkResult]]
    summary: Dict[str, Dict[str, float]]
    generated_at: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert report to dictionary for JSON serialization."""
        return {
            'results': {
                method: [r.to_dict() for r in results]
                for method, results in self.results.items()
            },
            'summary': self.summary,
            'generated_at': self.generated_at
        }


class Benchmark:
    """
    Main benchmark class for running ablation experiments.
    
    Supports three extraction methods:
    - E1 (Native): Native PDF text extraction using pdfplumber/pymupdf
    - E2 (OCR): OCR-based extraction using vision models
    - E3 (Hybrid): Hybrid approach combining native and OCR
    
    Example:
        >>> from src.evaluation.benchmark import Benchmark
        >>> benchmark = Benchmark()
        >>> 
        >>> # Run ablation on single PDF
        >>> result = benchmark.run_ablation(
        ...     pdf_path="document.pdf",
        ...     method="hybrid",
        ...     extract_fn=custom_extraction_function
        ... )
        >>>
        >>> # Compare multiple methods
        >>> results = {
        ...     "native": [result1, result2],
        ...     "ocr": [result3, result4],
        ...     "hybrid": [result5, result6]
        ... }
        >>> report = benchmark.compare_methods(results)
    """
    
    # Supported extraction methods
    SUPPORTED_METHODS = ['native', 'ocr', 'hybrid']
    
    def __init__(self, output_dir: Optional[str] = None):
        """
        Initialize benchmark instance.
        
        Args:
            output_dir: Directory to save benchmark results (default: ./benchmark_results)
        """
        self.output_dir = Path(output_dir) if output_dir else Path("benchmark_results")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.results_cache: Dict[str, List[BenchmarkResult]] = {method: [] for method in self.SUPPORTED_METHODS}
        
    def run_ablation(
        self,
        pdf_paths: List[str],
        method: str,
        extract_fn: Callable[[str], Dict[str, Any]],
        ground_truth_fn: Optional[Callable[[str], str]] = None
    ) -> List[BenchmarkResult]:
        """
        Run ablation experiment for a specific extraction method.
        
        Args:
            pdf_paths: List of PDF file paths to process
            method: Extraction method ('native', 'ocr', or 'hybrid')
            extract_fn: Function that takes a PDF path and returns extraction result
                       Expected return format: {'text': str, 'total_pages': int}
            ground_truth_fn: Optional function to retrieve ground truth text for a PDF path
        
        Returns:
            List of BenchmarkResult objects, one per PDF
            
        Raises:
            ValueError: If method is not supported
        """
        if method not in self.SUPPORTED_METHODS:
            raise ValueError(f"Unsupported method: {method}. Must be one of {self.SUPPORTED_METHODS}")
        
        results = []
        
        logger.info(f"Running ablation experiment: {method}")
        logger.info(f"Processing {len(pdf_paths)} PDF files...")
        
        for pdf_path in pdf_paths:
            try:
                result = self._benchmark_single_pdf(
                    pdf_path=pdf_path,
                    method=method,
                    extract_fn=extract_fn,
                    ground_truth_fn=ground_truth_fn
                )
                results.append(result)
                logger.info(f"  ✓ {pdf_path}: {result.pages_per_second:.2f} pages/sec, "
                          f"CER={result.cer:.3f if result.cer is not None else 'N/A'}")
            except Exception as e:
                logger.error(f"  ✗ {pdf_path}: {str(e)}")
                error_result = BenchmarkResult(
                    method=method,
                    pdf_path=pdf_path,
                    total_pages=0,
                    processing_time=0.0,
                    memory_peak=0.0,
                    errors=[str(e)]
                )
                results.append(error_result)
        
        # Cache results
        self.results_cache[method].extend(results)
        
        # Save individual results
        self._save_results(results, f"{method}_ablation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        
        return results
    
    def _benchmark_single_pdf(
        self,
        pdf_path: str,
        method: str,
        extract_fn: Callable[[str], Dict[str, Any]],
        ground_truth_fn: Optional[Callable[[str], str]]
    ) -> BenchmarkResult:
        """
        Benchmark a single PDF file.
        
        Args:
            pdf_path: Path to PDF file
            method: Extraction method
            extract_fn: Extraction function
            ground_truth_fn: Ground truth retrieval function
            
        Returns:
            BenchmarkResult with all metrics
        """
        # Start memory tracking
        tracemalloc.start()
        
        # Measure processing time
        start_time = time.perf_counter()
        
        try:
            extraction_result = extract_fn(pdf_path)
            extracted_text = extraction_result.get('text', '')
            total_pages = extraction_result.get('total_pages', 0)
        except Exception as e:
            tracemalloc.stop()
            raise RuntimeError(f"Extraction failed: {str(e)}") from e
        
        processing_time = time.perf_counter() - start_time
        
        # Get peak memory usage
        _, peak_memory = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_memory_mb = peak_memory / (1024 * 1024)  # Convert to MB
        
        # Calculate quality metrics if ground truth available
        cer = None
        wer = None
        similarity = None
        
        if ground_truth_fn:
            try:
                from src.evaluation.metrics import calculate_cer, calculate_wer, text_similarity
                ground_truth = ground_truth_fn(pdf_path)
                cer = calculate_cer(extracted_text, ground_truth)
                wer = calculate_wer(extracted_text, ground_truth)
                similarity = text_similarity(extracted_text, ground_truth)
            except Exception as e:
                logger.warning(f"Could not calculate quality metrics for {pdf_path}: {e}")
        
        return BenchmarkResult(
            method=method,
            pdf_path=pdf_path,
            total_pages=total_pages,
            processing_time=processing_time,
            memory_peak=peak_memory_mb,
            cer=cer,
            wer=wer,
            similarity=similarity,
            metadata={
                'timestamp': datetime.now().isoformat(),
                'extracted_length': len(extracted_text),
            }
        )
    
    def compare_methods(self, results: Optional[Dict[str, List[BenchmarkResult]]] = None) -> ComparisonReport:
        """
        Generate comparison report across multiple methods.
        
        Args:
            results: Dictionary mapping method names to lists of BenchmarkResults.
                    If None, uses cached results from previous run_ablation calls.
        
        Returns:
            ComparisonReport with aggregated statistics
        """
        if results is None:
            results = self.results_cache
        
        summary = {}
        
        for method, method_results in results.items():
            if not method_results:
                continue
            
            # Filter out results with errors
            valid_results = [r for r in method_results if not r.errors]
            
            if not valid_results:
                continue
            
            # Calculate aggregates
            total_pages = sum(r.total_pages for r in valid_results)
            total_time = sum(r.processing_time for r in valid_results)
            
            summary[method] = {
                'total_pdfs': len(valid_results),
                'total_pages': total_pages,
                'avg_pages_per_second': total_pages / total_time if total_time > 0 else 0,
                'avg_memory_mb': sum(r.memory_peak for r in valid_results) / len(valid_results),
                'avg_cer': sum(r.cer for r in valid_results if r.cer is not None) / 
                          len([r for r in valid_results if r.cer is not None]) 
                          if any(r.cer is not None for r in valid_results) else None,
                'avg_wer': sum(r.wer for r in valid_results if r.wer is not None) / 
                          len([r for r in valid_results if r.wer is not None])
                          if any(r.wer is not None for r in valid_results) else None,
                'avg_similarity': sum(r.similarity for r in valid_results if r.similarity is not None) / 
                                 len([r for r in valid_results if r.similarity is not None])
                                 if any(r.similarity is not None for r in valid_results) else None,
            }
        
        report = ComparisonReport(
            results=results,
            summary=summary,
            generated_at=datetime.now().isoformat()
        )
        
        # Save comparison report
        self._save_comparison_report(report)
        
        return report
    
    def _save_results(self, results: List[BenchmarkResult], filename: str):
        """Save benchmark results to JSON file."""
        filepath = self.output_dir / filename
        data = {'results': [r.to_dict() for r in results]}
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Results saved to {filepath}")
    
    def _save_comparison_report(self, report: ComparisonReport):
        """Save comparison report to JSON file."""
        filename = f"comparison_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = self.output_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
        
        logger.info(f"Comparison report saved to {filepath}")


def print_comparison_table(report: ComparisonReport):
    """
    Print formatted comparison table to console.
    
    Args:
        report: ComparisonReport to display
    """
    print("\n" + "=" * 100)
    print("EXTRACTION METHOD COMPARISON REPORT")
    print("=" * 100)
    print(f"Generated: {report.generated_at}")
    print("-" * 100)
    
    # Header
    print(f"{'Method':<12} {'PDFs':>8} {'Pages':>10} {'Pages/sec':>12} {'Memory(MB)':>12} "
          f"{'CER':>10} {'WER':>10} {'Similarity':>12}")
    print("-" * 100)
    
    # Rows
    for method, stats in report.summary.items():
        cer_str = f"{stats['avg_cer']:.3f}" if stats['avg_cer'] is not None else "N/A"
        wer_str = f"{stats['avg_wer']:.3f}" if stats['avg_wer'] is not None else "N/A"
        sim_str = f"{stats['avg_similarity']:.3f}" if stats['avg_similarity'] is not None else "N/A"
        
        print(f"{method:<12} {stats['total_pdfs']:>8} {stats['total_pages']:>10} "
              f"{stats['avg_pages_per_second']:>12.2f} {stats['avg_memory_mb']:>12.2f} "
              f"{cer_str:>10} {wer_str:>10} {sim_str:>12}")
    
    print("=" * 100)
    
    # Find best method for each metric
    print("\nBEST PERFORMERS:")
    if report.summary:
        # Speed
        fastest = max(report.summary.items(), 
                     key=lambda x: x[1]['avg_pages_per_second'])[0]
        print(f"  Fastest:      {fastest} ({report.summary[fastest]['avg_pages_per_second']:.2f} pages/sec)")
        
        # Memory
        lightest = min(report.summary.items(), 
                      key=lambda x: x[1]['avg_memory_mb'])[0]
        print(f"  Lightest:     {lightest} ({report.summary[lightest]['avg_memory_mb']:.2f} MB)")
        
        # Quality (lowest CER if available)
        methods_with_cer = [(m, s) for m, s in report.summary.items() if s['avg_cer'] is not None]
        if methods_with_cer:
            most_accurate = min(methods_with_cer, key=lambda x: x[1]['avg_cer'])[0]
            print(f"  Most Accurate: {most_accurate} (CER={report.summary[most_accurate]['avg_cer']:.3f})")
    print()


if __name__ == "__main__":
    # Example usage
    print("Benchmark Framework Demo")
    print("=" * 50)
    
    # Create dummy extraction functions for demonstration
    def dummy_native_extract(pdf_path: str) -> Dict[str, Any]:
        """Simulate native extraction."""
        time.sleep(0.1)  # Simulate processing
        return {'text': f"Native extracted text from {pdf_path}", 'total_pages': 5}
    
    def dummy_ocr_extract(pdf_path: str) -> Dict[str, Any]:
        """Simulate OCR extraction."""
        time.sleep(0.5)  # Simulate slower processing
        return {'text': f"OCR extracted txt from {pdf_path}", 'total_pages': 5}  # Note typo
    
    def dummy_ground_truth(pdf_path: str) -> str:
        """Simulate ground truth."""
        return f"Native extracted text from {pdf_path}"
    
    # Initialize benchmark
    benchmark = Benchmark(output_dir="./benchmark_demo_results")
    
    # Test PDFs
    test_pdfs = ["doc1.pdf", "doc2.pdf", "doc3.pdf"]
    
    # Run ablations
    print("\nRunning Native extraction...")
    native_results = benchmark.run_ablation(
        pdf_paths=test_pdfs,
        method='native',
        extract_fn=dummy_native_extract,
        ground_truth_fn=dummy_ground_truth
    )
    
    print("\nRunning OCR extraction...")
    ocr_results = benchmark.run_ablation(
        pdf_paths=test_pdfs,
        method='ocr',
        extract_fn=dummy_ocr_extract,
        ground_truth_fn=dummy_ground_truth
    )
    
    # Compare and print results
    all_results = {'native': native_results, 'ocr': ocr_results}
    report = benchmark.compare_methods(all_results)
    print_comparison_table(report)
