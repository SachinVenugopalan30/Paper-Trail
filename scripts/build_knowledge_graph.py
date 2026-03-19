#!/usr/bin/env python3
"""
Knowledge Graph Builder for PDF Documents

Processes PDF extraction results and builds a Neo4j knowledge graph with entities
and relationships extracted using LLM.

Usage:
    # Process all result files (recommended first 15 pages per PDF)
    python3 scripts/build_knowledge_graph.py --all

    # Process with custom page limit
    python3 scripts/build_knowledge_graph.py --all --max-pages 10

    # Test single PDF
    python3 scripts/build_knowledge_graph.py --test data/processed/batch3/MOZILLA/results/XXX_results.json

    # Resume from checkpoint
    python3 scripts/build_knowledge_graph.py --all --resume

Features:
    - Discovers all result files from data/processed/*/*/results/
    - Parallel processing with 3 workers
    - Per-page entity extraction (not combined)
    - Checkpoint/resume capability
    - Automatic replacement of failed files
    - Progress bar and detailed stats
"""

import argparse
import json
import glob
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from datetime import datetime
from tqdm import tqdm
import sys
import time

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.llm import get_client, EntityExtractionChain
from src.kg import get_client as get_kg_client, BulkImporter
from src.llm.chains import ExtractionResult


@dataclass
class CheckpointEntry:
    """Single checkpoint entry for a PDF."""
    pdf_path: str
    status: str  # 'pending', 'processing', 'completed', 'failed', 'skipped'
    pages_processed: int = 0
    total_pages: int = 0
    entities_created: int = 0
    relations_created: int = 0
    error_message: str = ""
    processed_at: str = ""


class KGCheckpoint:
    """Checkpoint manager for KG building process."""
    
    def __init__(self, checkpoint_path: str = "data/processed/kg_checkpoint.json"):
        self.checkpoint_path = Path(checkpoint_path)
        self.entries: Dict[str, CheckpointEntry] = {}
        self._load()
    
    def _load(self):
        """Load checkpoint from file."""
        if self.checkpoint_path.exists():
            try:
                with open(self.checkpoint_path, 'r') as f:
                    data = json.load(f)
                    for key, entry_data in data.items():
                        self.entries[key] = CheckpointEntry(**entry_data)
                print(f"Loaded checkpoint: {len(self.entries)} entries")
            except Exception as e:
                print(f"Warning: Could not load checkpoint: {e}")
    
    def _save(self):
        """Save checkpoint to file."""
        data = {k: asdict(v) for k, v in self.entries.items()}
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.checkpoint_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def is_completed(self, pdf_path: str) -> bool:
        """Check if PDF has been completed."""
        key = str(pdf_path)
        if key in self.entries:
            return self.entries[key].status == 'completed'
        return False
    
    def is_failed(self, pdf_path: str) -> bool:
        """Check if PDF has failed."""
        key = str(pdf_path)
        if key in self.entries:
            return self.entries[key].status == 'failed'
        return False

    def is_skipped(self, pdf_path: str) -> bool:
        """Check if PDF was skipped (no usable content)."""
        key = str(pdf_path)
        if key in self.entries:
            return self.entries[key].status == 'skipped'
        return False
    
    def mark_processing(self, pdf_path: str, total_pages: int):
        """Mark PDF as currently processing."""
        self.entries[str(pdf_path)] = CheckpointEntry(
            pdf_path=str(pdf_path),
            status='processing',
            total_pages=total_pages
        )
        self._save()
    
    def mark_completed(self, pdf_path: str, entities: int, relations: int):
        """Mark PDF as completed."""
        key = str(pdf_path)
        if key in self.entries:
            self.entries[key].status = 'completed'
            self.entries[key].entities_created = entities
            self.entries[key].relations_created = relations
            self.entries[key].processed_at = datetime.now().isoformat()
            self._save()
    
    def mark_failed(self, pdf_path: str, error: str):
        """Mark PDF as failed."""
        key = str(pdf_path)
        if key in self.entries:
            self.entries[key].status = 'failed'
            self.entries[key].error_message = error
        else:
            self.entries[key] = CheckpointEntry(
                pdf_path=str(pdf_path),
                status='failed',
                error_message=error
            )
        self._save()
    
    def get_stats(self) -> Dict:
        """Get checkpoint statistics."""
        stats = {'completed': 0, 'failed': 0, 'processing': 0, 'pending': 0}
        for entry in self.entries.values():
            stats[entry.status] = stats.get(entry.status, 0) + 1
        return stats
    
    def reset(self):
        """Clear all checkpoint entries."""
        self.entries = {}
        self._save()


