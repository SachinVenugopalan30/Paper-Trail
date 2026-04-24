#!/bin/bash
#SBATCH --job-name=paper_trail
#SBATCH --partition=general
#SBATCH --account=class_cse573spring2026
#SBATCH --qos=class

# Resource Allocation
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=160G
#SBATCH --time=08:00:00

# Output files
#SBATCH --output=%x_%j.out
#SBATCH --error=%x_%j.err

# Requesting the actual GPU
#SBATCH --gres=gpu:h100:1

set -euo pipefail
set -x
trap 'echo "FAILED at line $LINENO with exit code $?"' ERR

# ============================
# USER SETTINGS (override with sbatch --export=ALL,...)
# ============================
WORKDIR="/scratch/svenug15/Paper-Trail"
echo $WORKDIR
DATA_DIR="${DATA_DIR:-"$WORKDIR/data"}"

# All corpus directories to process (space-separated; override to run a subset)
CORPUS_DIRS="${CORPUS_DIRS:-
    $DATA_DIR/batch3/MOZILLA
    $DATA_DIR/batch4/LIBRE_OFFICE
}"

# Extraction settings
EXTRACT_METHOD="${EXTRACT_METHOD:-hybrid}"     # native | ocr | hybrid
PARALLEL_WORKERS="${PARALLEL_WORKERS:-3}"
MAX_PAGES="${MAX_PAGES:-}"                     # empty = no limit
PDF_LIMIT="${PDF_LIMIT:-}"                      # empty = no limit

# KG settings
LLM_PROVIDER="${LLM_PROVIDER:-ollama}"         # ollama | claude | openai | gemini
KG_RESUME="${KG_RESUME:-1}"                    # 1 = resume from checkpoint

# Pipeline stages (1=run, 0=skip)
RUN_EXTRACT="${RUN_EXTRACT:-1}"
RUN_KG="${RUN_KG:-1}"
RUN_RAG_INDEX="${RUN_RAG_INDEX:-1}"

# Services
NEO4J_PASSWORD="${NEO4J_PASSWORD:-password}"
NEO4J_SIF="${NEO4J_SIF:-/scratch/$USER/containers/neo4j.sif}"
OCR_HOST="${OCR_HOST:-localhost}"
OCR_PORT="${OCR_PORT:-8080}"

# GLM-OCR via vLLM on NVIDIA GPU
GLM_OCR_MODEL="${GLM_OCR_MODEL:-zai-org/GLM-OCR}"
GLM_OCR_HF_CACHE="${GLM_OCR_HF_CACHE:-/scratch/$USER/hf_cache}"
GLM_OCR_MAX_LEN="${GLM_OCR_MAX_LEN:-8192}"
GLM_OCR_GPU="${GLM_OCR_GPU:-0}"

# Python conda env name
CONDA_ENV="${CONDA_ENV:-paper_trail_env}"

# vLLM container and Python packages
VLLM_SIF="${VLLM_SIF:-/packages/apps/simg/vllm-nightly-26.03.19.sif}"
PY_PACKAGES="/scratch/$USER/py_packages_transformers"

# ============================
# Setup
# ============================
echo "WORKDIR=$WORKDIR"
ls -ld "$WORKDIR" || exit 1
cd "$WORKDIR"

JOB_ID="${SLURM_JOB_ID:-$$}"
NEO4J_HTTP_PORT="${NEO4J_HTTP_PORT:-$((7474 + SLURM_JOB_ID % 1000))}"
NEO4J_BOLT_PORT="${NEO4J_BOLT_PORT:-$((7687 + SLURM_JOB_ID % 1000))}"
LOGDIR="$WORKDIR/logs/$JOB_ID"
mkdir -p "$LOGDIR"

echo "===== paper_trail_pipeline ====="
echo "Node:         $(hostname)"
echo "SLURM_JOB_ID: ${SLURM_JOB_ID:-}"
echo "DATA_DIR:     $DATA_DIR"
echo "METHOD:       $EXTRACT_METHOD"
echo "LLM_PROVIDER: $LLM_PROVIDER"
echo "Stages:       extract=$RUN_EXTRACT  kg=$RUN_KG  rag=$RUN_RAG_INDEX"
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

# Ensure poppler is available (needed for PDF page count and image conversion)
conda install -y -c conda-forge poppler 2>/dev/null || true

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
            sleep 3
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
    [[ -n "${OCR_PID:-}" ]]   && kill "${OCR_PID}"   2>/dev/null || true
}
trap cleanup EXIT

# ============================
# Start Neo4j via Apptainer
# ============================
SCRATCH_BASE="${SCRATCH:-/scratch/$USER}"
NEO4J_SCRATCH="$SCRATCH_BASE/neo4j/persistent"
mkdir -p "$NEO4J_SCRATCH"/{data,logs,import,plugins}

