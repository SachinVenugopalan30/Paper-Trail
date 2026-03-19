"""
PDF Extraction Package.

Provides hybrid PDF extraction capabilities combining native text extraction
with OCR fallback for optimal text recovery.

Main exports:
    - extract_native: Native PDF text extraction using pdfplumber
    - extract_ocr: OCR-based text extraction using GLM-OCR
    - extract_both_methods: Extract with BOTH native and OCR for comparison
    - route_extraction: Intelligent routing between native and OCR methods
    - convert_pdf_to_images: Convert PDF pages to images for OCR processing
    - BatchProcessor: Parallel batch processing with checkpoint support
    - CheckpointManager: Resume capability for long-running batches
"""

from src.extraction.native import extract_native
from src.extraction.ocr import extract_ocr, GLMOCRClientError, GLMOCRServerError, GLMOCRConnectionError
from src.extraction.router import route_extraction, extract_both_methods
from src.extraction.pdf_converter import convert_pdf_to_images, convert_pdfs_to_images_batch, get_page_count
from src.extraction.checkpoint import CheckpointManager
from src.extraction.batch_processor import BatchProcessor

__all__ = [
    # Core extraction
    "extract_native",
    "extract_ocr",
    "extract_both_methods",
    "route_extraction",
    # Image conversion
    "convert_pdf_to_images",
    "convert_pdfs_to_images_batch",
    "get_page_count",
    # Batch processing
    "BatchProcessor",
    "CheckpointManager",
    # Exceptions
    "GLMOCRClientError",
    "GLMOCRServerError",
    "GLMOCRConnectionError",
]
