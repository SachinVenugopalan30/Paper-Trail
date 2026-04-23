"""
Batch PDF processor with parallel execution and checkpoint management.

Processes multiple PDFs in parallel, extracts both native and OCR text,
tracks progress, and saves results per file.
"""

import gc
import itertools
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from tqdm import tqdm

from src.extraction.checkpoint import CheckpointManager
from src.extraction.native import extract_native
from src.extraction.ocr import GLMOCRClientError, extract_ocr
from src.extraction.pdf_converter import convert_pdf_to_images, get_page_count


class BatchProcessor:
    """
    Process multiple PDFs in batch with parallel workers and checkpoint support.
    """

    def __init__(
        self,
        output_dir: str,
        checkpoint_path: str,
        project_name: str,
        max_pages: int = 20,
        parallel_workers: int = 3,
        save_images: bool = True,
        ocr_dpi: int = 200,
        ocr_timeout: int = 300,
        method: str = "hybrid",
    ):
        """
        Initialize batch processor.

        Args:
            output_dir: Base output directory (e.g., data/processed/mozilla)
            checkpoint_path: Path to checkpoint JSON file
            project_name: Name of this processing project
            max_pages: Maximum pages per PDF (skip if exceeded)
            parallel_workers: Number of parallel workers (default: 3)
            save_images: Whether to save converted images
            ocr_dpi: DPI for image conversion
            ocr_timeout: Timeout for OCR requests in seconds
            method: Extraction method - 'native', 'ocr', or 'hybrid' (default)
        """
        self.output_dir = Path(output_dir)
        self.checkpoint = CheckpointManager(checkpoint_path, project_name)
        self.max_pages = max_pages
        self.parallel_workers = parallel_workers
        self.save_images = save_images
        self.ocr_dpi = ocr_dpi
        self.ocr_timeout = ocr_timeout
        self.method = method

        # Create output subdirectories
        self.results_dir = self.output_dir / "results"
        self.images_dir = self.output_dir / "images"

        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)

    def _process_single_pdf(
        self, pdf_path: str, limit_pages: Optional[int] = None
    ) -> Dict:
        """
        Process a single PDF file - extract both native and OCR.

        Args:
            pdf_path: Path to PDF file
            limit_pages: Limit processing to first N pages (for testing)

        Returns:
            Dictionary with extraction results for all pages
        """
        pdf_file = Path(pdf_path)
        filename = pdf_file.name
        pdf_name = pdf_file.stem

        result = {
            "source_pdf": str(pdf_path),
            "total_pages": 0,
            "pages": [],
            "summary": {
                "native_success_rate": "0/0",
                "ocr_success_rate": "0/0",
                "average_native_coverage": 0.0,
                "ocr_failed_pages": [],
                "native_failed_pages": [],
                "total_processing_time_seconds": 0.0,
                "extracted_at": datetime.now().isoformat(),
            },
        }

        try:
            # Check if already processed
            if self.checkpoint.is_processed(pdf_path):
                return {"status": "already_processed", "source_pdf": pdf_path}

            # Get page count
            try:
                total_pages = get_page_count(pdf_path)
                result["total_pages"] = total_pages
            except Exception as e:
                self.checkpoint.mark_file_failed(
                    pdf_path, f"Could not get page count: {e}", "page_count"
                )
                result["summary"]["error"] = f"Page count failed: {e}"
                return result

            # Check page limit
            if total_pages > self.max_pages:
                self.checkpoint.mark_file_skipped(
                    pdf_path,
                    f"{total_pages} pages (>{self.max_pages} limit)",
                    {"page_count": total_pages},
                )
                result["status"] = "skipped"
                result["summary"]["skip_reason"] = f"Too many pages: {total_pages}"
                return result

            # Convert PDF to images (skip for native-only method)
            image_paths = []
            if self.method != "native":
                pdf_images_dir = (
                    self.images_dir / pdf_name if self.save_images else None
                )

                if self.save_images and pdf_images_dir:
                    pdf_images_dir.mkdir(parents=True, exist_ok=True)

                try:
                    image_paths = convert_pdf_to_images(
                        pdf_path=str(pdf_file),
                        output_dir=str(pdf_images_dir) if pdf_images_dir else "/tmp",
                        dpi=self.ocr_dpi,
                    )
                except Exception as e:
                    self.checkpoint.mark_file_failed(
                        pdf_path, f"PDF conversion failed: {e}", "conversion"
                    )
                    result["summary"]["error"] = f"Conversion failed: {e}"
                    return result

            # Pre-extract native text ONCE before the page loop
            try:
                native_start = time.time()
                native_result = extract_native(str(pdf_file))
                native_pages = native_result.get("pages", [])
                native_time_total = (time.time() - native_start) * 1000
            except Exception as e:
                self.checkpoint.mark_file_failed(
                    pdf_path, f"Native extraction failed: {e}", "native"
                )
                result["summary"]["error"] = f"Native extraction failed: {e}"
                return result

            # Process each page
            native_success = 0
            ocr_success = 0
            total_coverage = 0.0
            ocr_failed_pages = []
            native_failed_pages = []

            start_time = time.time()
            last_processed_page = self.checkpoint.get_last_processed_page(pdf_path)

            # For native-only, drive the loop off native_pages; otherwise use image_paths
            if self.method == "native":
                page_count = len(native_pages)
                pages_to_process = (
                    min(page_count, limit_pages) if limit_pages else page_count
                )
                page_iter = enumerate([None] * pages_to_process, start=1)
            else:
                pages_to_process = (
                    min(len(image_paths), limit_pages)
                    if limit_pages
                    else len(image_paths)
                )
                page_iter = enumerate(image_paths[:pages_to_process], start=1)

            for page_idx, image_path in page_iter:
                # Skip already processed pages
                if page_idx <= last_processed_page:
                    continue

                page_result = {
                    "page_number": page_idx,
                    "native": {
                        "text": "",
                        "tables": [],
                        "coverage": 0.0,
                        "word_count": 0,
                        "char_count": 0,
                        "success": False,
                        "error": None,
                        "processing_time_ms": 0,
                    },
                    "ocr": {
                        "text": "",
                        "success": False,
                        "error": None,
                        "image_path": image_path
                        if (self.save_images and image_path)
                        else None,
                        "processing_time_ms": 0,
                    },
                }

                # Extract native text - use pre-extracted per-page data
                try:
                    if page_idx <= len(native_pages):
                        page_data = native_pages[page_idx - 1]
                        page_result["native"]["text"] = page_data.get("text", "")
                        page_result["native"]["tables"] = page_data.get("tables", [])
                        page_result["native"]["coverage"] = page_data.get(
                            "coverage", 0.0
                        )
                        page_result["native"]["word_count"] = page_data.get(
                            "word_count", 0
                        )
                        page_result["native"]["char_count"] = page_data.get(
                            "char_count", 0
                        )
                        page_result["native"]["success"] = True
                        # Distribute total time across pages (approximate)
                        page_result["native"]["processing_time_ms"] = (
                            int(native_time_total / len(native_pages))
                            if native_pages
                            else 0
                        )

                        native_success += 1
                        total_coverage += page_data.get("coverage", 0.0)
                    else:
                        page_result["native"]["error"] = (
                            f"Page {page_idx} not found in native extraction"
                        )
                        native_failed_pages.append(page_idx)

                except Exception as e:
                    page_result["native"]["error"] = str(e)
                    native_failed_pages.append(page_idx)

                # Extract OCR text (skip if native-only)
                if self.method != "native":
                    try:
                        ocr_start = time.time()
                        ocr_text = extract_ocr(
                            image_path, max_tokens=4096, timeout=self.ocr_timeout
                        )
                        ocr_time = (time.time() - ocr_start) * 1000

                        page_result["ocr"]["text"] = ocr_text
                        page_result["ocr"]["success"] = True
                        page_result["ocr"]["processing_time_ms"] = int(ocr_time)

                        ocr_success += 1

                    except Exception as e:
                        page_result["ocr"]["error"] = str(e)
                        ocr_failed_pages.append(page_idx)

                result["pages"].append(page_result)

                # Mark this page as processed
                self.checkpoint.mark_page_processed(
                    pdf_path, page_idx, pages_to_process
                )

            # Free large intermediate data structures
            del native_result
            del native_pages
            image_paths = []

            # Calculate summary
            total_time = time.time() - start_time
            result["summary"]["native_success_rate"] = (
                f"{native_success}/{pages_to_process}"
            )
            result["summary"]["ocr_success_rate"] = f"{ocr_success}/{pages_to_process}"
            result["summary"]["average_native_coverage"] = total_coverage
            result["summary"]["ocr_failed_pages"] = ocr_failed_pages
            result["summary"]["native_failed_pages"] = native_failed_pages
            result["summary"]["total_processing_time_seconds"] = round(total_time, 2)

            # Save results to file
            result_file = self.results_dir / f"{pdf_name}_results.json"
            with open(result_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)

            # Mark file as complete
            self.checkpoint.mark_file_complete(pdf_path)

            # Free full result dict before returning (data already on disk)
            lightweight = {
                "status": "complete",
                "source_pdf": str(pdf_path),
                "result_file": str(result_file),
                "total_pages": result["total_pages"],
                "summary": result["summary"],
            }
            del result
            gc.collect()
            return lightweight

        except Exception as e:
            self.checkpoint.mark_file_failed(pdf_path, str(e), "unknown")
            result["status"] = "error"
            result["summary"]["error"] = str(e)
            return result

    def process_batch(
        self,
        pdf_paths: List[str],
        limit: Optional[int] = None,
        limit_pages_per_pdf: Optional[int] = None,
    ) -> List[Dict]:
        """
        Process a batch of PDFs with parallel workers.

        Args:
            pdf_paths: List of PDF file paths
            limit: Limit to first N PDFs (for testing)
            limit_pages_per_pdf: Limit each PDF to first N pages

        Returns:
            List of results for each PDF
        """
        # Filter already processed files
        files_to_process = []
        for pdf_path in pdf_paths[:limit] if limit else pdf_paths:
            if not self.checkpoint.is_processed(pdf_path):
                files_to_process.append(pdf_path)

        if not files_to_process:
            print("All files already processed!")
            return []

        print(
            f"Processing {len(files_to_process)} PDFs with {self.parallel_workers} workers..."
        )
        print(f"Results will be saved to: {self.results_dir}")
        print(f"Images will be saved to: {self.images_dir}")
        print(f"Checkpoint: {self.checkpoint.checkpoint_path}")
        print()

        results = []
        completed_count = 0
        max_pending = self.parallel_workers * 2  # Sliding window size

        # Process with sliding window to bound memory usage
        with ThreadPoolExecutor(max_workers=self.parallel_workers) as executor:
            with tqdm(total=len(files_to_process), desc="Processing PDFs") as pbar:
                pending = {}
                file_iter = iter(files_to_process)

                # Seed initial batch
                for pdf_path in itertools.islice(file_iter, max_pending):
                    fut = executor.submit(
                        self._process_single_pdf, pdf_path, limit_pages_per_pdf
                    )
                    pending[fut] = pdf_path

                while pending:
                    done, _ = wait(pending, return_when=FIRST_COMPLETED)

                    for future in done:
                        pdf_path = pending.pop(future)
                        try:
                            result = future.result()
                            results.append(result)

                            status = result.get("status", "unknown")
                            filename = Path(pdf_path).name
                            pbar.set_postfix(
                                {"last": f"{filename[:20]}... ({status})"}
                            )
                        except Exception as e:
                            print(f"\nError processing {pdf_path}: {e}")
                            self.checkpoint.mark_file_failed(
                                pdf_path, str(e), "processing"
                            )

                        pbar.update(1)
                        completed_count += 1

                        # Submit next item to keep window full
                        next_pdf = next(file_iter, None)
                        if next_pdf is not None:
                            fut = executor.submit(
                                self._process_single_pdf,
                                next_pdf,
                                limit_pages_per_pdf,
                            )
                            pending[fut] = next_pdf

                    # Periodic garbage collection
                    if completed_count % 50 == 0:
                        gc.collect()

        # Print summary
        stats = self.checkpoint.get_stats()
        print("\n" + "=" * 60)
        print("BATCH PROCESSING COMPLETE")
        print("=" * 60)
        print(f"Processed:     {stats['processed']} files")
        print(f"Failed:        {stats['failed']} files")
        print(f"Skipped:       {stats['skipped']} files")
        print(f"In Progress:   {stats['in_progress']} files")
        print(f"\nResults saved to: {self.results_dir}")
        print(f"Checkpoint: {self.checkpoint.checkpoint_path}")

        return results

    def get_failed_files(self) -> Dict[str, str]:
        """Get list of failed files with error messages."""
        return {k: v["error"] for k, v in self.checkpoint.get_failed_files().items()}

    def get_skipped_files(self) -> Dict[str, str]:
        """Get list of skipped files with reasons."""
        return {k: v["reason"] for k, v in self.checkpoint.get_skipped_files().items()}
