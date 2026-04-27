"""FastAPI server for the Paper Trail chat UI.

Replaces the legacy Gradio surface. Serves a single-page app from
`src/web/static/` and exposes JSON + Server-Sent Events endpoints
that drive the hybrid RAG pipeline.
"""

import asyncio
import json
import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List, Optional, Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.web.pipeline import build_rag_chain, apply_provider_model, PROVIDER_MODELS
from src.rag.chain import ChatMessage

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"

_state: Dict[str, Any] = {"chain": None}
_swap_lock = threading.Lock()


def _initial_provider_model() -> tuple:
    """Pick a sensible default — the configured default_provider + its model."""
    from src.llm.config import get_config
    cfg = get_config()
    provider = cfg.default_provider
    pcfg = cfg.get_provider_config(provider)
    model = pcfg.model if pcfg else ""
    return provider, model


@asynccontextmanager
async def lifespan(app: FastAPI):
    provider, _ = _initial_provider_model()
    logger.info(f"Boot: building RAG chain with provider={provider}")
    _state["chain"] = build_rag_chain(provider=provider, top_k=8)
    logger.info("RAG chain ready.")
    yield
    logger.info("Shutting down.")


app = FastAPI(title="Paper Trail", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


class ConfigBody(BaseModel):
    provider: str
    model: str


class RetrieveBody(BaseModel):
    query: str


class HistoryItem(BaseModel):
    role: str
    content: str


class ChatBody(BaseModel):
    query: str
    history: List[HistoryItem] = []


@app.get("/")
async def index():
    return FileResponse(str(_STATIC_DIR / "index.html"))


@app.get("/api/providers")
async def providers():
    chain = _state["chain"]
    if chain is None:
        raise HTTPException(503, "Pipeline not initialized")
    cfg = chain.llm_client.config
    enabled = set(cfg.get_enabled_providers())
    visible: Dict[str, Dict[str, Any]] = {
        name: spec for name, spec in PROVIDER_MODELS.items() if name in enabled
    }
    active_provider = chain.llm_client.get_current_provider()
    active_pcfg = cfg.get_provider_config(active_provider)
    active_model = active_pcfg.model if active_pcfg else ""
    return {
        "providers": visible,
        "active": {"provider": active_provider, "model": active_model},
    }


@app.post("/api/config")
async def set_config(body: ConfigBody):
    chain = _state["chain"]
    if chain is None:
        raise HTTPException(503, "Pipeline not initialized")
    if body.provider not in PROVIDER_MODELS:
        raise HTTPException(400, f"Unknown provider: {body.provider}")
    if not body.model.strip():
        raise HTTPException(400, "Model name required")
    try:
        with _swap_lock:
            apply_provider_model(chain.llm_client, body.provider, body.model.strip())
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.exception("Provider swap failed")
        raise HTTPException(500, f"Swap failed: {e}")
    return {"ok": True, "provider": body.provider, "model": body.model.strip()}


@app.post("/api/retrieve")
async def retrieve(body: RetrieveBody):
    chain = _state["chain"]
    if chain is None:
        raise HTTPException(503, "Pipeline not initialized")
    query = body.query.strip()
    if not query:
        return {"results": []}

    def _run():
        return chain.retriever.retrieve(query)

    results = await asyncio.to_thread(_run)
    payload = []
    for r in results:
        text = r.text or ""
        payload.append({
            "chunk_id": r.chunk_id,
            "source": r.source,
            "score": round(float(r.score), 4),
            "document_id": r.metadata.get("document_id", ""),
            "preview": text[:400],
        })
    return {"results": payload}


@app.post("/api/chat")
async def chat(body: ChatBody):
    chain = _state["chain"]
    if chain is None:
        raise HTTPException(503, "Pipeline not initialized")
    query = body.query.strip()
    if not query:
        async def _empty():
            yield _sse("token", {"text": "Please enter a question."})
            yield _sse("done", {})
        return StreamingResponse(_empty(), media_type="text/event-stream")

    history = [ChatMessage(role=h.role, content=h.content) for h in body.history]

    async def event_stream():
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()
        sentinel = object()

        def _producer():
            try:
                for tok in chain.stream_query(query, history=history):
                    asyncio.run_coroutine_threadsafe(queue.put(tok), loop)
            except Exception as e:
                logger.exception("Stream producer crashed")
                asyncio.run_coroutine_threadsafe(
                    queue.put(f"\n\n[error: {e}]"), loop
                )
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(sentinel), loop)

        threading.Thread(target=_producer, daemon=True).start()

        try:
            while True:
                tok = await queue.get()
                if tok is sentinel:
                    break
                yield _sse("token", {"text": tok})
        finally:
            yield _sse("done", {})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def main(host: str = "127.0.0.1", port: int = 7860, reload: bool = False):
    """Launch the Paper Trail web UI via uvicorn."""
    import uvicorn
    print(f"Paper Trail running on http://{host}:{port}")
    uvicorn.run(
        "src.web.server:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
