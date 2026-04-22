#!/bin/bash
#SBATCH --job-name=paper_trail_full
#SBATCH --partition=fpga
#SBATCH --account=class_cse573spring2026
#SBATCH --qos=class

# Resource Allocation
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=160G
#SBATCH --time=12:00:00

# GPU for GLM-OCR server
#SBATCH --gres=gpu:a30:1

# Output files
#SBATCH --output=%x_%j.out
#SBATCH --error=%x_%j.err

set -euo pipefail
set -x
trap 'echo "FAILED at line $LINENO with exit code $?"' ERR

# ============================
# USER SETTINGS
# ============================
WORKDIR="/scratch/svenug15/swm-project"
DATA_DIR="${DATA_DIR:-"$WORKDIR/data"}"

CORPUS_DIRS="${CORPUS_DIRS:-
    $DATA_DIR/batch2/GHOSTSCRIPT
    $DATA_DIR/batch2/TIKA
    $DATA_DIR/batch3/MOZILLA
    $DATA_DIR/batch4/LIBRE_OFFICE
    $DATA_DIR/batch4/OOO
    $DATA_DIR/batch4/pdf.js
}"

# Extraction settings — OCR-only since GLM-OCR outperforms native (CER 0.61 vs 1.27)
EXTRACT_METHOD="${EXTRACT_METHOD:-ocr}"
PARALLEL_WORKERS="${PARALLEL_WORKERS:-8}"
MAX_PAGES="${MAX_PAGES:-}"       # empty = no limit
PDF_LIMIT="${PDF_LIMIT:-}"       # empty = process all PDFs

# KG settings
KG_METHOD="${KG_METHOD:-llm}"    # llm | classical | both
KG_RESUME="${KG_RESUME:-1}"

# Pipeline stages (1=run, 0=skip — useful for re-running individual steps)
RUN_EXTRACT="${RUN_EXTRACT:-1}"
RUN_KG="${RUN_KG:-1}"
RUN_RAG_INDEX="${RUN_RAG_INDEX:-1}"
RUN_EXPORT="${RUN_EXPORT:-1}"

# Services
NEO4J_PASSWORD="${NEO4J_PASSWORD:-password}"
NEO4J_SIF="${NEO4J_SIF:-/scratch/$USER/containers/neo4j.sif}"
NEO4J_HTTP_PORT="${NEO4J_HTTP_PORT:-7474}"
NEO4J_BOLT_PORT="${NEO4J_BOLT_PORT:-7687}"

# GLM-OCR via vLLM
OCR_HOST="${OCR_HOST:-localhost}"
OCR_PORT="${OCR_PORT:-8080}"
GLM_OCR_MODEL="${GLM_OCR_MODEL:-zai-org/GLM-OCR}"
GLM_OCR_SERVED_NAME="${GLM_OCR_SERVED_NAME:-glm-ocr}"
GLM_OCR_HF_CACHE="${GLM_OCR_HF_CACHE:-/scratch/$USER/hf_cache}"
GLM_OCR_MAX_LEN="${GLM_OCR_MAX_LEN:-8192}"
GLM_OCR_GPU="${GLM_OCR_GPU:-0}"

CONDA_ENV="${CONDA_ENV:-paper_trail_env}"

# Export destination (set to a path on your laptop-accessible scratch or /home)
EXPORT_DIR="${EXPORT_DIR:-$WORKDIR/export}"

# ============================
# Setup
# ============================
echo "WORKDIR=$WORKDIR"
ls -ld "$WORKDIR" || exit 1
cd "$WORKDIR"

JOB_ID="${SLURM_JOB_ID:-$$}"
LOGDIR="$WORKDIR/logs/$JOB_ID"
mkdir -p "$LOGDIR"

echo "===== paper_trail_full_pipeline ====="
echo "Node:         $(hostname)"
echo "SLURM_JOB_ID: ${SLURM_JOB_ID:-}"
echo "DATA_DIR:     $DATA_DIR"
echo "METHOD:       $EXTRACT_METHOD"
echo "KG_METHOD:    $KG_METHOD"
echo "LLM_PROVIDER: ${LLM_PROVIDER:-ollama}"
echo "Stages:       extract=$RUN_EXTRACT  kg=$RUN_KG  rag=$RUN_RAG_INDEX  export=$RUN_EXPORT"
echo "Corpora:"
for corpus_dir in $CORPUS_DIRS; do
    echo "  $corpus_dir"
done

# ============================
# Modules / env activation
# ============================
module purge || true
module load mamba/latest || true

eval "$(conda shell.bash hook)"
conda activate "$CONDA_ENV"