def find_all_result_files() -> List[Path]:
    """Find all result files from processed directories."""
    pattern = "data/processed/*/*/results/*_results.json"
    files = list(Path(project_root).glob(pattern))
    return sorted(files)


def process_single_pdf(
    result_file: Path,
    llm_client,
    kg_client,
    extraction_chain: EntityExtractionChain,
    max_pages: int = 15,
    checkpoint: Optional[KGCheckpoint] = None
) -> Tuple[int, int, str]:
    """
    Process a single PDF result file.
    
    Returns:
        Tuple of (entities_created, relations_created, status)
    """
    try:
        # Load result data
        with open(result_file, 'r') as f:
            data = json.load(f)
        
        total_pages = data.get('total_pages', 0)
        pages_to_process = min(max_pages, total_pages)
        
        # Mark as processing in checkpoint
        if checkpoint:
            checkpoint.mark_processing(result_file, pages_to_process)
        
        all_results = []

        # Parse document metadata from filename: GHOSTSCRIPT-687111-2_results.json
        stem = result_file.stem  # e.g. GHOSTSCRIPT-687111-2_results
        doc_stem = stem.replace("_results", "")  # e.g. GHOSTSCRIPT-687111-2
        parts = doc_stem.split("-")
        source_tracker = parts[0] if parts else ""
        source_bug_id = parts[1] if len(parts) > 1 else ""

        # Process each page
        for i, page in enumerate(data.get('pages', [])[:pages_to_process], 1):
            # Get text - prefer OCR if available and longer
            native_text = page.get('native', {}).get('text', '')
            ocr_text = page.get('ocr', {}).get('text', '')

            text = ocr_text if len(ocr_text) > len(native_text) else native_text

            if not text or len(text.strip()) < 50:  # Skip very short pages
                continue

            # Limit text length for speed (first 8000 chars)
            text_to_process = text[:8000]
            page_doc_id = f"{doc_stem}_page_{i}"

            try:
                # Extract entities
                result = extraction_chain.extract(
                    text=text_to_process,
                    document_id=page_doc_id
                )

                # Inject filename-derived metadata into the Document entity
                for entity in result.entities:
                    if entity.type == "Document" and entity.name == page_doc_id:
                        entity.properties.setdefault("source_tracker", source_tracker)
                        entity.properties.setdefault("source_bug_id", source_bug_id)
                        entity.properties.setdefault("doc_id", page_doc_id)
                        break
                
                if result.entities:
                    all_results.append(result)
                    
            except Exception as e:
                # Log error but continue with other pages
                print(f"    Warning: Error on page {i}: {e}")
                continue
        
        # Import to Neo4j
        if all_results:
            importer = BulkImporter(client=kg_client, batch_size=100)
            for result in all_results:
                importer.import_extraction_result(result)

            total_entities = sum(len(r.entities) for r in all_results)
            total_relations = sum(len(r.relations) for r in all_results)

            # Mark as completed
            if checkpoint:
                checkpoint.mark_completed(result_file, total_entities, total_relations)

            return total_entities, total_relations, 'completed'
        else:
            # No usable text in any page — mark as skipped so --resume ignores it
            if checkpoint:
                key = str(result_file)
                checkpoint.entries[key] = CheckpointEntry(
                    pdf_path=key,
                    status='skipped',
                    error_message="No usable text content (all pages < 50 chars)",
                    processed_at=datetime.now().isoformat(),
                )
                checkpoint._save()
            return 0, 0, 'skipped'
            
    except Exception as e:
        error_msg = str(e)
        if checkpoint:
            checkpoint.mark_failed(result_file, error_msg)
        return 0, 0, f'error: {error_msg}'


