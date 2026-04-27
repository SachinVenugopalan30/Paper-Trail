"""
Hybrid PDF Extraction Router Module.

Implements intelligent routing logic to choose between native PDF extraction
(pdfplumber) and OCR-based extraction (GLM-OCR) based on text coverage metrics.
"""

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from src.extraction.native import extract_native
from src.extraction.ocr import extract_ocr, GLMOCRClientError
from src.extraction.pdf_converter import convert_pdf_to_images, get_page_count


logger = logging.getLogger(__name__)


def calculate_native_coverage(native_result: Dict[str, Any]) -> float:
    """
    Calculate the text coverage from native extraction results.
    
    Args:
        native_result: Dictionary containing native extraction results
        
    Returns:
        Text coverage as a float between 0.0 and 1.0
    """
    if "overall_coverage" in native_result:
        return native_result.get("overall_coverage", 0.0) or 0.0
    return native_result.get("coverage", 0.0) or 0.0


def _perform_ocr_extraction(pdf_path: str, max_tokens: int = 4092, dpi: int = 200) -> str:
    """
    Perform OCR extraction on a PDF by converting pages to images.
    
    Args:
        pdf_path: Path to the PDF file
        max_tokens: Maximum tokens for OCR (default: 4096)
        dpi: Image resolution in DPI (default: 200). 
             Lower values (150-200) recommended for large documents to reduce token count.
    
    Returns:
        Combined extracted text from all pages
    
    Raises:
        FileNotFoundError: If the PDF file does not exist
        GLMOCRClientError: If OCR extraction fails
    """
    logger.info(f"Converting PDF to images for OCR: {pdf_path}")
    
    pdf_path_obj = Path(pdf_path)
    temp_dir = pdf_path_obj.parent / f"_temp_ocr_{pdf_path_obj.stem}"
    
    try:
        image_paths = convert_pdf_to_images(
            pdf_path=str(pdf_path_obj),
            output_dir=str(temp_dir),
            dpi=dpi
        )
        
        if not image_paths:
            raise GLMOCRClientError(f"Failed to convert PDF to images: {pdf_path}")
        
        logger.info(f"Converted {len(image_paths)} pages to images")
        
        all_text = []
        for i, image_path in enumerate(image_paths, 1):
            logger.debug(f"Running OCR on page {i}/{len(image_paths)}")
            page_text = extract_ocr(image_path, max_tokens=max_tokens)
            all_text.append(page_text)
        
        return "\n\n".join(all_text)
    
    finally:
        if temp_dir.exists():
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.debug(f"Cleaned up temporary directory: {temp_dir}")


