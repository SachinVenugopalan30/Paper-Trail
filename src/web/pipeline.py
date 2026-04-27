"""Shared RAG pipeline construction + provider/model registry.

Used by the FastAPI server (`src/web/server.py`). Lifted from the legacy
Gradio chatbot so both surfaces can share the same chain-build logic.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_DEFAULT_RAG_CONFIG = str(_PROJECT_ROOT / "config" / "rag.yaml")

try:
    from dotenv import load_dotenv
    load_dotenv(_PROJECT_ROOT / ".env")
except ImportError:
    pass


PROVIDER_MODELS = {
    "claude": {
        "type": "select",
        "options": [
            "claude-opus-4-20250514",
            "claude-sonnet-4-20250514",
            "claude-3-5-sonnet-20241022",
            "claude-3-haiku-20240307",
        ],
    },
    "openai": {
        "type": "select",
        "options": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
    },
    "gemini": {
        "type": "select",
        "options": ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-pro"],
    },
    "ollama": {
        "type": "select-or-text",
        "options": ["llama3.2:3b", "llama3.1:8b", "gemma2:2b", "qwen2.5:7b", "mistral:7b"],
    },
    "vllm": {
        "type": "text",
        "placeholder": "openai/gpt-4o, anthropic/claude-3.5-sonnet, ...",
    },
}


def build_rag_chain(provider: str = "vllm", top_k: int = 8, config_path: Optional[str] = None):
    """Build the full RAG pipeline: vector store + BM25 + graph + retriever + chain."""
    import yaml

    cfg_path = config_path or _DEFAULT_RAG_CONFIG
    with open(cfg_path, "r") as f:
        cfg = yaml.safe_load(f) or {}

    cfg.setdefault("retrieval", {})["final_top_k"] = top_k

    from src.rag.vector_store import VectorStore
    vec_cfg = cfg.get("vector", {})
    vs = VectorStore(
        collection_name=vec_cfg.get("collection_name", "pdf_chunks"),
        embedding_model=vec_cfg.get("embedding_model", "all-MiniLM-L6-v2"),
        persist_directory=vec_cfg.get("persist_directory", "data/rag/chromadb"),
    )

    from src.rag.bm25 import BM25Index
    bm_cfg = cfg.get("bm25", {})
    bm25 = BM25Index(k1=bm_cfg.get("k1", 1.5), b=bm_cfg.get("b", 0.75))
    bm25_path = bm_cfg.get("persist_path", "data/rag/bm25_index.json")
    if not bm25.load(bm25_path):
        logger.warning("BM25 index not found — keyword search disabled. Run `rag index` first.")

    graph_ret = None
    try:
        from src.kg.client import get_client as get_kg_client
        kg = get_kg_client()
        kg.connect()
        from src.rag.graph_retriever import GraphRetriever
        ret_cfg = cfg.get("retrieval", {})
        graph_ret = GraphRetriever(
            kg_client=kg,
            max_entities=ret_cfg.get("graph_max_entities", 5),
            max_hops=ret_cfg.get("graph_max_hops", 1),
        )
    except Exception as e:
        logger.warning(f"Neo4j unavailable — graph retrieval disabled: {e}")

    from src.rag.hybrid import HybridRetriever
    retriever = HybridRetriever(
        vector_store=vs,
        bm25_index=bm25,
        graph_retriever=graph_ret,
        config=cfg,
    )

    from src.llm.client import get_client as get_llm_client
    llm = get_llm_client(provider_name=provider)

    from src.rag.chain import RAGChain
    return RAGChain(retriever=retriever, llm_client=llm, config=cfg)


def apply_provider_model(client, provider: str, model: str) -> None:
    """Mutate in-memory provider config and rebuild the LangChain client."""
    cfg = client.config.get_provider_config(provider)
    if not cfg:
        raise ValueError(f"Unknown provider: {provider}")
    cfg.model = model
    client.switch_provider(provider)