def process_all_pdfs(
    result_files: List[Path],
    max_pages: int = 15,
    parallel_workers: int = 3,
    checkpoint: Optional[KGCheckpoint] = None,
    resume: bool = False
) -> Dict:
    """
    Process all PDFs with parallel workers.
    
    Returns:
        Dict with processing statistics
    """
    # Filter out completed/skipped files if resuming
    if resume and checkpoint:
        files_to_process = [
            f for f in result_files
            if not checkpoint.is_completed(f) and not checkpoint.is_skipped(f)
        ]
        print(f"Resuming: {len(files_to_process)} of {len(result_files)} PDFs remaining")
    else:
        files_to_process = result_files
        if checkpoint:
            checkpoint.reset()
    
    # Initialize clients (will be shared across workers)
    print("\nInitializing LLM and Neo4j clients...")
    llm_client = get_client()
    kg_client = get_kg_client()
    
    if not kg_client.connect():
        print("ERROR: Failed to connect to Neo4j")
        return {'error': 'Neo4j connection failed'}
    
    extraction_chain = EntityExtractionChain(
        llm_client=llm_client,
        min_confidence=0.6,
        enable_fallback=True
    )
    
    print(f"✓ Connected to Neo4j")
    print(f"Processing {len(files_to_process)} PDFs with {parallel_workers} workers...\n")
    
    # Process in parallel
    total_entities = 0
    total_relations = 0
    completed = 0
    failed = 0
    
    with ThreadPoolExecutor(max_workers=parallel_workers) as executor:
        # Submit all tasks
        future_to_file = {
            executor.submit(
                process_single_pdf,
                pdf_file,
                llm_client,
                kg_client,
                extraction_chain,
                max_pages,
                checkpoint
            ): pdf_file for pdf_file in files_to_process
        }
        
        # Process completed tasks with progress bar
        with tqdm(total=len(files_to_process), desc="Processing PDFs") as pbar:
            for future in as_completed(future_to_file):
                pdf_file = future_to_file[future]
                try:
                    entities, relations, status = future.result()
                    total_entities += entities
                    total_relations += relations
                    
                    if status == 'completed':
                        completed += 1
                    elif status == 'skipped':
                        pass  # don't count as failed
                    else:
                        failed += 1
                        
                    # Update progress bar
                    pbar.set_postfix({
                        'entities': total_entities,
                        'relations': total_relations,
                        'completed': completed
                    })
                    pbar.update(1)
                    
                except Exception as e:
                    print(f"\nERROR processing {pdf_file}: {e}")
                    failed += 1
                    pbar.update(1)
    
    # Get final Neo4j stats
    db_stats = kg_client.get_stats()
    
    kg_client.close()
    
    return {
        'total_pdfs': len(files_to_process),
        'completed': completed,
        'failed': failed,
        'total_entities': total_entities,
        'total_relations': total_relations,
        'db_stats': db_stats
    }


def test_single_pdf(result_file: str, max_pages: int = 15):
    """Test extraction on a single PDF."""
    print("="*70)
    print("Knowledge Graph Extraction - Single PDF Test")
    print("="*70)
    
    result_path = Path(result_file)
    if not result_path.exists():
        print(f"ERROR: File not found: {result_file}")
        return
    
    # Load and show info
    with open(result_path) as f:
        data = json.load(f)
    
    print(f"\nPDF: {result_path.name}")
    print(f"Total pages: {data.get('total_pages', 0)}")
    print(f"Will process: {min(max_pages, data.get('total_pages', 0))} pages")
    print("\n" + "="*70)
    
    # Initialize clients
    llm_client = get_client()
    kg_client = get_kg_client()
    
    if not kg_client.connect():
        print("ERROR: Failed to connect to Neo4j")
        return
    
    extraction_chain = EntityExtractionChain(
        llm_client=llm_client,
        min_confidence=0.6,
        enable_fallback=True
    )
    
    print("✓ Connected to Neo4j")
    
    # Process
    entities, relations, status = process_single_pdf(
        result_path,
        llm_client,
        kg_client,
        extraction_chain,
        max_pages
    )
    
    print(f"\n{'='*70}")
    print("Results:")
    print(f"  Status: {status}")
    print(f"  Entities: {entities}")
    print(f"  Relations: {relations}")
    
    # Show Neo4j stats
    db_stats = kg_client.get_stats()
    print(f"\nNeo4j Database:")
    for label, count in db_stats.get('node_counts_by_label', {}).items():
        print(f"  {label}: {count} nodes")
    
    kg_client.close()
    print(f"\n{'='*70}")
    print("✓ Test complete!")