def extract_both_methods(
    pdf_path: str,
    ocr_max_tokens: int = 4096,
    ocr_dpi: int = 200,
    ocr_timeout: int = 300
) -> Dict[str, Any]:
    """
    Extract text using BOTH native and OCR methods for comparison.
    
    This is used for the ground truth annotation tool to compare
    native vs OCR extraction quality side-by-side.
    
    Args:
        pdf_path: Path to the PDF file
        ocr_max_tokens: Maximum tokens for OCR (default: 4096)
        ocr_dpi: Image resolution for OCR (default: 200)
        ocr_timeout: OCR request timeout in seconds (default: 300)
        
    Returns:
        Dictionary containing both native and OCR results:
        {
            "source_pdf": str,
            "total_pages": int,
            "pages": [
                {
                    "page_number": int,
                    "native": {"text": str, "coverage": float, "success": bool, "error": str},
                    "ocr": {"text": str, "success": bool, "error": str, "image_path": str}
                }
            ],
            "summary": {...}
        }
    """
    pdf_file = Path(pdf_path)
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
            "extracted_at": datetime.now().isoformat()
        }
    }
    
    try:
        # Get page count
        from src.extraction.pdf_converter import get_page_count
        total_pages = get_page_count(pdf_path)
        result["total_pages"] = total_pages
        
        # Convert to images
        import tempfile
        with tempfile.TemporaryDirectory() as temp_dir:
            image_paths = convert_pdf_to_images(
                pdf_path=str(pdf_file),
                output_dir=temp_dir,
                dpi=ocr_dpi
            )
            
            native_success = 0
            ocr_success = 0
            total_coverage = 0.0
            ocr_failed_pages = []
            native_failed_pages = []
            
            start_time = time.time()
            
            # Extract native text once (for all pages)
            native_result = None
            native_pages = []
            
            for page_idx, image_path in enumerate(image_paths, start=1):
                page_result = {
                    "page_number": page_idx,
                    "native": {
                        "text": "",
                        "coverage": 0.0,
                        "success": False,
                        "error": None,
                        "processing_time_ms": 0
                    },
                    "ocr": {
                        "text": "",
                        "success": False,
                        "error": None,
                        "image_path": image_path,
                        "processing_time_ms": 0
                    }
                }
                
                # Native extraction (only once for first page, then split)
                try:
                    if page_idx == 1:
                        native_start = time.time()
                        native_result = extract_native(str(pdf_file))
                        native_time = (time.time() - native_start) * 1000
                        
                        # Split by form feed (page break)
                        full_text = native_result.get("text", "")
                        native_pages = full_text.split("\f") if "\f" in full_text else [full_text]
                        total_coverage = native_result.get("coverage", 0.0)
                    
                    # Get page-specific text
                    if page_idx <= len(native_pages):
                        page_result["native"]["text"] = native_pages[page_idx - 1]
                    page_result["native"]["coverage"] = total_coverage if page_idx == 1 else 0.0
                    page_result["native"]["success"] = True
                    page_result["native"]["processing_time_ms"] = int(native_time) if page_idx == 1 else 0
                    native_success += 1
                    
                except Exception as e:
                    page_result["native"]["error"] = str(e)
                    native_failed_pages.append(page_idx)
                
                # OCR extraction
                try:
                    ocr_start = time.time()
                    ocr_text = extract_ocr(image_path, max_tokens=ocr_max_tokens, timeout=ocr_timeout)
                    ocr_time = (time.time() - ocr_start) * 1000
                    
                    page_result["ocr"]["text"] = ocr_text
                    page_result["ocr"]["success"] = True
                    page_result["ocr"]["processing_time_ms"] = int(ocr_time)
                    ocr_success += 1
                    
                except Exception as e:
                    page_result["ocr"]["error"] = str(e)
                    ocr_failed_pages.append(page_idx)
                
                result["pages"].append(page_result)
            
            # Calculate summary
            total_time = time.time() - start_time
            result["summary"]["native_success_rate"] = f"{native_success}/{total_pages}"
            result["summary"]["ocr_success_rate"] = f"{ocr_success}/{total_pages}"
            result["summary"]["average_native_coverage"] = total_coverage
            result["summary"]["ocr_failed_pages"] = ocr_failed_pages
            result["summary"]["native_failed_pages"] = native_failed_pages
            result["summary"]["total_processing_time_seconds"] = round(total_time, 2)
            
    except Exception as e:
        result["summary"]["error"] = str(e)
    
    return result


