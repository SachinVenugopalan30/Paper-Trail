"""ChromaDB vector store wrapper for RAG retrieval."""

import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class VectorStore:
    """ChromaDB persistent vector store with sentence-transformer embeddings."""

    def __init__(
        self,
        collection_name: str = "pdf_chunks",
        embedding_model: str = "all-MiniLM-L6-v2",
        persist_directory: str = "data/rag/chromadb",
    ):
        self.collection_name = collection_name
        self.embedding_model = embedding_model
        self.persist_directory = persist_directory
        self._client = None
        self._collection = None
        self._ef = None

    def _ensure_initialized(self):
        if self._collection is not None:
            return
        try:
            import chromadb
            from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
        except ImportError as e:
            raise ImportError(f"chromadb and sentence-transformers are required: {e}")

        Path(self.persist_directory).mkdir(parents=True, exist_ok=True)
        self._ef = SentenceTransformerEmbeddingFunction(model_name=self.embedding_model)
        self._client = chromadb.PersistentClient(path=self.persist_directory)
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(self, chunks) -> int:
        """Add TextChunk objects to the vector store. Returns count added."""
        self._ensure_initialized()
        if not chunks:
            return 0

        ids = [c.chunk_id for c in chunks]
        documents = [c.text for c in chunks]
        metadatas = [
            {
                "document_id": c.document_id,
                "page_number": c.page_number,
                "source_file": c.source_file,
                **{k: str(v) for k, v in c.metadata.items()},
            }
            for c in chunks
        ]

        # ChromaDB has a batch size limit; insert in batches of 5000
        batch_size = 5000
        total = 0
        for i in range(0, len(ids), batch_size):
            self._collection.add(
                ids=ids[i : i + batch_size],
                documents=documents[i : i + batch_size],
                metadatas=metadatas[i : i + batch_size],
            )
            total += len(ids[i : i + batch_size])

        return total

    def query(self, query_text: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Query the vector store. Returns list of {chunk_id, text, score, metadata}."""
        self._ensure_initialized()
        results = self._collection.query(
            query_texts=[query_text],
            n_results=min(top_k, max(1, self.count())),
            include=["documents", "metadatas", "distances"],
        )

        output = []
        if not results["ids"] or not results["ids"][0]:
            return output

        for chunk_id, doc, meta, dist in zip(
            results["ids"][0],
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            output.append(
                {
                    "chunk_id": chunk_id,
                    "text": doc,
                    "score": float(1.0 - dist),  # cosine similarity
                    "metadata": meta,
                }
            )
        return output

    def count(self) -> int:
        """Return number of chunks stored."""
        self._ensure_initialized()
        return self._collection.count()

    def reset(self):
        """Delete and recreate the collection."""
        self._ensure_initialized()
        self._client.delete_collection(self.collection_name)
        self._collection = None
        self._ensure_initialized()
        logger.info("VectorStore collection reset.")
