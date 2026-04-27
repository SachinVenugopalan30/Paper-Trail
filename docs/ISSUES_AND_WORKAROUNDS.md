# Known Issues, Limitations, and Workarounds

Living catalog of bugs hit, root causes diagnosed, and the fixes applied. Grouped by pipeline stage.

---

## 1. Extraction (PDF → text)

### 1.1 Infinite loop in chunked Slurm jobs (FIXED)

**Symptom.** `submit_pipeline.sh` ran in 150-file chunks (Python restart per chunk to combat OOM). After first chunk, every subsequent chunk re-attempted the same 150 files and reported "All files already processed!" — no progress made.

**Root cause.** `CheckpointManager.is_processed()` only checked `processed_files`. Files in `failed_files` or `skipped_files` were not considered "done." The CLI also pre-sliced `pdf_paths[:limit]` *before* filtering, so the same 150 entries were always selected.

**Fix.**
- Added `CheckpointManager.is_done()` checking all three terminal states (processed/failed/skipped). See `src/extraction/checkpoint.py:131`.
- Refactored `BatchProcessor.process_batch()` to filter first, then apply limit. See `src/extraction/batch_processor.py:375`.
- Removed the pre-slice in `src/cli.py`; pass `limit=` to `process_batch()` instead.

### 1.2 Hybrid routing silently skips all pages (FIXED)

**Symptom.** When `method='hybrid'` and native coverage ≥ 0.8, no pages were processed. Document silently dropped.

**Root cause.** Page iterator at `batch_processor.py:202` only entered the native branch when `self.method == "native"`. Hybrid mode set `use_ocr=False` → `image_paths=[]` → fell into the OCR branch which iterates `len(image_paths) = 0`.

**Fix.** One-line change: `if self.method in ("native", "hybrid"):`.

### 1.3 pdfplumber garbage text on glyph-table PDFs (FIXED in indexer)

**Symptom.** Some PDFs yielded 500KB+ of `G G G G ...` from pdfplumber while OCR returned the real text (a few KB). RAG indexer's `text_preference: "longer"` picked the garbage.

**Root cause.** Native text extraction passes the 0.8 coverage threshold even when characters are unmapped glyphs (no `ToUnicode` map in the PDF). Coverage measures presence of any extracted chars, not their meaning.

**Workaround.** Added `_is_garbage()` heuristic in `src/rag/indexer.py:_pick_text` — flags text where one non-whitespace char comprises >40% of the page. Falls back to OCR when triggered.

**Limitation.** Catches the obvious `G G G ...` case but not subtler glyph misencodings (e.g. shifted Unicode that still has variety). Long-term fix would be to validate native extraction against a dictionary or run cheap OCR comparison.

---

## 2. OCR server (vLLM + GLM-OCR)

### 2.1 Encoder-cache overflow on large images (FIXED)

**Error.**
```
ValueError: Image with multimodal length 6111 exceeds encoder cache size 6084
```

**Root cause.** vLLM pre-allocates an encoder cache sized for one image at the configured DPI. 200 DPI scans of large pages exceeded that buffer.

**Fix.**
- Add `--limit-mm-per-prompt '{"image": 2}'` to `vllm serve` — doubles the cache.
- Drop default OCR DPI from 200 → 150 in `src/cli.py`.

**Note.** vLLM's `--limit-mm-per-prompt` requires JSON syntax (`'{"image": 2}'`). The shorthand `image=2` form was rejected.

### 2.2 OOM at chunk 13 (Slurm exit 137) (FIXED)

**Symptom.** Job killed by Linux OOM killer after ~2 hours. Chunked Python restart was working (Python RSS held flat at 3.26 MB), but the vLLM server's CPU RAM kept growing.

**Root cause.** vLLM defaults to `--max-num-seqs 64` — pre-allocates 64 concurrent request buffers. We only run one extraction worker against it; the other 63 buffers were dead weight that grew over time.

**Fix.** Add `--max-num-seqs 1` and bump `--gpu-memory-utilization 0.85`.

### 2.3 SGLang does not support GLM-OCR (HARD LIMITATION)

**Attempt.** Tried SGLang as a faster alternative to vLLM.

**Error.**
```
ValueError: No processor registered for architecture: ['GlmOcrForConditionalGeneration']
```

**Conclusion.** SGLang has no support for the GLM-OCR architecture. Stick with vLLM container.

### 2.4 Native vLLM pip install fails on Sol login node (HARD LIMITATION)

**Attempt.** Replace the vLLM Apptainer container with a pip-installed copy in the conda env, hoping for a leaner install.

**Errors.**
- Initial: GCC 8.5 too old (vLLM build needs ≥9).
- After loading newer GCC module: build hung at "Building wheel for vllm" for >15 min and was cancelled.

**Conclusion.** Use the pre-built container at `/packages/apps/simg/vllm-nightly-26.03.19.sif`. Native install impractical on shared HPC.

### 2.5 4xx OCR errors retried unnecessarily (FIXED)

**Symptom.** Some PDFs trigger HTTP 400 (e.g. malformed page), and the retry loop wasted 4 attempts before failing.

**Fix.** Added `GLMOCRNonRetryableError` in `src/extraction/ocr.py`. HTTP 4xx now raises immediately; only 5xx and connection errors retry with exponential backoff.

### 2.6 MTP speculative decoding unsupported in this vLLM nightly

**Attempt.** Add `--speculative-config.method mtp --speculative-config.num_speculative_tokens 1` for faster generation.

**Result.** vLLM 0.17.2rc1.dev96 in our container does not support MTP for GLM-OCR. Skipped.

---