def route_extraction(
    pdf_path: str,
    native_threshold: float = 0.8,
    ocr_max_tokens: int = 4096,
    ocr_dpi: int = 200
) -> Dict[str, Any]:
    """
    Route PDF extraction between native and OCR methods based on text coverage.
    
    This function implements hybrid routing logic:
    1. First attempts native extraction using pdfplumber
    2. Calculates text coverage from native results
    3. If coverage < native_threshold, falls back to OCR extraction
    4. Returns the best result with metadata about the extraction process
    
    Args:
        pdf_path: Path to the input PDF file
        native_threshold: Coverage threshold for native extraction (default: 0.8).
            If native coverage is below this value, OCR is used instead.
        ocr_max_tokens: Maximum tokens for OCR extraction (default: 4096)
        ocr_dpi: Image resolution for OCR in DPI (default: 200).
            Lower values (150-200) recommended for faster processing.
    
    Returns:
        Dictionary containing:
            - method: Extraction method used ('native' or 'ocr')
            - text: Extracted text content
            - native_coverage: Text coverage from native extraction (0.0 to 1.0)
            - time_taken: Total time taken for extraction in seconds
            - metadata: Additional metadata including:
                - native_result: Full native extraction result
                - ocr_used: Whether OCR was used
                - page_count: Number of pages in PDF (if available)
                - error: Error message if extraction failed
    
    Raises:
        FileNotFoundError: If the PDF file does not exist
        Exception: If both native and OCR extraction fail
    
    Example:
        >>> result = route_extraction("document.pdf", native_threshold=0.8)
        >>> print(f"Method: {result['method']}, Coverage: {result['native_coverage']:.2%}")
        Method: native, Coverage: 95.00%
    """
    from datetime import datetime
    
    start_time = time.time()
    pdf_path_obj = Path(pdf_path)
    
    if not pdf_path_obj.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    
    logger.info(f"Starting hybrid extraction for: {pdf_path}")
    
    result = {
        "method": "unknown",
        "text": "",
        "native_coverage": 0.0,
        "time_taken": 0.0,
        "metadata": {
            "native_result": None,
            "ocr_used": False,
            "page_count": None,
            "error": None
        }
    }
    
    try:
        logger.debug("Attempting native extraction...")
        native_start = time.time()
        native_result = extract_native(str(pdf_path_obj))
        native_time = time.time() - native_start
        
        native_coverage = calculate_native_coverage(native_result)
        result["native_coverage"] = native_coverage
        result["metadata"]["native_result"] = native_result
        result["metadata"]["page_count"] = native_result.get(
            "total_pages", len(native_result.get("pages", []))
        )

        def _native_text(nr):
            if nr.get("text"):
                return nr["text"]
            return "\n\n".join(p.get("text", "") for p in nr.get("pages", []))
        
        logger.info(
            f"Native extraction completed in {native_time:.2f}s "
            f"with coverage: {native_coverage:.2%}"
        )
        
        if native_coverage >= native_threshold:
            logger.info(
                f"Using native extraction (coverage {native_coverage:.2%} >= "
                f"threshold {native_threshold:.2%})"
            )
            result["method"] = "native"
            result["text"] = _native_text(native_result)
        else:
            logger.info(
                f"Native coverage {native_coverage:.2%} below threshold "
                f"{native_threshold:.2%}, falling back to OCR"
            )
            
            try:
                ocr_start = time.time()
                ocr_text = _perform_ocr_extraction(str(pdf_path_obj), ocr_max_tokens, ocr_dpi)
                ocr_time = time.time() - ocr_start
                
                result["method"] = "ocr"
                result["text"] = ocr_text
                result["metadata"]["ocr_used"] = True
                
                logger.info(
                    f"OCR extraction completed in {ocr_time:.2f}s, "
                    f"extracted {len(ocr_text)} characters"
                )
                
            except GLMOCRClientError as ocr_error:
                logger.warning(
                    f"OCR extraction failed: {ocr_error}. "
                    "Falling back to native extraction."
                )
                result["method"] = "native"
                result["text"] = _native_text(native_result)
                result["metadata"]["error"] = f"OCR failed: {ocr_error}"
    
    except Exception as e:
        logger.error(f"Native extraction failed: {e}")
        result["metadata"]["error"] = f"Native extraction failed: {e}"
        
        try:
            logger.info("Attempting OCR extraction as fallback...")
            ocr_start = time.time()
            ocr_text = _perform_ocr_extraction(str(pdf_path_obj), ocr_max_tokens, ocr_dpi)
            ocr_time = time.time() - ocr_start
            
            result["method"] = "ocr"
            result["text"] = ocr_text
            result["metadata"]["ocr_used"] = True
            
            logger.info(
                f"OCR fallback completed in {ocr_time:.2f}s, "
                f"extracted {len(ocr_text)} characters"
            )
            
        except GLMOCRClientError as ocr_error:
            logger.error(f"Both native and OCR extraction failed: {ocr_error}")
            result["metadata"]["error"] = (
                f"Both native and OCR extraction failed. "
                f"Native: {e}, OCR: {ocr_error}"
            )
            raise Exception(result["metadata"]["error"]) from ocr_error
    
    result["time_taken"] = time.time() - start_time
    
    logger.info(
        f"Hybrid extraction completed: method={result['method']}, "
        f"time={result['time_taken']:.2f}s, "
        f"coverage={result['native_coverage']:.2%}"
    )
    
    return result
