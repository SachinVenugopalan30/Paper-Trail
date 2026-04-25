#!/bin/bash
#SBATCH --job-name=paper_trail_extract
#SBATCH --partition=htc
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
#SBATCH --gres=gpu:a100:1

# Load shared environment
source "/scratch/$USER/Paper-Trail/common_env.sh"

# ============================
# Start services (OCR only — KG built locally)
# ============================
start_vllm_ocr

# ============================
# Step 1 — Batch PDF extraction (all corpora)
# ============================
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
echo "===== Job 1 DONE. Logs in $LOGDIR ====="
echo "Next: download data/processed/*/results/ and build KG locally."
