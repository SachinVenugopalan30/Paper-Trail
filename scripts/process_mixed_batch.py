#!/usr/bin/env python3
"""
Mixed Batch PDF Processor - Diverse Selection Edition

Processes PDFs from multiple batches (batch2, batch3, batch4) with guaranteed
diversity across document types. Automatically replaces skipped files to
ensure target count is reached.

Usage:
    # Process 100 PDFs with guaranteed type diversity
    python3 scripts/process_mixed_batch.py --total 100

    # Custom distribution across batches
    python3 scripts/process_mixed_batch.py --total 100 --batch2 30 --batch3 35 --batch4 35

    # Ensure minimum representation per document type
    python3 scripts/process_mixed_batch.py --total 100 --min-per-type 5

    # Preview selection without processing
    python3 scripts/process_mixed_batch.py --total 100 --preview

Features:
    - Guaranteed diversity: minimum files from each document type
    - Automatic replacement: skipped files are replaced from reserve pool
    - Smart pooling: selects 150 PDFs initially, processes until 100 complete
    - Organized output: results saved by batch/type folders
    - Checkpoint support: resume interrupted processing
"""

import argparse
import random
import glob
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Set
from collections import defaultdict
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.extraction.batch_processor import BatchProcessor


def find_pdfs_in_batches() -> Dict[str, List[str]]:
    """Find all PDFs in each batch directory."""
    batches = {
        'batch2': 'data/batch2',
        'batch3': 'data/batch3', 
        'batch4': 'data/batch4'
    }
    
    pdfs_by_batch = {}
    for batch_name, batch_dir in batches.items():
        batch_path = project_root / batch_dir
        if batch_path.exists():
            pdfs = glob.glob(str(batch_path / "**" / "*.pdf"), recursive=True)
            pdfs_by_batch[batch_name] = pdfs
            print(f"  Found {len(pdfs)} PDFs in {batch_name}")
        else:
            print(f"  Warning: {batch_dir} not found")
            pdfs_by_batch[batch_name] = []
    
    return pdfs_by_batch


def get_pdf_type(pdf_path: str) -> Tuple[str, str]:
    """Extract batch and document type from PDF path."""
    path_str = str(pdf_path)
    
    # Determine batch
    if 'batch2' in path_str:
        batch = 'batch2'
    elif 'batch3' in path_str:
        batch = 'batch3'
    elif 'batch4' in path_str:
        batch = 'batch4'
    else:
        batch = 'unknown'
    
    # Determine type from parent folder name
    pdf_path_obj = Path(pdf_path)
    parent = pdf_path_obj.parent.name
    if parent and parent not in ['batch2', 'batch3', 'batch4']:
        doc_type = parent
    else:
        # Fallback to filename
        filename = pdf_path_obj.name
        if '-' in filename:
            doc_type = filename.split('-')[0]
        else:
            doc_type = 'unknown'
    
    return batch, doc_type


def organize_pdfs_by_type(pdfs_by_batch: Dict[str, List[str]]) -> Dict[Tuple[str, str], List[str]]:
    """Organize PDFs by (batch, type) tuple."""
    organized = defaultdict(list)
    
    for batch_name, pdfs in pdfs_by_batch.items():
        for pdf in pdfs:
            batch, doc_type = get_pdf_type(pdf)
            if batch != 'unknown':
                organized[(batch, doc_type)].append(pdf)
    
    return dict(organized)