if ! curl -fsS "http://localhost:${NEO4J_HTTP_PORT}" >/dev/null 2>&1; then
    echo "Starting Neo4j via Apptainer ($NEO4J_SIF)..."
    [[ -f "$NEO4J_SIF" ]] || {
        echo "Neo4j SIF not found. Pulling..."
        mkdir -p "$(dirname "$NEO4J_SIF")"
        apptainer pull "$NEO4J_SIF" docker://neo4j:5-community
    }

    apptainer run \
        --writable-tmpfs \
        --bind "$NEO4J_SCRATCH/data:/data" \
        --bind "$NEO4J_SCRATCH/logs:/logs" \
        --bind "$NEO4J_SCRATCH/plugins:/plugins" \
        --env TINI_SUBREAPER=1 \
        --env NEO4J_AUTH="neo4j/${NEO4J_PASSWORD}" \
        --env NEO4J_server_memory_heap_initial__size=1G \
        --env NEO4J_server_memory_heap_max__size=4G \
        --env NEO4J_server_memory_pagecache__size=2G \
        --env NEO4J_server_http_listen__address="0.0.0.0:${NEO4J_HTTP_PORT}" \
        --env NEO4J_server_bolt_listen__address="0.0.0.0:${NEO4J_BOLT_PORT}" \
        --env NEO4J_server_config_strict__validation_enabled=false \
        "$NEO4J_SIF" \
        > "$LOGDIR/neo4j.log" 2>&1 &
    NEO4J_PID=$!

    wait_for_http "http://localhost:${NEO4J_HTTP_PORT}" "Neo4j HTTP" 300
else
    echo "Neo4j already running on port ${NEO4J_HTTP_PORT}."
fi
export NEO4J_PASSWORD="$NEO4J_PASSWORD"
export NEO4J_URI="bolt://localhost:${NEO4J_BOLT_PORT}"

# ============================
# Start GLM-OCR server via vLLM (only needed for ocr/hybrid)
# ============================
if [[ "$EXTRACT_METHOD" != "native" ]] && [[ "$RUN_EXTRACT" == "1" ]]; then
    if ! curl -fsS "http://${OCR_HOST}:${OCR_PORT}/v1/models" >/dev/null 2>&1; then
        echo "Starting GLM-OCR server ($GLM_OCR_MODEL) via vLLM on CUDA device $GLM_OCR_GPU..."
        mkdir -p "$GLM_OCR_HF_CACHE"

        PYTHONPATH="${PY_PACKAGES}:${PYTHONPATH:-}" \
        HF_HOME="$GLM_OCR_HF_CACHE" \
        CUDA_VISIBLE_DEVICES="$GLM_OCR_GPU" \
        apptainer exec \
            --nv \
            --bind /scratch:/scratch \
            "$VLLM_SIF" \
            vllm serve "$GLM_OCR_MODEL" \
                --host 127.0.0.1 \
                --port "$OCR_PORT" \
                --max-model-len "$GLM_OCR_MAX_LEN" \
                --tensor-parallel-size 1 \
                --trust-remote-code \
        > "$LOGDIR/ocr_server.log" 2>&1 &
        OCR_PID=$!

        wait_for_http "http://${OCR_HOST}:${OCR_PORT}/v1/models" "GLM-OCR vLLM" 1800
        echo "GLM-OCR ready at http://${OCR_HOST}:${OCR_PORT}"
    else
        echo "GLM-OCR server already running."
    fi
fi

export OCR_API_BASE="http://${OCR_HOST}:${OCR_PORT}/v1"

# ============================
# Step 1 — Batch PDF extraction (all corpora)
# ============================
if [[ "$RUN_EXTRACT" == "1" ]]; then
    echo "===== STEP 1: Batch extraction ($EXTRACT_METHOD) ====="

    for corpus_dir in $CORPUS_DIRS; do
        [[ -d "$corpus_dir" ]] || { echo "SKIP (not found): $corpus_dir"; continue; }

        # Derive a slug from the path, e.g. batch2/GHOSTSCRIPT → batch2_ghostscript
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

# Update Neo4j URI in config to match dynamic port
sed -i "s|uri: bolt://localhost:.*|uri: bolt://localhost:${NEO4J_BOLT_PORT}|" \
    "$WORKDIR/config/neo4j.yaml"

if [[ "$RUN_KG" == "1" ]]; then
    echo "===== STEP 2: Knowledge graph ====="

    python3 -m src.cli kg init \
        2>&1 | tee "$LOGDIR/kg_init.log"

    KG_SCRIPT_ARGS=(--all)
    [[ "$KG_RESUME" == "1" ]] && KG_SCRIPT_ARGS+=(--resume)
    KG_SCRIPT_ARGS+=(--llm-provider vllm --llm-base-url "http://${OCR_HOST}:${OCR_PORT}/v1" --llm-model "$GLM_OCR_MODEL")

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

echo "===== DONE. Logs in $LOGDIR ====="
