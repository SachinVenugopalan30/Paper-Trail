"""Native PDF Text Extraction Module.

Extracts text, tables, and metadata from PDFs using pdfplumber.
Returns per-page data with individual coverage calculation.
"""

from typing import Any, Dict, List
from pathlib import Path
import pdfplumber


def extract_native(pdf_path: str) -> Dict[str, Any]:
    """
    Extract text, tables, and metadata PER PAGE from a PDF file.

    Uses pdfplumber for native text extraction with layout preservation.
    Calculates per-page text coverage and returns data structured by page.

    Args:
        pdf_path: Path to the input PDF file

    Returns:
        Dictionary containing:
            - pages: List of page dictionaries, each containing:
                - text: Extracted text content for this page
                - tables: List of tables on this page
                - coverage: Text coverage percentage for this page (0.0 to 1.0)
                - word_count: Number of words on this page
                - char_count: Number of characters on this page
            - metadata: PDF metadata dictionary
            - total_pages: Total number of pages
            - overall_coverage: Average coverage across all pages

    Raises:
        FileNotFoundError: If the PDF file does not exist
        Exception: For other extraction errors
    """
    if not Path(pdf_path).exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    try:
        with pdfplumber.open(pdf_path) as pdf:
            metadata = pdf.metadata or {}

            pages = []
            total_coverage = 0.0

            for page_idx, page in enumerate(pdf.pages, start=1):
                # Extract text
                page_text = page.extract_text() or ""
                word_count = len(page_text.split())
                char_count = len(page_text)

                # Extract tables for this page
                page_tables = []
                tables = page.extract_tables()
                for table in tables:
                    if table and any(row for row in table):
                        page_tables.append(table)

                # Calculate per-page coverage
                page_coverage = _calculate_page_coverage(
                    page, char_count
                )
                total_coverage += page_coverage

                pages.append({
                    "text": page_text,
                    "tables": page_tables,
                    "coverage": page_coverage,
                    "word_count": word_count,
                    "char_count": char_count
                })

            total_pages = len(pdf.pages)
            overall_coverage = total_coverage / total_pages if total_pages > 0 else 0.0

            return {
                "pages": pages,
                "metadata": metadata,
                "total_pages": total_pages,
                "overall_coverage": round(overall_coverage, 4)
            }

    except Exception as e:
        raise Exception(f"Error extracting text from {pdf_path}: {str(e)}") from e


def _calculate_page_coverage(page, char_count: int) -> float:
    """
    Calculate text coverage percentage for a single page.

    Args:
        page: pdfplumber Page object
        char_count: Number of characters on the page

    Returns:
        Text coverage as a float between 0.0 and 1.0
    """
    width = page.width
    height = page.height

    if not width or not height:
        return 0.0

    page_area = width * height

    if page_area == 0:
        return 0.0

    # Estimate character area (roughly 20 square units per char)
    estimated_char_area = char_count * 20
    coverage = min(estimated_char_area / page_area, 1.0)

    return round(coverage, 4)


def extract_tables_from_pdf(pdf_path: str) -> List[List[List[str]]]:
    """
    Extract all tables from a PDF file.

    Args:
        pdf_path: Path to the input PDF file

    Returns:
        List of tables, where each table is a list of rows,
        and each row is a list of cell values
    """
    tables = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_tables = page.extract_tables()
            for table in page_tables:
                if table and any(row for row in table):
                    tables.append(table)

    return tables


def extract_native_legacy(pdf_path: str) -> Dict[str, Any]:
    """
    Legacy function for backward compatibility.
    
    Returns combined text across all pages.
    
    Args:
        pdf_path: Path to the input PDF file
        
    Returns:
        Dictionary with combined text, tables, coverage, and metadata
    """
    result = extract_native(pdf_path)
    
    # Combine all page texts
    combined_text = "\n\n".join([page["text"] for page in result["pages"]])
    combined_tables = []
    for page in result["pages"]:
        combined_tables.extend(page["tables"])
    
    return {
        "text": combined_text,
        "tables": combined_tables,
        "coverage": result["overall_coverage"],
        "metadata": result["metadata"],
        "total_pages": result["total_pages"]
    }