## 3. RAG indexer

### 3.1 ChromaDB existing index silently reused

**Behavior.** `python3 -m src.cli rag index` is a no-op if the vector store already has chunks. Easy to mistake for "ran but ignored my new data."

**Workaround.** Always pass `--force` after adding new result JSONs:
```bash
python3 -m src.cli rag index --force
```

### 3.2 Per-document `Batches: 1/1` progress spam (COSMETIC)

**Cause.** Indexer calls `vector_store.add_chunks(chunks)` once per document. `chromadb`'s sentence-transformer embedder prints a tqdm bar per `.encode()` call → ~2700 bars for the GHOSTSCRIPT corpus.

**Workaround.**
```bash
TQDM_DISABLE=1 python3 -m src.cli rag index --force
```

### 3.3 `HybridRetriever.retrieve()` does not accept `top_k` kwarg

**Gotcha.** `top_k` is config-driven via `config/rag.yaml`. To override per-query in code, set the attribute:
```python
r = HybridRetriever(...)
r.final_top_k = 5
r.retrieve(query)
```

### 3.4 Corpus content is mostly attached sample PDFs, not bug discussions

**Observation.** Ghostscript "bug report" PDFs are largely the input PDFs that triggered the bug (UN reports, bank certificates, US Mint ads, etc.) — not descriptions of the bug. The retriever surfaces those samples for any query.

**Implication.** RAG answers will reflect attached-document content, not Ghostscript fault analysis. Same likely true for Mozilla and LibreOffice corpora. Worth flagging in the final report.

---

## 4. Knowledge graph (LLM extraction)

### 4.1 `python-dotenv` installed but `load_dotenv()` never called

**Symptom.** `OPENROUTER_API_KEY` set in `.env` not picked up by config substitution.

**Fix.** Added `load_dotenv(project_root / ".env")` near the top of `scripts/build_knowledge_graph.py`. Inline scripts must call `load_dotenv()` themselves.

### 4.2 `vllm` provider name is misleading

**Note.** The `vllm` entry in `config/llm.yaml` is just any OpenAI-compatible endpoint. We currently point it at OpenRouter. The `OpenAIProvider` class does not pass `base_url` from config, so `vllm` is the only path for hosted OpenAI-compatible APIs.

### 4.3 OpenRouter reasoning tokens inflate cost

**Issue.** Qwen3-style hybrid models emit 1k–10k reasoning tokens before the answer. These are billed as completion tokens. For ~500-token KG extractions, reasoning can multiply cost 5–20×.

**Fix.** Added `extra_body` field to `ProviderConfig`. Set in `config/llm.yaml`:
```yaml
extra_body:
  reasoning:
    enabled: false
```
Passed to `ChatOpenAI(extra_body=...)`. Note: must be a top-level kwarg, not nested in `model_kwargs` (LangChain warns otherwise).

### 4.4 `--limit` flag added for cost dry-runs

**Reason.** Original `build_knowledge_graph.py` had no way to process a subset for cost estimation against paid APIs.

**Usage.**
```bash
python3 scripts/build_knowledge_graph.py --all --limit 10 --reset
```
Then check OpenRouter dashboard or `GET /api/v1/credits` to measure spend.

---

## 5. Multi-machine workflow

### 5.1 Result merging is glob-based, no manifest

**Convention.** Each teammate processes a subset (Sachin: batch2/{GHOSTSCRIPT,TIKA}; Teammate 2: batch3/MOZILLA; Teammate 3: batch4/{LIBRE_OFFICE,OOO,pdf.js}).

**Merge.** Each teammate zips `data/processed/*/results/*_results.json` and ships it. Recipient unzips into project root. Both indexers (RAG + KG) glob `data/processed/*/results/*_results.json` automatically — no manifest needed.

**Caveat.** Project sub-directory names must be unique across teammates to avoid overwrite. Current naming (`batch2_ghostscript`, `batch3_mozilla`, `batch4_libre_office`, etc.) is unique by accident.

### 5.2 `pdf.js` corpus subdir contains a `.` — no operational issue

The `.` in `$DATA_DIR/batch4/pdf.js` is fine for bash, glob, and Python paths. Result JSONs end up under `data/processed/batch4_pdf.js/results/`.

---

## 6. Environment and shell

### 6.1 Apptainer container missing common executables

**Issue.** Inside the vLLM SIF, `grep` and `python3` aren't on `$PATH`. Use absolute paths (`/usr/local/bin/python3`) when scripting against the container.

### 6.2 Fish shell escaping breaks single-quoted JSON

**Issue.** Embedding JSON like `'{"image": 2}'` inside `python3 -c '...'` in fish loses quoting. Workaround: write a temp script via `python3 -c 'open("...").write("...")'` rather than chaining.

### 6.3 `.env` location

`.env` lives in project root: `/Users/sachin/Desktop/Uni Courses/CSE 573 - SWM/2Project/.env`. `load_dotenv()` finds it via `project_root / ".env"`. Make sure `.env` is in `.gitignore`.

---

## 7. Unfixed / accepted limitations

- **Slurm `--mem=160G` shared between Python + vLLM.** No way to budget separately. If vLLM grows again, reduce `--gpu-memory-utilization` further or split into two Slurm steps.
- **No quality validation on native text** beyond the garbage-char heuristic. Subtle pdfplumber misencodings still leak into the index.
- **OpenRouter free-tier rate limit** (20 req/min, 200/day) makes free Kimi/Qwen models impractical for full-corpus KG building. Use a paid model or run overnight in chunks.
- **No tests.** `tests/` is empty. Validation is done via the Streamlit annotation tool and manual scripts.
