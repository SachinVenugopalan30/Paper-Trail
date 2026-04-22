"""RAG Indexer: reads result JSONs, chunks text, populates ChromaDB and BM25."""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional

import yaml

logger = logging.getLogger(__name__)

# Default config path
_DEFAULT_CONFIG = Path(__file__).parent.parent.parent / "config" / "rag.yaml"


def _load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    p = Path(config_path) if config_path else _DEFAULT_CONFIG
    if not p.exists():
        return {}
    with open(p, "r") as f:
        return yaml.safe_load(f) or {}


@dataclass
class TextChunk:
    chunk_id: str          # "{doc_stem}_page_{n}_chunk_{m}"
    text: str
    document_id: str       # e.g. "GHOSTSCRIPT-687111-2"
    page_number: int
    source_file: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class RAGIndexer:
    """Build and manage the RAG index from processed result JSON files."""

    def __init__(self, config_path: Optional[str] = None):
        cfg = _load_config(config_path)
        idx_cfg = cfg.get("indexing", {})
        vec_cfg = cfg.get("vector", {})
        bm_cfg = cfg.get("bm25", {})

        self.chunk_size: int = idx_cfg.get("chunk_size", 800)
        self.chunk_overlap: int = idx_cfg.get("chunk_overlap", 150)
        self.min_chunk_length: int = idx_cfg.get("min_chunk_length", 50)
        self.text_preference: str = idx_cfg.get("text_preference", "longer")

        self.vector_collection: str = vec_cfg.get("collection_name", "pdf_chunks")
        self.embedding_model: str = vec_cfg.get("embedding_model", "all-MiniLM-L6-v2")
        self.persist_dir: str = vec_cfg.get("persist_directory", "data/rag/chromadb")

        self.bm25_path: str = bm_cfg.get("persist_path", "data/rag/bm25_index.json")
        self.bm25_k1: float = bm_cfg.get("k1", 1.5)
        self.bm25_b: float = bm_cfg.get("b", 0.75)

        # Lazy-loaded stores
        self._vector_store = None
        self._bm25_index = None

    # ------------------------------------------------------------------
    # Stores (lazy init)
    # ------------------------------------------------------------------

    def _get_vector_store(self):
        if self._vector_store is None:
            from src.rag.vector_store import VectorStore
            self._vector_store = VectorStore(
                collection_name=self.vector_collection,
                embedding_model=self.embedding_model,
                persist_directory=self.persist_dir,
            )
        return self._vector_store

    def _get_bm25(self):
        if self._bm25_index is None:
            from src.rag.bm25 import BM25Index
            self._bm25_index = BM25Index(k1=self.bm25_k1, b=self.bm25_b)
        return self._bm25_index

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover_result_files(self) -> List[Path]:
        """Glob all *_results.json files under data/processed/."""
        project_root = Path(__file__).parent.parent.parent
        pattern = "data/processed/*/results/*_results.json"
        files = sorted(project_root.glob(pattern))
        logger.info(f"Discovered {len(files)} result files")
        return files

    # ------------------------------------------------------------------
    # Chunking
    # ------------------------------------------------------------------

    def _pick_text(self, page: Dict[str, Any]) -> str:
        """Pick the best text for a page based on text_preference."""
        native_text = (page.get("native") or {}).get("text") or ""
        ocr_text = (page.get("ocr") or {}).get("text") or ""

        if self.text_preference == "native":
            return native_text or ocr_text
        elif self.text_preference == "ocr":
            return ocr_text or native_text
        else:  # "longer"
            return native_text if len(native_text) >= len(ocr_text) else ocr_text

    def chunk_document(self, result_path: Path) -> List[TextChunk]:
        """Read a result JSON and return all TextChunks for the document."""
        try:
            with open(result_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read {result_path}: {e}")
            return []

        doc_stem = result_path.stem.replace("_results", "")
        document_id = doc_stem

        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter
        except ImportError:
            from langchain.text_splitter import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )

        chunks: List[TextChunk] = []
        for page in data.get("pages", []):
            page_num = page.get("page_number", 0)
            text = self._pick_text(page).strip()
            if len(text) < self.min_chunk_length:
                continue

            splits = splitter.split_text(text)
            for chunk_idx, chunk_text in enumerate(splits):
                if len(chunk_text.strip()) < self.min_chunk_length:
                    continue
                chunk_id = f"{doc_stem}_page_{page_num}_chunk_{chunk_idx}"
                chunks.append(
                    TextChunk(
                        chunk_id=chunk_id,
                        text=chunk_text.strip(),
                        document_id=document_id,
                        page_number=page_num,
                        source_file=str(result_path),
                    )
                )
        return chunks

    # ------------------------------------------------------------------
    # Index building
    # ------------------------------------------------------------------

    def build_index(self, force_rebuild: bool = False) -> Dict[str, int]:
        """Build ChromaDB and BM25 indexes. Returns stats dict."""
        vs = self._get_vector_store()
        bm25 = self._get_bm25()

        # Check if already built
        if not force_rebuild and vs.count() > 0:
            logger.info(f"Vector store already has {vs.count()} chunks. Use force_rebuild=True to rebuild.")
            if bm25.count() == 0:
                bm25.load(self.bm25_path)
            return self.get_stats()

        if force_rebuild:
            vs.reset()
            from src.rag.bm25 import BM25Index
            self._bm25_index = BM25Index(k1=self.bm25_k1, b=self.bm25_b)
            bm25 = self._bm25_index

        result_files = self.discover_result_files()
        if not result_files:
            logger.warning("No result files found in data/processed/")
            return {"documents": 0, "pages": 0, "chunks": 0}

        all_chunks: List[TextChunk] = []
        total_pages = 0
        docs_processed = 0

        for rf in result_files:
            chunks = self.chunk_document(rf)
            if chunks:
                # Count pages from the source file
                try:
                    with open(rf, "r", encoding="utf-8") as f:
                        d = json.load(f)
                    total_pages += len(d.get("pages", []))
                except Exception:
                    pass
                all_chunks.extend(chunks)
                docs_processed += 1

        logger.info(f"Total chunks to index: {len(all_chunks)}")

        # Populate vector store
        logger.info("Populating vector store...")
        vs.add_chunks(all_chunks)

        # Populate BM25
        logger.info("Building BM25 index...")
        bm25.add_chunks(all_chunks)
        bm25.save(self.bm25_path)

        return {
            "documents": docs_processed,
            "pages": total_pages,
            "chunks": len(all_chunks),
        }

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        vs = self._get_vector_store()
        bm25 = self._get_bm25()
        if bm25.count() == 0:
            bm25.load(self.bm25_path)
        return {
            "vector_chunks": vs.count(),
            "bm25_chunks": bm25.count(),
            "persist_directory": self.persist_dir,
            "bm25_path": self.bm25_path,
        }
