#!/bin/bash
#SBATCH --job-name=paper_trail_rag_index
#SBATCH --partition=htc
#SBATCH --account=class_cse573spring2026
#SBATCH --qos=class

# Resource Allocation (CPU only)
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=02:00:00

# Output files
#SBATCH --output=%x_%j.out
#SBATCH --error=%x_%j.err

# No GPU needed for RAG indexing

# Load shared environment
source "/scratch/$USER/Paper-Trail/common_env.sh"

# ============================
# Step 3 — Build RAG index
# ============================
echo "===== STEP 3: RAG index ====="

python3 -m src.cli rag index \
    2>&1 | tee "$LOGDIR/rag_index.log"

python3 -m src.cli rag stats \
    2>&1 | tee "$LOGDIR/rag_stats.log"

echo "===== Job 2 DONE. Logs in $LOGDIR ====="
echo "Artifacts to copy to local machine:"
echo "  ChromaDB:    $WORKDIR/data/rag/chromadb/"
echo "  BM25 index:  $WORKDIR/data/rag/bm25_index.json"
echo "  Result JSONs: $WORKDIR/data/processed/*/results/"
