"""
Ground truth annotation tool with web interface.

This module provides a Streamlit-based web interface for:
- Viewing processed PDF results with saved images
- Comparing Native vs OCR extraction outputs
- Annotating which method performed better
- Editing and saving ground truth text
- Auto-calculating CER/WER metrics

Usage:
    streamlit run src/evaluation/ground_truth_tool.py

Features:
    - Load from processed results (data/processed/...)
    - Side-by-side image viewer and text comparison
    - One-click voting for better extraction method
    - Handle OCR failures gracefully
    - Text editor for corrections
    - Automatic metric calculation
    - JSON export of annotations
"""

import json
import base64
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime

# Add parent directory to path for imports when running via streamlit
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Note: Streamlit is imported inside functions to allow module import without UI


@dataclass
class Annotation:
    """
    Single annotation record for a PDF page.
    
    Attributes:
        pdf_path: Path to the source PDF file
        page_number: Page number (1-indexed)
        native_text: Text extracted using native method
        ocr_text: Text extracted using OCR method
        native_success: Whether native extraction succeeded
        ocr_success: Whether OCR extraction succeeded
        ocr_error: Error message if OCR failed
        selected_method: Which method was chosen ('native', 'ocr', 'ocr_failed')
        edited_text: User-edited ground truth text
        cer_native: CER for native vs edited text
        cer_ocr: CER for OCR vs edited text
        wer_native: WER for native vs edited text
        wer_ocr: WER for OCR vs edited text
        timestamp: When annotation was created
        notes: Optional user notes
    """
    pdf_path: str
    page_number: int
    native_text: str
    ocr_text: str
    native_success: bool = True
    ocr_success: bool = True
    ocr_error: Optional[str] = None
    selected_method: str = ""
    edited_text: str = ""
    cer_native: Optional[float] = None
    cer_ocr: Optional[float] = None
    wer_native: Optional[float] = None
    wer_ocr: Optional[float] = None
    timestamp: str = ""
    notes: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


