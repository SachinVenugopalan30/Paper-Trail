"""Gradio chatbot UI for the Hybrid RAG system."""

import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

_DEFAULT_RAG_CONFIG = str(Path(__file__).parent.parent.parent / "config" / "rag.yaml")


def _build_rag_chain(provider: str = "ollama", top_k: int = 8, config_path: Optional[str] = None):
    """Build the full RAG pipeline: indexer → stores → retriever → chain."""
    import yaml

    cfg_path = config_path or _DEFAULT_RAG_CONFIG
    with open(cfg_path, "r") as f:
        cfg = yaml.safe_load(f) or {}

    # Override top_k
    cfg.setdefault("retrieval", {})["final_top_k"] = top_k

    # Vector store
    from src.rag.vector_store import VectorStore
    vec_cfg = cfg.get("vector", {})
    vs = VectorStore(
        collection_name=vec_cfg.get("collection_name", "pdf_chunks"),
        embedding_model=vec_cfg.get("embedding_model", "all-MiniLM-L6-v2"),
        persist_directory=vec_cfg.get("persist_directory", "data/rag/chromadb"),
    )

    # BM25
    from src.rag.bm25 import BM25Index
    bm_cfg = cfg.get("bm25", {})
    bm25 = BM25Index(k1=bm_cfg.get("k1", 1.5), b=bm_cfg.get("b", 0.75))
    bm25_path = bm_cfg.get("persist_path", "data/rag/bm25_index.json")
    if not bm25.load(bm25_path):
        logger.warning("BM25 index not found — keyword search disabled. Run `rag index` first.")

    # Graph retriever (optional — skip if Neo4j unavailable)
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

    # Hybrid retriever
    from src.rag.hybrid import HybridRetriever
    retriever = HybridRetriever(
        vector_store=vs,
        bm25_index=bm25,
        graph_retriever=graph_ret,
        config=cfg,
    )

    # LLM client
    from src.llm.client import get_client as get_llm_client
    llm = get_llm_client(provider_name=provider)

    # RAG chain
    from src.rag.chain import RAGChain
    chain = RAGChain(retriever=retriever, llm_client=llm, config=cfg)
    return chain


def create_chatbot_app(config_path: Optional[str] = None):
    """Create and return the Gradio Blocks application."""
    import gradio as gr

    # State
    _chain_cache = {}
    _last_results = {"results": []}

    def get_chain(provider: str, top_k: int):
        key = (provider, top_k)
        if key not in _chain_cache:
            print(f"Loading RAG pipeline (provider={provider}, top_k={top_k})...")
            _chain_cache[key] = _build_rag_chain(provider, top_k, config_path)
            print("RAG pipeline ready.")
        return _chain_cache[key]

    def respond(message: str, history: List[Dict[str, Any]], provider: str, top_k: int):
        """Gradio streaming chat handler (messages format for Gradio 6+)."""
        if not message.strip():
            history = history + [{"role": "user", "content": message},
                                  {"role": "assistant", "content": "Please enter a question."}]
            yield history, json.dumps([], indent=2)
            return

        from src.rag.chain import ChatMessage
        chain = get_chain(provider, int(top_k))

        # Convert gradio messages-format history to ChatMessage list
        chat_history = []
        for msg in history:
            chat_history.append(ChatMessage(role=msg["role"], content=msg["content"]))

        # Retrieve results first
        results = chain.retriever.retrieve(message)
        _last_results["results"] = results

        context = chain.format_context(results)
        prompt = chain.build_prompt(message, context, chat_history)

        # Append user message and empty assistant placeholder
        history = history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": ""},
        ]

        # Stream LLM response
        accumulated = ""
        try:
            for token in chain.llm_client.stream_text(
                prompt=prompt,
                system_prompt=chain.system_prompt,
            ):
                accumulated += token
                history[-1] = {"role": "assistant", "content": accumulated}
                yield history, _format_results(results)
        except Exception as e:
            # Fallback to non-streaming
            try:
                response = chain.llm_client.chat_text(
                    prompt=prompt,
                    system_prompt=chain.system_prompt,
                )
                accumulated = response.content if hasattr(response, "content") else str(response)
            except Exception as e2:
                accumulated = f"Error: {e2}"
            history[-1] = {"role": "assistant", "content": accumulated}
            yield history, _format_results(results)
            return

    def _format_results(results) -> str:
        data = [
            {
                "chunk_id": r.chunk_id,
                "source": r.source,
                "score": round(r.score, 4),
                "document_id": r.metadata.get("document_id", ""),
                "text_preview": r.text[:200] + "..." if len(r.text) > 200 else r.text,
            }
            for r in results
        ]
        return json.dumps(data, indent=2)

    def clear_chat():
        return [], ""

    with gr.Blocks(title="PDF Knowledge Base Chatbot") as demo:
        gr.Markdown("# PDF Knowledge Base RAG Chatbot\nAsk questions about the processed PDF documents.")

        with gr.Row():
            with gr.Column(scale=3):
                chatbot = gr.Chatbot(label="Conversation", height=500)
                with gr.Row():
                    msg_box = gr.Textbox(
                        placeholder="Ask a question about the documents...",
                        label="Your question",
                        scale=4,
                    )
                    submit_btn = gr.Button("Send", variant="primary", scale=1)
                clear_btn = gr.Button("Clear Conversation")

            with gr.Column(scale=1):
                with gr.Accordion("Settings", open=False):
                    provider_dd = gr.Dropdown(
                        choices=["ollama", "claude", "openai", "gemini"],
                        value="ollama",
                        label="LLM Provider",
                    )
                    topk_slider = gr.Slider(
                        minimum=1, maximum=20, value=8, step=1,
                        label="Top-K results",
                    )

                with gr.Accordion("Retrieval Details", open=False):
                    retrieval_json = gr.JSON(label="Last retrieval sources")

        submit_btn.click(
            respond,
            inputs=[msg_box, chatbot, provider_dd, topk_slider],
            outputs=[chatbot, retrieval_json],
        )
        msg_box.submit(
            respond,
            inputs=[msg_box, chatbot, provider_dd, topk_slider],
            outputs=[chatbot, retrieval_json],
        )
        clear_btn.click(clear_chat, outputs=[chatbot, retrieval_json])

    return demo


def main():
    """Launch the Gradio chatbot."""
    logging.basicConfig(level=logging.INFO)
    app = create_chatbot_app()
    app.launch(server_port=7860, share=False)


if __name__ == "__main__":
    main()