def main():
    parser = argparse.ArgumentParser(
        description='Build Knowledge Graph from processed PDF results',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test single PDF
  python3 scripts/build_knowledge_graph.py --test data/processed/batch3/MOZILLA/results/XXX_results.json

  # Process all PDFs (first 15 pages each)
  python3 scripts/build_knowledge_graph.py --all

  # Process with custom page limit
  python3 scripts/build_knowledge_graph.py --all --max-pages 10

  # Resume from checkpoint
  python3 scripts/build_knowledge_graph.py --all --resume

  # Reset checkpoint and start fresh
  python3 scripts/build_knowledge_graph.py --all --reset
        """
    )
    
    parser.add_argument('--test', type=str,
                       help='Test with single PDF file')
    parser.add_argument('--all', action='store_true',
                       help='Process all result files')
    parser.add_argument('--max-pages', type=int, default=15,
                       help='Maximum pages to process per PDF (default: 15)')
    parser.add_argument('--workers', type=int, default=3,
                       help='Number of parallel workers (default: 3)')
    parser.add_argument('--resume', action='store_true',
                       help='Resume from checkpoint')
    parser.add_argument('--reset', action='store_true',
                       help='Reset checkpoint and start fresh')
    parser.add_argument('--clear', action='store_true',
                       help='Wipe all Neo4j nodes and relations before rebuilding')
    parser.add_argument('--checkpoint', type=str,
                       default='data/processed/kg_checkpoint.json',
                       help='Checkpoint file path')
    
    args = parser.parse_args()
    
    if not args.test and not args.all and not args.clear:
        parser.print_help()
        return

    if args.clear:
        print("Clearing Neo4j database...")
        kg_client = get_kg_client()
        if kg_client.connect():
            kg_client.run_query("MATCH (n) DETACH DELETE n")
            kg_client.close()
            print("✓ Neo4j database cleared")
        else:
            print("ERROR: Could not connect to Neo4j to clear database")
            return

        if not args.test and not args.all:
            return

    # Initialize checkpoint
    checkpoint = KGCheckpoint(args.checkpoint)

    if args.reset:
        checkpoint.reset()
        print("✓ Checkpoint reset")

    if args.test:
        # Test mode
        test_single_pdf(args.test, args.max_pages)
    elif args.all:
        # Find all result files
        result_files = find_all_result_files()
        
        if not result_files:
            print("ERROR: No result files found in data/processed/*/*/results/")
            return
        
        print("="*70)
        print("Knowledge Graph Builder")
        print("="*70)
        print(f"Found {len(result_files)} result files")
        print(f"Max pages per PDF: {args.max_pages}")
        print(f"Parallel workers: {args.workers}")
        print(f"Checkpoint: {args.checkpoint}")
        
        if args.resume:
            stats = checkpoint.get_stats()
            print(f"\nCheckpoint status:")
            print(f"  Completed: {stats.get('completed', 0)}")
            print(f"  Failed: {stats.get('failed', 0)}")
        
        print("\nStarting processing...")
        print("="*70)
        
        # Process all
        start_time = time.time()
        results = process_all_pdfs(
            result_files,
            max_pages=args.max_pages,
            parallel_workers=args.workers,
            checkpoint=checkpoint,
            resume=args.resume
        )
        
        elapsed = time.time() - start_time
        
        # Final report
        print("\n" + "="*70)
        print("FINAL RESULTS")
        print("="*70)
        print(f"Time: {elapsed/60:.1f} minutes")
        print(f"PDFs processed: {results.get('completed', 0)}/{results.get('total_pdfs', 0)}")
        print(f"Failed: {results.get('failed', 0)}")
        print(f"Total entities: {results.get('total_entities', 0)}")
        print(f"Total relations: {results.get('total_relations', 0)}")
        
        print("\nNeo4j Database:")
        db_stats = results.get('db_stats', {})
        for label, count in sorted(db_stats.get('node_counts_by_label', {}).items(), 
                                   key=lambda x: x[1], reverse=True):
            print(f"  {label}: {count} nodes")
        
        total_nodes = sum(db_stats.get('node_counts_by_label', {}).values())
        total_rels = sum(db_stats.get('relation_counts_by_type', {}).values())
        print(f"\n  Total: {total_nodes} nodes, {total_rels} relations")
        
        print("\n" + "="*70)
        print("✓ Knowledge graph building complete!")
        print("="*70)


if __name__ == '__main__':
    main()
