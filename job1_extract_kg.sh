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
# Step 1 — Batch PDF extraction (chunked to prevent C-extension memory leaks)
# ============================
echo "===== STEP 1: Batch extraction ($EXTRACT_METHOD) ====="

# Memory logger
log_memory() {
    local tag="${1:-unknown}"
    echo "[MEMORY] $(date +%H:%M:%S)  tag=$tag  $(ps -o pid,rss,comm --no-headers --pid $$ | awk '{print "Python_RSS_MB=" $2/1024}')" >> "$LOGDIR/memory.log"
}

CHUNK_SIZE=150

for corpus_dir in $CORPUS_DIRS; do
    [[ -d "$corpus_dir" ]] || { echo "SKIP (not found): $corpus_dir"; continue; }

    corpus_slug=$(echo "$corpus_dir" | sed "s|$DATA_DIR/||" | tr '/' '_' | tr '[:upper:]' '[:lower:]')
    out_dir="$DATA_DIR/processed/$corpus_slug"
    checkpoint="$out_dir/checkpoint.json"
    mkdir -p "$out_dir"

    # Count total PDFs once
    total_pdfs=$(find "$corpus_dir" -maxdepth 1 -name '*.pdf' | wc -l)
    echo "--- Extracting: $corpus_dir → $out_dir ($total_pdfs total PDFs) ---"

    chunk=0
    while true; do
        chunk=$((chunk + 1))
        echo "--- Chunk $chunk (max $CHUNK_SIZE PDFs) ---"
        log_memory "before_chunk_${chunk}"

        EXTRACT_ARGS=(
            extract-batch "$corpus_dir"
            --method "$EXTRACT_METHOD"
            --parallel "$PARALLEL_WORKERS"
            --output-dir "$out_dir"
            --checkpoint "$checkpoint"
            --limit "$CHUNK_SIZE"
        )
        [[ -n "$MAX_PAGES" ]] && EXTRACT_ARGS+=(--max-pages "$MAX_PAGES")

        python3 -m src.cli "${EXTRACT_ARGS[@]}" \
            2>&1 | tee -a "$LOGDIR/extract_${corpus_slug}.log"

        log_memory "after_chunk_${chunk}"

        # Check if everything is tracked in checkpoint
        tracked=$(python3 -c "
import json, sys, os
cp_path = '$checkpoint'
if not os.path.exists(cp_path):
    sys.exit(1)
cp = json.load(open(cp_path))
total = len(cp.get('processed_files',{})) + len(cp.get('failed_files',{})) + len(cp.get('skipped_files',{}))
print(total)
")
        echo "Checkpoint tracked: $tracked / $total_pdfs"

        if [[ "$tracked" -ge "$total_pdfs" ]]; then
            echo "All $total_pdfs PDFs tracked in checkpoint. Done with $corpus_dir."
            break
        fi

        echo "More PDFs remaining. Restarting Python for next chunk..."
    done

done

echo "All corpora extracted."
echo "===== Job 1 DONE. Logs in $LOGDIR ====="
echo "Next: download data/processed/*/results/ and build KG locally."