class AnnotationStore:
    """
    Storage manager for ground truth annotations.
    
    Handles saving/loading annotations to/from JSON files with automatic
    CER/WER calculation when ground truth is edited.
    """
    
    def __init__(self, storage_path: str = "./ground_truth_annotations.json"):
        """
        Initialize annotation store.
        
        Args:
            storage_path: Path to JSON file for storing annotations
        """
        self.storage_path = Path(storage_path)
        self.annotations: Dict[str, Annotation] = {}  # Key: "pdf_path::page_number"
        self._load_annotations()
    
    def _get_key(self, pdf_path: str, page_number: int) -> str:
        """Generate unique key for annotation."""
        return f"{pdf_path}::{page_number}"
    
    def _load_annotations(self):
        """Load existing annotations from storage."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for key, ann_dict in data.items():
                        self.annotations[key] = Annotation(**ann_dict)
                print(f"Loaded {len(self.annotations)} existing annotations")
            except Exception as e:
                print(f"Could not load annotations: {e}")
    
    def save_annotation(self, annotation: Annotation) -> None:
        """
        Save annotation and auto-calculate metrics.
        
        Args:
            annotation: Annotation to save
        """
        from src.evaluation.metrics import calculate_cer, calculate_wer, text_similarity
        
        # Auto-calculate metrics only if extraction succeeded
        if annotation.native_success:
            annotation.cer_native = calculate_cer(annotation.native_text, annotation.edited_text)
            annotation.wer_native = calculate_wer(annotation.native_text, annotation.edited_text)
        else:
            annotation.cer_native = 1.0  # Max error
            annotation.wer_native = 1.0
        
        if annotation.ocr_success:
            annotation.cer_ocr = calculate_cer(annotation.ocr_text, annotation.edited_text)
            annotation.wer_ocr = calculate_wer(annotation.ocr_text, annotation.edited_text)
        else:
            annotation.cer_ocr = 1.0  # Max error
            annotation.wer_ocr = 1.0
        
        # Store annotation
        key = self._get_key(annotation.pdf_path, annotation.page_number)
        self.annotations[key] = annotation
        
        # Save to disk
        self._save_to_disk()
    
    def _save_to_disk(self):
        """Save all annotations to JSON file."""
        data = {key: asdict(ann) for key, ann in self.annotations.items()}
        with open(self.storage_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def get_annotation(self, pdf_path: str, page_number: int) -> Optional[Annotation]:
        """
        Retrieve annotation for specific PDF page.
        
        Args:
            pdf_path: Path to PDF file
            page_number: Page number
            
        Returns:
            Annotation if exists, None otherwise
        """
        key = self._get_key(pdf_path, page_number)
        return self.annotations.get(key)
    
    def get_all_annotations(self) -> List[Annotation]:
        """Get all stored annotations."""
        return list(self.annotations.values())
    
    def get_summary_stats(self) -> Dict[str, Any]:
        """
        Calculate summary statistics across all annotations.
        
        Returns:
            Dictionary with aggregated statistics
        """
        if not self.annotations:
            return {}
        
        anns = list(self.annotations.values())
        native_wins = sum(1 for a in anns if a.selected_method == 'native')
        ocr_wins = sum(1 for a in anns if a.selected_method == 'ocr')
        ocr_failed = sum(1 for a in anns if a.selected_method == 'ocr_failed')
        
        # Average metrics (only for successful extractions)
        native_cers = [a.cer_native for a in anns if a.cer_native is not None and a.native_success]
        ocr_cers = [a.cer_ocr for a in anns if a.cer_ocr is not None and a.ocr_success]
        
        avg_cer_native = sum(native_cers) / len(native_cers) if native_cers else 0.0
        avg_cer_ocr = sum(ocr_cers) / len(ocr_cers) if ocr_cers else 0.0
        
        return {
            'total_annotations': len(anns),
            'native_selections': native_wins,
            'ocr_selections': ocr_wins,
            'ocr_failed_selections': ocr_failed,
            'avg_cer_native': avg_cer_native,
            'avg_cer_ocr': avg_cer_ocr,
        }
    
    def export_for_training(self, output_path: str):
        """
        Export annotations in training-ready format.
        
        Args:
            output_path: Path to save exported JSON
        """
        training_data = []
        for ann in self.annotations.values():
            training_data.append({
                'pdf_path': ann.pdf_path,
                'page_number': ann.page_number,
                'ground_truth': ann.edited_text,
                'native_raw': ann.native_text,
                'ocr_raw': ann.ocr_text,
                'native_success': ann.native_success,
                'ocr_success': ann.ocr_success,
                'ocr_error': ann.ocr_error,
                'metrics': {
                    'cer_native': ann.cer_native,
                    'cer_ocr': ann.cer_ocr,
                    'wer_native': ann.wer_native,
                    'wer_ocr': ann.wer_ocr,
                },
                'selected_method': ann.selected_method,
            })
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(training_data, f, indent=2, ensure_ascii=False)


class ProcessedResultsLoader:
    """
    Loader for processed extraction results.
    
    Reads the JSON files created by batch_processor.py from multiple directories
    and provides easy access to images and extraction results.
    """
    
    def __init__(self, results_dirs: Optional[List[str]] = None):
        """
        Initialize loader.
        
        Args:
            results_dirs: List of directories containing *_results.json files.
                         If None, scans data/processed/*/*/results/
        """
        if results_dirs is None:
            # Auto-discover all batch/type result directories
            self.results_dirs = self._discover_result_directories()
        else:
            self.results_dirs = [Path(d) for d in results_dirs]
        
        self.results: List[Dict] = []
        self._load_all_results()
    
    def _discover_result_directories(self) -> List[Path]:
        """Auto-discover all result directories in data/processed/."""
        discovered = []
        base_dir = Path("data/processed")
        
        if base_dir.exists():
            # Look for */*/results/ pattern (batch/type/results)
            for batch_dir in base_dir.iterdir():
                if batch_dir.is_dir():
                    for type_dir in batch_dir.iterdir():
                        if type_dir.is_dir():
                            results_dir = type_dir / "results"
                            if results_dir.exists():
                                discovered.append(results_dir)
        
        # Also check legacy mozilla directory
        legacy_dir = Path("data/processed/mozilla/results")
        if legacy_dir.exists():
            discovered.append(legacy_dir)
        
        if not discovered:
            print(f"Warning: No result directories found in {base_dir}")
        else:
            print(f"Discovered {len(discovered)} result directories:")
            for d in discovered:
                print(f"  - {d}")
        
        return discovered
    
    def _load_all_results(self):
        """Load all result files from all directories."""
        for results_dir in self.results_dirs:
            if not results_dir.exists():
                print(f"Warning: Results directory not found: {results_dir}")
                continue
            
            result_files = sorted(results_dir.glob("*_results.json"))
            for result_file in result_files:
                try:
                    with open(result_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        # Add metadata about source directory
                        data['_source_dir'] = str(results_dir)
                        self.results.append(data)
                except Exception as e:
                    print(f"Error loading {result_file}: {e}")
        
        print(f"Loaded {len(self.results)} processed PDFs total")
    
    def get_batch_type_counts(self) -> Dict[str, int]:
        """Get counts of PDFs by batch/type."""
        counts = {}
        for result in self.results:
            source = Path(result.get('source_pdf', ''))
            # Extract batch and type from path
            parts = source.parts
            if 'batch' in str(source):
                for i, part in enumerate(parts):
                    if 'batch' in part:
                        batch = part
                        doc_type = parts[i + 1] if i + 1 < len(parts) else 'unknown'
                        key = f"{batch}/{doc_type}"
                        counts[key] = counts.get(key, 0) + 1
                        break
            elif 'mozilla' in str(source):
                counts['mozilla'] = counts.get('mozilla', 0) + 1
        return counts
    
    def get_all_pdfs(self) -> List[Dict]:
        """Get all loaded PDF results."""
        return self.results
    
    def get_pdf_by_name(self, pdf_name: str) -> Optional[Dict]:
        """
        Get specific PDF by name (without extension).
        
        Args:
            pdf_name: PDF filename without .pdf extension
            
        Returns:
            PDF result data or None
        """
        for result in self.results:
            source = Path(result.get('source_pdf', ''))
            if source.stem == pdf_name or source.name == pdf_name:
                return result
        return None
    
    def get_page_data(self, pdf_name: str, page_number: int) -> Optional[Dict]:
        """
        Get specific page data from a PDF.
        
        Args:
            pdf_name: PDF filename
            page_number: Page number (1-indexed)
            
        Returns:
            Page data dictionary or None
        """
        pdf_data = self.get_pdf_by_name(pdf_name)
        if not pdf_data:
            return None
        
        pages = pdf_data.get('pages', [])
        for page in pages:
            if page.get('page_number') == page_number:
                return page
        return None
    
    def get_image_path(self, pdf_name: str, page_number: int) -> Optional[str]:
        """
        Get path to saved image for a specific page.
        
        Args:
            pdf_name: PDF filename
            page_number: Page number
            
        Returns:
            Path to image file or None
        """
        page_data = self.get_page_data(pdf_name, page_number)
        if not page_data:
            return None
        
        ocr_data = page_data.get('ocr', {})
        return ocr_data.get('image_path')


def encode_image_to_base64(image_path: str) -> Optional[str]:
    """
    Encode image file to base64 for display.
    
    Args:
        image_path: Path to image file
        
    Returns:
        Base64 encoded image string or None
    """
    try:
        with open(image_path, 'rb') as f:
            img_bytes = f.read()
        b64 = base64.b64encode(img_bytes).decode('utf-8')
        return f"data:image/png;base64,{b64}"
    except Exception as e:
        print(f"Error encoding image {image_path}: {e}")
        return None


def run_streamlit_app():
    """
    Launch the Streamlit web interface for ground truth annotation.
    
    This function should be called when running:
        streamlit run src/evaluation/ground_truth_tool.py
    """
    import streamlit as st
    
    st.set_page_config(
        page_title="PDF Extraction Ground Truth Tool",
        page_icon="📄",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Initialize storage and loader
    if 'store' not in st.session_state:
        # Use a specific storage path in the project directory
        storage_path = Path("data/processed/ground_truth_annotations.json")
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        st.session_state.store = AnnotationStore(str(storage_path))
        st.sidebar.info(f"💾 Annotations saved to:\n`{storage_path}`")
    
    # Show current annotation count in sidebar
    if st.session_state.store.annotations:
        st.sidebar.success(f"✅ {len(st.session_state.store.annotations)} annotations saved")
    else:
        st.sidebar.warning("⚠️ No annotations saved yet")
    
    if 'loader' not in st.session_state:
        # Auto-discover all result directories
        st.session_state.loader = ProcessedResultsLoader()
    
    if 'current_pdf_idx' not in st.session_state:
        st.session_state.current_pdf_idx = 0
    
    if 'current_page_idx' not in st.session_state:
        st.session_state.current_page_idx = 0
    
    # Sidebar - Configuration
    st.sidebar.header("⚙️ Configuration")
    
    # Show discovered directories
    st.sidebar.subheader("📁 Result Directories")
    batch_counts = st.session_state.loader.get_batch_type_counts()
    for batch_type, count in sorted(batch_counts.items()):
        st.sidebar.text(f"{batch_type}: {count} PDFs")
    
    # Get all processed PDFs
    all_pdfs = st.session_state.loader.get_all_pdfs()
    
    if not all_pdfs:
        st.error("❌ No processed PDFs found!")
        st.info("👈 Check the Results Directory path in the sidebar")
        st.markdown("""
        ### Expected Directory Structure:
        ```
        data/processed/mozilla/
        ├── results/
        │   ├── MOZILLA-1000230-0_results.json
        │   ├── MOZILLA-1001080-0_results.json
        │   └── ...
        └── images/
            ├── MOZILLA-1000230-0/
            │   ├── MOZILLA-1000230-0_page_0001.png
            │   └── ...
            └── ...
        ```
        
        Run batch processing first:
        ```bash
        python3 -m src.cli extract-batch data/batch3/MOZILLA \
          --limit 10 --output-dir data/processed/mozilla
        ```
        """)
        return
    
    # Sidebar - PDF Selection
    st.sidebar.header("📁 Document Selection")
    
    # Track current PDF to detect changes
    if 'current_pdf_name' not in st.session_state:
        st.session_state.current_pdf_name = ""
    
    # PDF selector
    pdf_names = [Path(pdf.get('source_pdf', 'unknown')).name for pdf in all_pdfs]
    selected_pdf_name = st.sidebar.selectbox(
        "Select PDF",
        options=pdf_names,
        index=st.session_state.current_pdf_idx
    )
    
    # Update index
    st.session_state.current_pdf_idx = pdf_names.index(selected_pdf_name)
    current_pdf = all_pdfs[st.session_state.current_pdf_idx]
    
    # If PDF changed, clear old session state for previous PDF
    if selected_pdf_name != st.session_state.current_pdf_name:
        # Clear all session state keys related to the old PDF
        keys_to_clear = [k for k in st.session_state.keys() if isinstance(k, str) and k.startswith(('selected_method_', 'ground_truth_text_', 'ground_truth_editor_', 'annotation_notes_'))]
        for key in keys_to_clear:
            if key in st.session_state:
                del st.session_state[key]
        
        # Reset to first page
        st.session_state.current_page_idx = 0
        
        # Update current PDF name
        st.session_state.current_pdf_name = selected_pdf_name
        
        # Rerun to refresh with cleared state
        st.rerun()
    
    # Page selector
    total_pages = current_pdf.get('total_pages', 1)
    page_numbers = list(range(1, total_pages + 1))
    
    # Track current page to detect changes
    if 'current_page_num' not in st.session_state:
        st.session_state.current_page_num = 1
    
    selected_page = st.sidebar.selectbox(
        "Page",
        options=page_numbers,
        index=min(st.session_state.current_page_idx, len(page_numbers) - 1)
    )
    
    st.session_state.current_page_idx = page_numbers.index(selected_page)
    
    # If page changed via selectbox (not via prev/next buttons), clear state
    if selected_page != st.session_state.current_page_num:
        # Clear all session state keys for the old page of current PDF
        old_page = st.session_state.current_page_num
        keys_to_clear = [k for k in st.session_state.keys() if isinstance(k, str) and 
                        (k.startswith(f'selected_method_{selected_pdf_name}_{old_page}') or 
                         k.startswith(f'ground_truth_text_{selected_pdf_name}_{old_page}') or
                         k.startswith(f'ground_truth_editor_{selected_pdf_name}_{old_page}') or
                         k.startswith(f'annotation_notes_{selected_pdf_name}_{old_page}'))]
        for key in keys_to_clear:
            if key in st.session_state:
                del st.session_state[key]
        
        # Update current page
        st.session_state.current_page_num = selected_page
    
    # Show summary info
    summary = current_pdf.get('summary', {})
    st.sidebar.info(f"📄 Pages: {total_pages}")
    st.sidebar.info(f"📝 Native: {summary.get('native_success_rate', 'N/A')}")
    st.sidebar.info(f"🔍 OCR: {summary.get('ocr_success_rate', 'N/A')}")
    
    # Sidebar - Stats
    st.sidebar.header("📊 Statistics")
    stats = st.session_state.store.get_summary_stats()
    if stats:
        st.sidebar.metric("Total Annotations", stats.get('total_annotations', 0))
        col1, col2, col3 = st.sidebar.columns(3)
        col1.metric("Native", stats.get('native_selections', 0))
        col2.metric("OCR", stats.get('ocr_selections', 0))
        col3.metric("Failed", stats.get('ocr_failed_selections', 0))
        
        if stats.get('avg_cer_native') is not None:
            st.sidebar.metric("Avg CER (Native)", f"{stats['avg_cer_native']:.2%}")
        if stats.get('avg_cer_ocr') is not None:
            st.sidebar.metric("Avg CER (OCR)", f"{stats['avg_cer_ocr']:.2%}")
    
    # Navigation buttons
    st.sidebar.header("🔄 Navigation")
    nav_col1, nav_col2 = st.sidebar.columns(2)
    
    with nav_col1:
        if st.button("⬅️ Prev PDF", width='stretch'):
            if st.session_state.current_pdf_idx > 0:
                st.session_state.current_pdf_idx -= 1
                st.session_state.current_page_idx = 0
                st.rerun()
    
    with nav_col2:
        if st.button("Next PDF ➡️", width='stretch'):
            if st.session_state.current_pdf_idx < len(all_pdfs) - 1:
                st.session_state.current_pdf_idx += 1
                st.session_state.current_page_idx = 0
                st.rerun()
    
    # Main content
    st.title("📄 PDF Extraction Ground Truth Annotation Tool")
    st.subheader(f"{selected_pdf_name} - Page {selected_page}")
    
    # Get page data
    page_data = st.session_state.loader.get_page_data(selected_pdf_name, selected_page)
    
    if not page_data:
        st.error(f"❌ No data found for page {selected_page}")
        return
    
    # Get existing annotation
    pdf_path = current_pdf.get('source_pdf', '')
    existing = st.session_state.store.get_annotation(pdf_path, selected_page)
    
    # Three-column layout
    col_img, col_native, col_ocr = st.columns([1.2, 1, 1])
    
    # Column 1: Image
    with col_img:
        st.markdown("### 📷 Original Page")
        image_path = st.session_state.loader.get_image_path(selected_pdf_name, selected_page)
        
        if image_path and Path(image_path).exists():
            img_data = encode_image_to_base64(image_path)
            if img_data:
                st.image(img_data, width='stretch')
                st.caption(f"Image: {Path(image_path).name}")
            else:
                st.error("Could not load image")
        else:
            st.warning(f"⚠️ Image not found:\n{image_path}")
            st.info("Images should be in: data/processed/mozilla/images/")
    
    # Column 2: Native Extraction
    with col_native:
        st.markdown("### 📝 Native Extraction")
        native_data = page_data.get('native', {})
        native_text = native_data.get('text', '')
        native_success = native_data.get('success', False)
        native_coverage = native_data.get('coverage', 0)
        
        # Create unique key for this PDF/page
        native_key = f"native_text_{selected_pdf_name}_{selected_page}"
        
        if native_success:
            st.success(f"✓ Success (Coverage: {native_coverage:.1%})")
            st.text_area(
                "Extracted Text",
                value=native_text,
                height=250,
                key=native_key,
                disabled=True
            )
            st.caption(f"{len(native_text)} characters")
        else:
            st.error("✗ Native extraction failed")
            error_key = f"native_error_{selected_pdf_name}_{selected_page}"
            st.text_area(
                "Error",
                value=native_data.get('error', 'Unknown error'),
                height=100,
                key=error_key,
                disabled=True
            )
    
    # Column 3: OCR Extraction
    with col_ocr:
        st.markdown("### 🔍 OCR Extraction")
        ocr_data = page_data.get('ocr', {})
        ocr_text = ocr_data.get('text', '')
        ocr_success = ocr_data.get('success', False)
        ocr_error = ocr_data.get('error', '')
        
        # Create unique key for this PDF/page
        ocr_key = f"ocr_text_{selected_pdf_name}_{selected_page}"
        
        if ocr_success:
            st.success("✓ OCR Success")
            st.text_area(
                "OCR Text",
                value=ocr_text,
                height=250,
                key=ocr_key,
                disabled=True
            )
            st.caption(f"{len(ocr_text)} characters")
        else:
            st.error(f"✗ OCR Failed: {ocr_error}")
            st.info("Select 'OCR Failed' in the voting section below")
    
    # Initialize selected_method in session state if not exists
    # Use a key based on current PDF and page
    method_key = f"selected_method_{selected_pdf_name}_{selected_page}"
    
    if method_key not in st.session_state:
        # Initialize from existing annotation or auto-select
        if existing and existing.selected_method:
            st.session_state[method_key] = existing.selected_method
        else:
            # Auto-select best option
            if not ocr_success:
                st.session_state[method_key] = "native" if native_success else ""
            elif not native_success:
                st.session_state[method_key] = "ocr"
            else:
                st.session_state[method_key] = "native"  # Default
    
    # Voting section
    st.divider()
    st.subheader("🎯 Quality Assessment")
    
    vote_col1, vote_col2, vote_col3 = st.columns(3)
    
    with vote_col1:
        native_btn = st.button(
            "✅ Native Better",
            type="primary" if st.session_state[method_key] == "native" else "secondary",
            width='stretch',
            disabled=not native_success,
            key=f"native_btn_{selected_pdf_name}_{selected_page}"
        )
    
    with vote_col2:
        ocr_btn = st.button(
            "🔍 OCR Better",
            type="primary" if st.session_state[method_key] == "ocr" else "secondary",
            width='stretch',
            disabled=not ocr_success,
            key=f"ocr_btn_{selected_pdf_name}_{selected_page}"
        )
    
    with vote_col3:
        ocr_failed_btn = st.button(
            "⚠️ OCR Failed",
            type="primary" if st.session_state[method_key] == "ocr_failed" else "secondary",
            width='stretch',
            disabled=ocr_success,  # Only enable if OCR actually failed
            key=f"ocr_fail_btn_{selected_pdf_name}_{selected_page}"
        )
    
    # Initialize ground truth text in session state
    text_key = f"ground_truth_text_{selected_pdf_name}_{selected_page}"
    
    if text_key not in st.session_state:
        # Initialize from existing annotation or auto-select
        if existing and existing.edited_text and existing.pdf_path == pdf_path and existing.page_number == selected_page:
            st.session_state[text_key] = existing.edited_text
        else:
            # Default to native text initially
            st.session_state[text_key] = native_text if native_success else ""
    
    # Update selection and text based on button clicks
    text_updated = False
    if native_btn:
        st.session_state[method_key] = "native"
        if native_success:
            st.session_state[text_key] = native_text
            text_updated = True
        st.rerun()
    elif ocr_btn:
        st.session_state[method_key] = "ocr"
        if ocr_success:
            st.session_state[text_key] = ocr_text
            text_updated = True
        st.rerun()
    elif ocr_failed_btn:
        st.session_state[method_key] = "ocr_failed"
        if native_success:
            st.session_state[text_key] = native_text
            text_updated = True
        st.rerun()
    
    selected_method = st.session_state[method_key]
    
    # Show selection
    if selected_method:
        method_emoji = {"native": "✅", "ocr": "🔍", "ocr_failed": "⚠️"}
        st.info(f"Selected: {method_emoji.get(selected_method, '')} {selected_method.replace('_', ' ').title()}")
    
    # Ground truth editing
    st.divider()
    st.subheader("✏️ Ground Truth Editor")
    
    # Create a unique key for the text area that changes when method changes
    # This forces Streamlit to re-render with the new value
    editor_key = f"ground_truth_editor_{selected_pdf_name}_{selected_page}_{selected_method}"
    
    edited_text = st.text_area(
        "Edit text to create perfect ground truth (or confirm selected extraction):",
        value=st.session_state[text_key],
        height=250,
        key=editor_key
    )
    
    # Notes
    notes_key = f"annotation_notes_{selected_pdf_name}_{selected_page}"
    notes_default = ""
    if existing and existing.pdf_path == pdf_path and existing.page_number == selected_page:
        notes_default = existing.notes
    
    notes = st.text_input(
        "Notes (optional):",
        value=notes_default,
        key=notes_key
    )
    
    # Save button
    save_col1, save_col2 = st.columns([1, 3])
    
    with save_col1:
        save_btn = st.button("💾 Save Ground Truth", type="primary", width='stretch')
    
    with save_col2:
        if save_btn:
            try:
                # Ensure edited_text is never None
                edited_text_safe = edited_text if edited_text is not None else ""
                
                # Debug info
                print(f"DEBUG: Saving annotation for {pdf_path}, page {selected_page}")
                print(f"DEBUG: Selected method: {selected_method}")
                print(f"DEBUG: Text length: {len(edited_text_safe)}")
                
                annotation = Annotation(
                    pdf_path=pdf_path,
                    page_number=selected_page,
                    native_text=native_text,
                    ocr_text=ocr_text,
                    native_success=native_success,
                    ocr_success=ocr_success,
                    ocr_error=ocr_error,
                    selected_method=selected_method,
                    edited_text=edited_text_safe,
                    notes=notes
                )
                
                # Save the annotation
                st.session_state.store.save_annotation(annotation)
                
                # Show success with file location
                storage_file = st.session_state.store.storage_path
                st.success(f"✅ Annotation saved successfully!")
                st.info(f"💾 Location: `{storage_file}`")
                st.info(f"📊 Total annotations: {len(st.session_state.store.annotations)}")
                
                # Show metrics
                metrics_col1, metrics_col2 = st.columns(2)
                with metrics_col1:
                    st.json({
                        "CER (Native)": annotation.cer_native,
                        "WER (Native)": annotation.wer_native,
                    })
                with metrics_col2:
                    st.json({
                        "CER (OCR)": annotation.cer_ocr,
                        "WER (OCR)": annotation.wer_ocr,
                    })
                    
            except Exception as e:
                st.error(f"❌ Error saving annotation: {e}")
                import traceback
                st.code(traceback.format_exc())
                st.info("Please check the error above and try again.")
    
    # Export section
    st.divider()
    st.subheader("📤 Export Annotations")
    
    export_col1, export_col2 = st.columns(2)
    
    with export_col1:
        try:
            if st.button("Export for Training", width='stretch'):
                # Check if we have any annotations
                all_annotations = st.session_state.store.get_all_annotations()
                
                if not all_annotations:
                    st.warning("⚠️ No annotations to export! Please save some annotations first.")
                    st.info("To save an annotation:\n1. Select a PDF and page\n2. Click 'Native Better' or 'OCR Better'\n3. Click '💾 Save Ground Truth'")
                else:
                    output_path = "training_data.json"
                    st.session_state.store.export_for_training(output_path)
                    
                    # Get absolute path for clarity
                    abs_path = Path(output_path).absolute()
                    
                    st.success(f"✅ Training data exported!")
                    st.info(f"📁 File: `{abs_path}`")
                    st.info(f"📝 Total annotations: {len(all_annotations)}")
                    
                    # Show preview
                    try:
                        with open(output_path, 'r') as f:
                            preview = json.load(f)[:3]  # First 3 items
                            st.json(preview)
                    except Exception as e:
                        st.error(f"Error reading exported file: {e}")
        except Exception as e:
            st.error(f"❌ Export error: {e}")
            import traceback
            st.code(traceback.format_exc())
    
    with export_col2:
        try:
            if st.button("View All Annotations", width='stretch'):
                all_anns = st.session_state.store.get_all_annotations()
                if all_anns:
                    st.json([asdict(a) for a in all_anns[-5:]])  # Show last 5
                else:
                    st.info("No annotations saved yet.")
        except Exception as e:
            st.error(f"❌ View error: {e}")


if __name__ == "__main__":
    # Check if running as streamlit app
    try:
        import streamlit as st
        # If we can import streamlit, we're likely running as `streamlit run`
        run_streamlit_app()
    except ImportError:
        print("Streamlit not installed. Run: pip install streamlit")
        print("Then: streamlit run src/evaluation/ground_truth_tool.py")