python3 -V
which python3
python3 -c "import src; print('src package OK')" || {
    echo "ERROR: could not import src — check WORKDIR and CONDA_ENV"
    exit 1
}

# ============================
# Helpers
# ============================
wait_for_http() {
    local url="$1"
    local name="$2"
    local timeout_s="${3:-120}"
    echo "Waiting for $name at $url ..."
    set +e
    timeout "$timeout_s" bash -c "
        until curl -fsS '$url' >/dev/null 2>&1; do
            sleep 5
        done
    "
    local rc=$?
    set -e
    if [[ $rc -ne 0 ]]; then
        echo "ERROR: $name did not become ready at $url within ${timeout_s}s"
        return 1
    fi
    echo "$name ready."
}

cleanup() {
    echo "Cleaning up background services..."
    [[ -n "${NEO4J_PID:-}" ]] && kill "${NEO4J_PID}" 2>/dev/null || true
    [[ -n "${OCR_PID:-}"   ]] && kill "${OCR_PID}"   2>/dev/null || true
}
trap cleanup EXIT

# ============================
# Start Neo4j via Apptainer
# ============================
SCRATCH_BASE="${SLURM_TMPDIR:-${SCRATCH:-/scratch/$USER}}"
NEO4J_SCRATCH="$SCRATCH_BASE/neo4j/$JOB_ID"
mkdir -p "$NEO4J_SCRATCH"/{data,logs,import,plugins}

if ! curl -fsS "http://localhost:${NEO4J_HTTP_PORT}" >/dev/null 2>&1; then
    echo "Starting Neo4j via Apptainer ($NEO4J_SIF)..."
    [[ -f "$NEO4J_SIF" ]] || {
        echo "Neo4j SIF not found. Pulling..."
        mkdir -p "$(dirname "$NEO4J_SIF")"
        apptainer pull "$NEO4J_SIF" docker://neo4j:5-community
    }

    apptainer run \
        --bind "$NEO4J_SCRATCH/data:/data" \
        --bind "$NEO4J_SCRATCH/logs:/logs" \
        --bind "$NEO4J_SCRATCH/import:/var/lib/neo4j/import" \
        --bind "$NEO4J_SCRATCH/plugins:/plugins" \
        --env NEO4J_AUTH="neo4j/${NEO4J_PASSWORD}" \
        --env NEO4J_dbms_memory_heap_initial__size=2G \
        --env NEO4J_dbms_memory_heap_max__size=8G \
        --env NEO4J_dbms_memory_pagecache__size=4G \
        --env NEO4J_dbms_connector_http_listen__address="0.0.0.0:${NEO4J_HTTP_PORT}" \
        --env NEO4J_dbms_connector_bolt_listen__address="0.0.0.0:${NEO4J_BOLT_PORT}" \
        "$NEO4J_SIF" \
        > "$LOGDIR/neo4j.log" 2>&1 &
    NEO4J_PID=$!

    wait_for_http "http://localhost:${NEO4J_HTTP_PORT}" "Neo4j HTTP" 180
else
    echo "Neo4j already running on port ${NEO4J_HTTP_PORT}."
fi

export NEO4J_PASSWORD="$NEO4J_PASSWORD"
export NEO4J_URI="bolt://localhost:${NEO4J_BOLT_PORT}"

# ============================
# Start GLM-OCR via vLLM (skipped for native-only extraction)
# ============================
if [[ "$EXTRACT_METHOD" != "native" ]] && [[ "$RUN_EXTRACT" == "1" ]]; then
    if ! curl -fsS "http://${OCR_HOST}:${OCR_PORT}/v1/models" >/dev/null 2>&1; then
        echo "Starting GLM-OCR server ($GLM_OCR_MODEL) via vLLM on CUDA device $GLM_OCR_GPU..."
        mkdir -p "$GLM_OCR_HF_CACHE"

        CUDA_VISIBLE_DEVICES="$GLM_OCR_GPU" \
        HF_HOME="$GLM_OCR_HF_CACHE" \
        HUGGINGFACE_HUB_TOKEN="${HUGGINGFACE_HUB_TOKEN:-}" \
        vllm serve "$GLM_OCR_MODEL" \
            --host 127.0.0.1 \
            --port "$OCR_PORT" \
            --served-model-name "$GLM_OCR_SERVED_NAME" \
            --max-model-len "$GLM_OCR_MAX_LEN" \
            --tensor-parallel-size 1 \
            --trust-remote-code \
        > "$LOGDIR/ocr_server.log" 2>&1 &
        OCR_PID=$!

        # vLLM can take several minutes to load the model weights
        wait_for_http "http://${OCR_HOST}:${OCR_PORT}/v1/models" "GLM-OCR vLLM" 1800
        echo "GLM-OCR ready at http://${OCR_HOST}:${OCR_PORT}"
    else
        echo "GLM-OCR server already running."
    fi
