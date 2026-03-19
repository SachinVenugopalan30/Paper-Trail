"""RAG chain: prompt building, LLM call, and conversation memory."""

import logging
from dataclasses import dataclass
from typing import List, Tuple, Optional, Generator, Dict, Any

import yaml
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG = Path(__file__).parent.parent.parent / "config" / "rag.yaml"


def _load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    p = Path(config_path) if config_path else _DEFAULT_CONFIG
    if not p.exists():
        return {}
    with open(p, "r") as f:
        return yaml.safe_load(f) or {}


@dataclass
class ChatMessage:
    role: str      # "user" | "assistant"
    content: str


class RAGChain:
    """Orchestrates retrieval, prompt building, and LLM generation."""

    _DEFAULT_SYSTEM = (
        "You are a research assistant for a PDF document knowledge base. "
        "Answer based on the provided context. Cite document IDs when possible. "
        "If context is insufficient, say so."
    )

    def __init__(self, retriever, llm_client, config: Optional[Dict[str, Any]] = None):
        self.retriever = retriever
        self.llm_client = llm_client
        cfg = config or _load_config()
        gen = cfg.get("generation", {})
        self.system_prompt: str = gen.get("system_prompt", self._DEFAULT_SYSTEM).strip()
        self.max_context_tokens: int = gen.get("max_context_tokens", 3000)
        self.max_history_turns: int = gen.get("max_history_turns", 10)

    # ------------------------------------------------------------------
    # Context formatting
    # ------------------------------------------------------------------

    def format_context(self, results) -> str:
        """Format retrieval results into a labelled context block."""
        bm25_chunks = [r for r in results if r.source == "bm25"]
        vector_chunks = [r for r in results if r.source == "vector"]
        graph_chunks = [r for r in results if r.source == "graph"]

        lines = []

        if bm25_chunks:
            lines.append("[KEYWORD MATCHES]")
            for i, r in enumerate(bm25_chunks, 1):
                doc_id = r.metadata.get("document_id", "unknown")
                lines.append(f"{i}. [{doc_id}] {r.text[:500]}")

        if vector_chunks:
            lines.append("[SEMANTIC MATCHES]")
            for i, r in enumerate(vector_chunks, 1):
                doc_id = r.metadata.get("document_id", "unknown")
                lines.append(f"{i}. [{doc_id}] {r.text[:500]}")

        if graph_chunks:
            lines.append("[GRAPH CONTEXT]")
            for r in graph_chunks:
                lines.append(f"- {r.text[:300]}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Prompt building
    # ------------------------------------------------------------------

    def build_prompt(self, query: str, context: str, history: Optional[List[ChatMessage]] = None) -> str:
        parts = []

        if history:
            recent = history[-(self.max_history_turns * 2):]
            hist_lines = []
            for msg in recent:
                prefix = "User" if msg.role == "user" else "Assistant"
                hist_lines.append(f"{prefix}: {msg.content}")
            parts.append("=== CONVERSATION HISTORY ===")
            parts.append("\n".join(hist_lines))

        if context.strip():
            parts.append("=== RETRIEVED CONTEXT ===")
            parts.append(context)

        parts.append("=== QUESTION ===")
        parts.append(query)

        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def query(
        self,
        user_query: str,
        history: Optional[List[ChatMessage]] = None,
    ) -> Tuple[str, list]:
        """Retrieve + generate. Returns (answer_text, retrieval_results)."""
        if not user_query.strip():
            return "Please enter a question.", []

        results = self.retriever.retrieve(user_query)
        context = self.format_context(results)
        prompt = self.build_prompt(user_query, context, history)

        try:
            response = self.llm_client.chat_text(
                prompt=prompt,
                system_prompt=self.system_prompt,
            )
            answer = response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            answer = f"Error generating response: {e}"

        return answer, results

    def stream_query(
        self,
        user_query: str,
        history: Optional[List[ChatMessage]] = None,
    ) -> Generator[str, None, None]:
        """Stream response tokens. Falls back to non-streaming on error."""
        if not user_query.strip():
            yield "Please enter a question."
            return

        results = self.retriever.retrieve(user_query)
        context = self.format_context(results)
        prompt = self.build_prompt(user_query, context, history)

        try:
            for token in self.llm_client.stream_text(
                prompt=prompt,
                system_prompt=self.system_prompt,
            ):
                yield token
        except Exception as e:
            logger.error(f"LLM streaming failed: {e}")
            # Fallback to non-streaming
            try:
                response = self.llm_client.chat_text(
                    prompt=prompt,
                    system_prompt=self.system_prompt,
                )
                yield response.content if hasattr(response, "content") else str(response)
            except Exception as e2:
                yield f"Error generating response: {e2}"