def select_diverse_pdfs(
    pdfs_by_type: Dict[Tuple[str, str], List[str]],
    target_total: int = 100,
    min_per_type: int = 2,
    reserve_multiplier: float = 1.5,
    seed: int = 42
) -> Tuple[List[str], List[str]]:
    """
    Select PDFs with guaranteed diversity across types.
    
    Returns:
        Tuple of (primary_selection, reserve_pool)
        Primary: Target number of PDFs with diversity guarantee
        Reserve: Additional PDFs to replace skipped files
    """
    random.seed(seed)
    
    total_pool_size = int(target_total * reserve_multiplier)
    primary_count = target_total
    reserve_count = total_pool_size - target_total
    
    selected = []
    used_pdfs = set()
    
    # First pass: ensure minimum from each type
    print(f"\n  Ensuring minimum {min_per_type} files per type...")
    for (batch, doc_type), pdfs in sorted(pdfs_by_type.items()):
        if len(pdfs) >= min_per_type:
            type_selected = random.sample(pdfs, min_per_type)
            selected.extend(type_selected)
            used_pdfs.update(type_selected)
            print(f"    {batch}/{doc_type}: {min_per_type} files")
        else:
            # Take all available if fewer than minimum
            selected.extend(pdfs)
            used_pdfs.update(pdfs)
            print(f"    {batch}/{doc_type}: {len(pdfs)} files (all available)")
    
    # Second pass: fill remaining slots randomly from unused PDFs
    remaining_slots = primary_count - len(selected)
    
    if remaining_slots > 0:
        print(f"\n  Filling remaining {remaining_slots} slots randomly...")
        
        # Collect all unused PDFs
        all_unused = []
        for pdfs in pdfs_by_type.values():
            for pdf in pdfs:
                if pdf not in used_pdfs:
                    all_unused.append(pdf)
        
        # Randomly select to fill remaining slots
        if len(all_unused) >= remaining_slots:
            additional = random.sample(all_unused, remaining_slots)
            selected.extend(additional)
            used_pdfs.update(additional)
        else:
            # Take all available if not enough
            selected.extend(all_unused)
            used_pdfs.update(all_unused)
            print(f"  Warning: Only {len(all_unused)} additional PDFs available")
    
    # Third pass: create reserve pool
    reserve = []
    all_remaining = []
    for pdfs in pdfs_by_type.values():
        for pdf in pdfs:
            if pdf not in used_pdfs:
                all_remaining.append(pdf)
    
    reserve_size = min(reserve_count, len(all_remaining))
    if reserve_size > 0:
        reserve = random.sample(all_remaining, reserve_size)
    
    # Shuffle primary selection
    random.shuffle(selected)
    
    return selected, reserve


def process_with_replacement(
    primary_pdfs: List[str],
    reserve_pdfs: List[str],
    base_output_dir: str = 'data/processed',
    target_count: int = 100,
    max_pages: int = 5,
    parallel_workers: int = 3,
    save_images: bool = True
) -> Dict:
    """
    Process PDFs with automatic replacement for skipped files.
    
    Returns:
        Dict with final statistics
    """
    print(f"\n{'='*70}")
    print(f"Processing with Auto-Replacement")
    print(f"Target: {target_count} successful PDFs")
    print(f"Primary pool: {len(primary_pdfs)} PDFs")
    print(f"Reserve pool: {len(reserve_pdfs)} PDFs")
    print(f"{'='*70}")
    
    # Organize by type for efficient processing
    all_pdfs = primary_pdfs + reserve_pdfs
    groups = defaultdict(list)
    for pdf in all_pdfs:
        batch, doc_type = get_pdf_type(pdf)
        groups[(batch, doc_type)].append(pdf)
    
    processed_pdfs = []
    skipped_pdfs = []
    failed_pdfs = []
    
    total_stats = {
        'processed': 0,
        'failed': 0,
        'skipped': 0,
        'replaced': 0
    }
    
    # Process each group
    for (batch, doc_type), group_pdfs in sorted(groups.items()):
        output_dir = f"{base_output_dir}/{batch}/{doc_type}"
        
        print(f"\n{'='*70}")
        print(f"Group: {batch}/{doc_type}")
        print(f"PDFs in group: {len(group_pdfs)}")
        print(f"{'='*70}")
        
        # Separate primary from reserve in this group
        group_primary = [p for p in group_pdfs if p in primary_pdfs]
        group_reserve = [p for p in group_pdfs if p in reserve_pdfs]
        
        # Process primary PDFs
        if group_primary:
            processor = BatchProcessor(
                output_dir=output_dir,
                checkpoint_path=f'{output_dir}/checkpoint.json',
                project_name=f'{batch}_{doc_type}',
                max_pages=max_pages,
                parallel_workers=parallel_workers,
                save_images=save_images
            )
            
            results = processor.process_batch(pdf_paths=group_primary)
            
            # Track results
            for pdf, result in zip(group_primary, results):
                if result.get('status') == 'complete':
                    processed_pdfs.append(pdf)
                    total_stats['processed'] += 1
                elif result.get('status') == 'skipped':
                    skipped_pdfs.append(pdf)
                    total_stats['skipped'] += 1
                elif result.get('status') == 'error':
                    failed_pdfs.append(pdf)
                    total_stats['failed'] += 1
            
            print(f"  Group results: {len(processed_pdfs)} processed, {len(skipped_pdfs)} skipped, {len(failed_pdfs)} failed")
    
    # Now replace skipped files from reserve pool
    while len(processed_pdfs) < target_count and reserve_pdfs:
        needed = target_count - len(processed_pdfs)
        available = len(reserve_pdfs)
        to_replace = min(needed, available)
        
        if to_replace == 0:
            break
        
        print(f"\n{'='*70}")
        print(f"Replacement Round")
        print(f"Need {needed} more PDFs, {available} in reserve")
        print(f"{'='*70}")
        
        # Get replacement PDFs
        replacements = reserve_pdfs[:to_replace]
        reserve_pdfs = reserve_pdfs[to_replace:]
        
        # Group replacements by type
        replacement_groups = defaultdict(list)
        for pdf in replacements:
            batch, doc_type = get_pdf_type(pdf)
            replacement_groups[(batch, doc_type)].append(pdf)
        
        # Process replacements
        for (batch, doc_type), group_pdfs in replacement_groups.items():
            output_dir = f"{base_output_dir}/{batch}/{doc_type}"
            
            processor = BatchProcessor(
                output_dir=output_dir,
                checkpoint_path=f'{output_dir}/checkpoint.json',
                project_name=f'{batch}_{doc_type}_replacement',
                max_pages=max_pages,
                parallel_workers=parallel_workers,
                save_images=save_images
            )
            
            results = processor.process_batch(pdf_paths=group_pdfs)
            
            for pdf, result in zip(group_pdfs, results):
                if result.get('status') == 'complete':
                    processed_pdfs.append(pdf)
                    total_stats['processed'] += 1
                    total_stats['replaced'] += 1
                elif result.get('status') == 'skipped':
                    skipped_pdfs.append(pdf)
                    total_stats['skipped'] += 1
                elif result.get('status') == 'error':
                    failed_pdfs.append(pdf)
                    total_stats['failed'] += 1
    
    # Final summary
    print(f"\n{'='*70}")
    print("FINAL RESULTS")
    print(f"{'='*70}")
    print(f"  Successfully processed: {len(processed_pdfs)} PDFs")
    print(f"    (Target was: {target_count})")
    print(f"  Skipped: {total_stats['skipped']} PDFs")
    print(f"  Failed: {total_stats['failed']} PDFs")
    print(f"  Replaced: {total_stats['replaced']} PDFs from reserve")
    print(f"\n  Results saved to: {base_output_dir}/")
    print(f"  Organized by: batch/type/results/")
    
    if len(processed_pdfs) < target_count:
        print(f"\n  ⚠️  Warning: Only {len(processed_pdfs)}/{target_count} PDFs processed successfully")
        print(f"     Consider increasing --pool-size or checking max-pages limit")
    else:
        print(f"\n  ✓ Target reached: {len(processed_pdfs)} PDFs")
    
    return total_stats