fi

# Point ocr.py at the vLLM endpoint (overrides hardcoded defaults)
export GLM_OCR_URL="http://${OCR_HOST}:${OCR_PORT}/v1/chat/completions"
export GLM_OCR_MODEL="$GLM_OCR_SERVED_NAME"

# ============================
# Step 1 — Batch PDF extraction
# ============================
if [[ "$RUN_EXTRACT" == "1" ]]; then
    echo "===== STEP 1: Batch extraction ($EXTRACT_METHOD) ====="

    for corpus_dir in $CORPUS_DIRS; do
        [[ -d "$corpus_dir" ]] || { echo "SKIP (not found): $corpus_dir"; continue; }

        corpus_slug=$(echo "$corpus_dir" | sed "s|$DATA_DIR/||" | tr '/' '_' | tr '[:upper:]' '[:lower:]')
        out_dir="$DATA_DIR/processed/$corpus_slug"
        checkpoint="$out_dir/checkpoint.json"
        mkdir -p "$out_dir"

        echo "--- Extracting: $corpus_dir → $out_dir ---"

        EXTRACT_ARGS=(
            extract-batch "$corpus_dir"
            --method "$EXTRACT_METHOD"
            --parallel "$PARALLEL_WORKERS"
            --output-dir "$out_dir"
            --checkpoint "$checkpoint"
        )
        [[ -n "$MAX_PAGES" ]] && EXTRACT_ARGS+=(--max-pages "$MAX_PAGES")
        [[ -n "$PDF_LIMIT" ]] && EXTRACT_ARGS+=(--limit "$PDF_LIMIT")

        python3 -m src.cli "${EXTRACT_ARGS[@]}" \
            2>&1 | tee "$LOGDIR/extract_${corpus_slug}.log"

        echo "Done: $corpus_dir"
    done

    echo "All corpora extracted."
fi

# ============================
# Step 2 — Build Knowledge Graph
# ============================
if [[ "$RUN_KG" == "1" ]]; then
    echo "===== STEP 2: Knowledge graph ====="

    python3 -m src.cli kg init \
        2>&1 | tee "$LOGDIR/kg_init.log"

    KG_SCRIPT_ARGS=(--all --method "$KG_METHOD")
    [[ "$KG_RESUME" == "1" ]] && KG_SCRIPT_ARGS+=(--resume)

    python3 scripts/build_knowledge_graph.py "${KG_SCRIPT_ARGS[@]}" \
        2>&1 | tee "$LOGDIR/kg_build.log"

    python3 -m src.cli kg stats \
        2>&1 | tee "$LOGDIR/kg_stats.log"
fi

# ============================
# Step 3 — Build RAG index
# ============================
if [[ "$RUN_RAG_INDEX" == "1" ]]; then
    echo "===== STEP 3: RAG index ====="

    python3 -m src.cli rag index \
        2>&1 | tee "$LOGDIR/rag_index.log"

    python3 -m src.cli rag stats \
        2>&1 | tee "$LOGDIR/rag_stats.log"
fi

# ============================
# Step 4 — Export for laptop demo
# ============================
if [[ "$RUN_EXPORT" == "1" ]]; then
    echo "===== STEP 4: Exporting data for demo ====="
    mkdir -p "$EXPORT_DIR"

    # Export RAG index (ChromaDB + BM25) — just a directory copy
    echo "Copying RAG index..."
    cp -r "$DATA_DIR/rag" "$EXPORT_DIR/rag"

    # Dump Neo4j database
    echo "Dumping Neo4j database..."
    apptainer exec \
        --bind "$NEO4J_SCRATCH/data:/data" \
        --bind "$EXPORT_DIR:/export" \
        "$NEO4J_SIF" \
        neo4j-admin database dump neo4j --to-path=/export \
        2>&1 | tee "$LOGDIR/neo4j_dump.log"

    # Save final graph stats alongside the export
    python3 -m src.cli kg stats \
        2>&1 | tee "$EXPORT_DIR/kg_stats_final.txt"

    echo "Export complete. Contents:"
    ls -lh "$EXPORT_DIR"
    echo ""
    echo "To restore on your laptop:"
    echo "  1. Copy $EXPORT_DIR/rag  →  data/rag"
    echo "  2. Stop local Neo4j: docker-compose down"
    echo "  3. Restore dump: neo4j-admin database load neo4j --from-path=\$EXPORT_DIR --overwrite-destination=true"
    echo "  4. Start Neo4j: docker-compose up -d neo4j"
fi

echo "===== DONE. Logs in $LOGDIR ====="
