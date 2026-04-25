#!/bin/bash
# Common environment and helper functions for Paper-Trail Slurm jobs.
# Sourced by job1_extract_kg.sh and job2_rag_index.sh — do not run directly.

set -euo pipefail
set -x
trap 'echo "FAILED at line $LINENO with exit code $?"' ERR

# ============================
# USER SETTINGS (override with sbatch --export=ALL,...)
# ============================
WORKDIR="${WORKDIR:-/scratch/$USER/Paper-Trail}"
DATA_DIR="${DATA_DIR:-"$WORKDIR/data"}"

# Per-person batch assignments (override CORPUS_DIRS before submitting):
#   Sachin (default): batch2/GHOSTSCRIPT + batch2/TIKA
#   Teammate 2:  CORPUS_DIRS="$DATA_DIR/batch3/MOZILLA" ./submit_pipeline.sh
#   Teammate 3:  CORPUS_DIRS="$DATA_DIR/batch4/LIBRE_OFFICE $DATA_DIR/batch4/OOO $DATA_DIR/batch4/pdf.js" ./submit_pipeline.sh
CORPUS_DIRS="${CORPUS_DIRS:-
    $DATA_DIR/batch2/GHOSTSCRIPT
    $DATA_DIR/batch2/TIKA
}"

# Extraction settings
EXTRACT_METHOD="${EXTRACT_METHOD:-hybrid}"
PARALLEL_WORKERS="${PARALLEL_WORKERS:-3}"
MAX_PAGES="${MAX_PAGES:-5}"
PDF_LIMIT="${PDF_LIMIT:-}"

# Services
NEO4J_PASSWORD="${NEO4J_PASSWORD:-password}"
NEO4J_SIF="${NEO4J_SIF:-/scratch/$USER/containers/neo4j.sif}"
OCR_HOST="${OCR_HOST:-localhost}"
OCR_PORT="${OCR_PORT:-8080}"

# GLM-OCR via vLLM on NVIDIA GPU
GLM_OCR_MODEL="${GLM_OCR_MODEL:-zai-org/GLM-OCR}"
GLM_OCR_HF_CACHE="${GLM_OCR_HF_CACHE:-/scratch/$USER/hf_cache}"
GLM_OCR_MAX_LEN="${GLM_OCR_MAX_LEN:-16384}"
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
NEO4J_HTTP_PORT="${NEO4J_HTTP_PORT:-$((7474 + JOB_ID % 10000))}"
NEO4J_BOLT_PORT="${NEO4J_BOLT_PORT:-$((7687 + JOB_ID % 10000))}"
LOGDIR="$WORKDIR/logs/$JOB_ID"
mkdir -p "$LOGDIR"

echo "===== paper_trail_pipeline ====="
echo "Node:         $(hostname)"
echo "SLURM_JOB_ID: ${SLURM_JOB_ID:-}"
echo "DATA_DIR:     $DATA_DIR"
echo "METHOD:       $EXTRACT_METHOD"
echo "Stages:       extract=1  kg=0  rag=0 (KG built locally)"
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
start_neo4j() {
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
}

# ============================
# Start GLM-OCR server via vLLM
# ============================
start_vllm_ocr() {
    if [[ "$EXTRACT_METHOD" != "native" ]]; then
        if ! curl -fsS "http://${OCR_HOST}:${OCR_PORT}/v1/models" >/dev/null 2>&1; then
            echo "Starting GLM-OCR server ($GLM_OCR_MODEL) via vLLM on CUDA device $GLM_OCR_GPU..."
            mkdir -p "$GLM_OCR_HF_CACHE"

            HF_HOME="$GLM_OCR_HF_CACHE" \
            CUDA_VISIBLE_DEVICES="$GLM_OCR_GPU" \
            apptainer exec \
                --nv \
                --bind /scratch:/scratch \
                --env PYTHONPATH="$PY_PACKAGES:${PYTHONPATH:-}" \
                "$VLLM_SIF" \
                vllm serve "$GLM_OCR_MODEL" \
                    --host 127.0.0.1 \
                    --port "$OCR_PORT" \
                    --max-model-len "$GLM_OCR_MAX_LEN" \
                    --tensor-parallel-size 1 \
                    --trust-remote-code \
                    --gpu-memory-utilization 0.80 \
            > "$LOGDIR/ocr_server.log" 2>&1 &
            OCR_PID=$!

            wait_for_http "http://${OCR_HOST}:${OCR_PORT}/v1/models" "GLM-OCR vLLM" 1800
            echo "GLM-OCR ready at http://${OCR_HOST}:${OCR_PORT}"
        else
            echo "GLM-OCR server already running."
        fi
    fi
    export OCR_API_BASE="http://${OCR_HOST}:${OCR_PORT}/v1"
}