def save_pdf_list(pdfs: List[str], output_file: Path):
    """Save list of PDFs to file."""
    with open(output_file, 'w') as f:
        for pdf in pdfs:
            f.write(pdf + '\n')


def load_pdf_list(input_file: Path) -> List[str]:
    """Load PDF list from file."""
    with open(input_file) as f:
        return [line.strip() for line in f if line.strip()]


def count_types_in_list(pdfs: List[str]) -> Dict[Tuple[str, str], int]:
    """Count PDFs by (batch, type)."""
    counts = defaultdict(int)
    for pdf in pdfs:
        batch, doc_type = get_pdf_type(pdf)
        counts[(batch, doc_type)] += 1
    return dict(counts)


def main():
    parser = argparse.ArgumentParser(
        description='Process mixed PDF batches with guaranteed type diversity',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process 100 PDFs with diversity guarantee
  python3 scripts/process_mixed_batch.py --total 100

  # Ensure at least 5 files from each document type
  python3 scripts/process_mixed_batch.py --total 100 --min-per-type 5

  # Custom batch distribution
  python3 scripts/process_mixed_batch.py --batch2 30 --batch3 35 --batch4 35

  # Preview selection
  python3 scripts/process_mixed_batch.py --total 100 --preview
        """
    )
    
    parser.add_argument('--total', type=int, default=100,
                       help='Target number of PDFs to successfully process (default: 100)')
    parser.add_argument('--min-per-type', type=int, default=2,
                       help='Minimum files to select from each document type (default: 2)')
    parser.add_argument('--pool-size', type=float, default=1.5,
                       help='Multiplier for initial pool size (default: 1.5 = 150 PDFs for 100 target)')
    parser.add_argument('--batch2', type=int, default=None,
                       help='Number of PDFs from batch2 (default: auto-distribute)')
    parser.add_argument('--batch3', type=int, default=None,
                       help='Number of PDFs from batch3 (default: auto-distribute)')
    parser.add_argument('--batch4', type=int, default=None,
                       help='Number of PDFs from batch4 (default: auto-distribute)')
    parser.add_argument('--from-list', type=str, default=None,
                       help='Process PDFs from existing list file')
    parser.add_argument('--save-list', type=str, default='data/mixed_batch_selected.txt',
                       help='Save selected PDF list to this file')
    parser.add_argument('--preview', action='store_true',
                       help='Preview selection without processing')
    parser.add_argument('--seed', type=int, default=42,
                       help='Random seed (default: 42)')
    parser.add_argument('--max-pages', type=int, default=5,
                       help='Maximum pages per PDF (default: 5)')
    parser.add_argument('--workers', type=int, default=3,
                       help='Parallel workers (default: 3)')
    parser.add_argument('--base-output-dir', type=str, default='data/processed',
                       help='Base output directory (default: data/processed)')
    parser.add_argument('--no-images', action='store_true',
                       help='Do not save images')
    
    args = parser.parse_args()
    
    print("="*70)
    print("Mixed Batch PDF Processor - Diverse Selection")
    print("="*70)
    print(f"Target: {args.total} successful PDFs")
    print(f"Min per type: {args.min_per_type} files")
    print(f"Pool multiplier: {args.pool_size}x")
    
    if args.from_list:
        # Load from existing list
        print(f"\nLoading from: {args.from_list}")
        all_pdfs = load_pdf_list(Path(args.from_list))
        
        # Split into primary and reserve (first N are primary)
        primary_count = int(args.total * args.pool_size)
        primary_pdfs = all_pdfs[:args.total]
        reserve_pdfs = all_pdfs[args.total:]
        
        print(f"  Loaded {len(all_pdfs)} PDFs")
        print(f"  Primary: {len(primary_pdfs)}, Reserve: {len(reserve_pdfs)}")
    else:
        # Select new PDFs
        print("\nScanning batch directories...")
        pdfs_by_batch = find_pdfs_in_batches()
        
        print("\nOrganizing by document type...")
        pdfs_by_type = organize_pdfs_by_type(pdfs_by_batch)
        
        print(f"\nFound {len(pdfs_by_type)} document types:")
        for (batch, doc_type), pdfs in sorted(pdfs_by_type.items()):
            print(f"  {batch}/{doc_type}: {len(pdfs)} PDFs")
        
        print(f"\nSelecting diverse PDFs...")
        primary_pdfs, reserve_pdfs = select_diverse_pdfs(
            pdfs_by_type,
            target_total=args.total,
            min_per_type=args.min_per_type,
            reserve_multiplier=args.pool_size,
            seed=args.seed
        )
        
        # Save the lists
        save_pdf_list(primary_pdfs + reserve_pdfs, Path(args.save_list))
        
        print(f"\nSelected {len(primary_pdfs)} primary + {len(reserve_pdfs)} reserve = {len(primary_pdfs) + len(reserve_pdfs)} total")
        
        # Show type distribution
        print(f"\nType distribution in selection:")
        type_counts = count_types_in_list(primary_pdfs)
        for (batch, doc_type), count in sorted(type_counts.items()):
            print(f"  {batch}/{doc_type}: {count} files")
    
    if args.preview:
        print(f"\n{'='*70}")
        print("PREVIEW MODE - Primary Selection:")
        print(f"{'='*70}")
        for i, pdf in enumerate(primary_pdfs[:15], 1):
            batch, doc_type = get_pdf_type(pdf)
            print(f"  {i}. [{batch}/{doc_type}] {Path(pdf).name}")
        if len(primary_pdfs) > 15:
            print(f"  ... and {len(primary_pdfs) - 15} more")
        print(f"\nReserve pool: {len(reserve_pdfs)} PDFs ready for replacement")
        print("\nUse without --preview to process")
        return
    
    # Confirm before processing
    if not args.from_list:
        response = input(f"\nProcess {len(primary_pdfs)} PDFs with {len(reserve_pdfs)} replacements? [Y/n]: ").strip().lower()
        if response and response not in ['y', 'yes']:
            print("Cancelled.")
            return
    
    # Process with replacement
    stats = process_with_replacement(
        primary_pdfs=primary_pdfs,
        reserve_pdfs=reserve_pdfs,
        base_output_dir=args.base_output_dir,
        target_count=args.total,
        max_pages=args.max_pages,
        parallel_workers=args.workers,
        save_images=not args.no_images
    )


if __name__ == '__main__':
    main()
