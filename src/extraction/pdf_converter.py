"""
PDF to Image Converter Module with page counting support.

Converts PDF pages to high-resolution PNG images using pdf2image.
"""

import os
from pathlib import Path
from typing import List, Optional
from pdf2image import convert_from_path, convert_from_bytes
from pdf2image.exceptions import PDFPageCountError, PDFSyntaxError


def get_page_count(pdf_path: str) -> int:
    """
    Get the number of pages in a PDF file quickly without rendering.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Number of pages in the PDF
        
    Raises:
        FileNotFoundError: If PDF doesn't exist
        PDFPageCountError: If can't determine page count
        PDFSyntaxError: If PDF is corrupted
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    
    # Use pdfinfo (poppler) for fast page count without rendering
    from pdf2image.pdf2image import pdfinfo_from_path
    
    try:
        info = pdfinfo_from_path(pdf_path)
        return int(info.get("Pages", 0))
    except Exception as e:
        # Fallback: try to convert just page 0 to count total
        try:
            images = convert_from_path(pdf_path, first_page=1, last_page=1)
            # Get page count from the first image's info if available
            return len(convert_from_path(pdf_path, fmt="ppm"))  # ppm is faster
        except:
            raise PDFPageCountError(f"Could not determine page count: {e}")


def convert_pdf_to_images(
    pdf_path: str,
    output_dir: str,
    dpi: int = 200,
    first_page: Optional[int] = None,
    last_page: Optional[int] = None
) -> List[str]:
    """
    Convert PDF pages to high-resolution PNG images.
    
    Args:
        pdf_path: Path to the input PDF file
        output_dir: Directory where PNG images will be saved
        dpi: Resolution in dots per inch (default: 200)
        first_page: First page to convert (1-indexed, default: all)
        last_page: Last page to convert (1-indexed, default: all)
        
    Returns:
        List of file paths to the generated PNG images
        
    Raises:
        FileNotFoundError: If the PDF file does not exist
        PermissionError: If output directory cannot be created
        PDFSyntaxError: If the PDF file is corrupted or invalid
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    pdf_name = Path(pdf_path).stem
    output_files = []

    try:
        convert_kwargs = {
            "pdf_path": pdf_path,
            "dpi": dpi,
            "fmt": "png"
        }
        
        if first_page is not None:
            convert_kwargs["first_page"] = first_page
        if last_page is not None:
            convert_kwargs["last_page"] = last_page
            
        images = convert_from_path(**convert_kwargs)

        for page_num, image in enumerate(images, start=(first_page or 1)):
            output_filename = f"{pdf_name}_page_{page_num:04d}.png"
            output_file = output_path / output_filename
            image.save(str(output_file), "PNG")
            output_files.append(str(output_file))

    except PDFSyntaxError as e:
        raise PDFSyntaxError(f"PDF file is corrupted or invalid: {pdf_path}") from e
    except PDFPageCountError as e:
        raise PDFPageCountError(f"Could not determine page count for: {pdf_path}") from e

    return output_files


def convert_pdfs_to_images_batch(
    pdf_paths: List[str],
    output_dir: str,
    dpi: int = 200
) -> dict:
    """
    Batch convert multiple PDFs to images.
    
    Args:
        pdf_paths: List of paths to input PDF files
        output_dir: Base directory where PNG images will be saved
        dpi: Resolution in dots per inch (default: 200)
        
    Returns:
        Dictionary mapping PDF paths to their output image paths
    """
    results = {}

    for pdf_path in pdf_paths:
        pdf_name = Path(pdf_path).stem
        pdf_output_dir = os.path.join(output_dir, pdf_name)

        try:
            images = convert_pdf_to_images(pdf_path, pdf_output_dir, dpi)
            results[pdf_path] = images
        except Exception as e:
            results[pdf_path] = []

    return results
