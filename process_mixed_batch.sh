#!/bin/bash
# Process mixed batch of 100 PDFs from all 3 batches

PROJECT_DIR="/Users/sachin/Desktop/Uni Courses/CSE 573 - SWM/2Project"
cd "$PROJECT_DIR"

echo "=========================================="
echo "Processing Mixed Batch (100 PDFs)"
echo "=========================================="

# First, select random PDFs from each batch
python3 << 'EOF'
import random
import glob
from pathlib import Path

random.seed(42)

# Find PDFs from each batch
batch2_pdfs = glob.glob("data/batch2/**/*.pdf", recursive=True)
batch3_pdfs = glob.glob("data/batch3/**/*.pdf", recursive=True)  
batch4_pdfs = glob.glob("data/batch4/**/*.pdf", recursive=True)

print(f"Available: Batch 2: {len(batch2_pdfs)}, Batch 3: {len(batch3_pdfs)}, Batch 4: {len(batch4_pdfs)}")

# Select mix
selected = []
selected.extend(random.sample(batch2_pdfs, 33))
selected.extend(random.sample(batch3_pdfs, 33))
selected.extend(random.sample(batch4_pdfs, 34))
random.shuffle(selected)

# Save list
with open("/tmp/mixed_batch_100.txt", "w") as f:
    for pdf in selected:
        f.write(pdf + "\n")

print(f"Selected 100 PDFs: 33 from Batch 2, 33 from Batch 3, 34 from Batch 4")
print("File list saved to: /tmp/mixed_batch_100.txt")
EOF

# Now process each batch separately with the selected files
echo ""
echo "Processing Batch 2 (33 PDFs)..."
python3 << 'EOF'
import subprocess

with open("/tmp/mixed_batch_100.txt") as f:
    all_pdfs = [line.strip() for line in f if line.strip()]

batch2_pdfs = [p for p in all_pdfs if "batch2" in p][:33]

if batch2_pdfs:
    print(f"Processing {len(batch2_pdfs)} PDFs from Batch 2...")
    for pdf in batch2_pdfs:
        # Process single file
        subprocess.run([
            "python3", "-m", "src.cli", "extract", pdf,
            "--method", "hybrid",
            "--output", f"data/processed/mozilla/results/{Path(pdf).stem}_results.json",
            "--threshold", "0.8"
        ])
EOF

echo ""
echo "Processing Batch 3 (33 PDFs)..."
python3 << 'EOF'
import subprocess

with open("/tmp/mixed_batch_100.txt") as f:
    all_pdfs = [line.strip() for line in f if line.strip()]

batch3_pdfs = [p for p in all_pdfs if "batch3" in p][:33]

if batch3_pdfs:
    print(f"Processing {len(batch3_pdfs)} PDFs from Batch 3...")
    for pdf in batch3_pdfs:
        subprocess.run([
            "python3", "-m", "src.cli", "extract", pdf,
            "--method", "hybrid", 
            "--output", f"data/processed/mozilla/results/{Path(pdf).stem}_results.json",
            "--threshold", "0.8"
        ])
EOF

echo ""
echo "Processing Batch 4 (34 PDFs)..."
python3 << 'EOF'
import subprocess

with open("/tmp/mixed_batch_100.txt") as f:
    all_pdfs = [line.strip() for line in f if line.strip()]

batch4_pdfs = [p for p in all_pdfs if "batch4" in p][:34]

if batch4_pdfs:
    print(f"Processing {len(batch4_pdfs)} PDFs from Batch 4...")
    for pdf in batch4_pdfs:
        subprocess.run([
            "python3", "-m", "src.cli", "extract", pdf,
            "--method", "hybrid",
            "--output", f"data/processed/mozilla/results/{Path(pdf).stem}_results.json", 
            "--threshold", "0.8"
        ])
EOF

echo ""
echo "=========================================="
echo "Mixed batch processing complete!"
echo "=========================================="
ls -1 data/processed/mozilla/results/*_results.json | wc -l | xargs echo "Total result files:"
