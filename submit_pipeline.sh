#!/bin/bash
# submit_pipeline.sh — Submit the two-stage Paper-Trail pipeline to Slurm.
# Run this once from the login node. Job 2 starts automatically only if Job 1 succeeds.
#
# Usage:
#   chmod +x submit_pipeline.sh
#   ./submit_pipeline.sh
#
# To check status:
#   squeue -u $USER
#   sacct -j <JOBID> --format=JobID,JobName,State,ExitCode

set -euo pipefail

echo "Submitting Paper-Trail pipeline..."
echo ""

# Submit Job 1: Extraction only (GPU, 160 GB)
JOB1=$(sbatch job1_extract_kg.sh | awk '{print $NF}')
if [[ -z "$JOB1" ]]; then
    echo "ERROR: Failed to submit Job 1 (extract)."
    exit 1
fi
echo "✓ Job 1 (extract):  $JOB1"

# Submit Job 2: RAG Index (CPU, 32 GB) — depends on Job 1 success
JOB2=$(sbatch --dependency=afterok:"$JOB1" job2_rag_index.sh | awk '{print $NF}')
if [[ -z "$JOB2" ]]; then
    echo "ERROR: Failed to submit Job 2 (RAG index)."
    exit 1
fi
echo "✓ Job 2 (RAG index):  $JOB2"

echo ""
echo "Pipeline submitted successfully!"
echo "Job 2 will start automatically after Job 1 exits with code 0."
echo "KG build is done locally — not on HPC."
echo ""
echo "Monitor with:"
echo "  squeue -u \$USER"
echo "  tail -f paper_trail_extract_kg_${JOB1}.out"
echo "  tail -f paper_trail_rag_index_${JOB2}.out"
