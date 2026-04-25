#!/usr/bin/env python3
"""
CLI entry point for PDF/OCR extraction and benchmarking pipeline.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.extraction import extract_native, extract_ocr, route_extraction
from src.evaluation import Benchmark, calculate_all_metrics


def extract_command(args):
    """Extract text from PDFs using specified method."""
    pdf_path = Path(args.input)
    
    if not pdf_path.exists():
        print(f"Error: File not found: {pdf_path}")
        sys.exit(1)
    
    print(f"Processing: {pdf_path}")
    print(f"Method: {args.method}")
    
    if args.method == "native":
        result = extract_native(str(pdf_path))
        print(f"\nExtraction complete!")
        print(f"Coverage: {result['coverage']:.1%}")
        print(f"Text length: {len(result['text'])} characters")
        
    elif args.method == "ocr":
        # First convert to image
        from src.extraction import convert_pdf_to_images
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            images = convert_pdf_to_images(str(pdf_path), tmpdir)
            
            all_text = []
            for img_path in images:
                text = extract_ocr(img_path, max_tokens=args.max_tokens)
                all_text.append(text)
            
            result = {"text": "\n\n".join(all_text), "images": images}
            print(f"\nOCR complete!")
            print(f"Pages processed: {len(images)}")
            print(f"Text length: {len(result['text'])} characters")
    
    elif args.method == "hybrid":
        result = route_extraction(str(pdf_path), native_threshold=args.threshold)
        print(f"\nHybrid extraction complete!")
        print(f"Method used: {result['method']}")
        print(f"Native coverage: {result.get('native_coverage', 0):.1%}")
        print(f"Text length: {len(result['text'])} characters")
    
    # Save output
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"\nResults saved to: {output_path}")
    
    # Print preview
    if args.preview:
        print("\n" + "="*80)
        print("PREVIEW (first 1000 characters):")
        print("="*80)
        print(result['text'][:1000])
        if len(result['text']) > 1000:
            print("\n... [truncated]")


def benchmark_command(args):
    """Run ablation benchmark experiments."""
    input_dir = Path(args.input_dir)
    
    if not input_dir.exists():
        print(f"Error: Directory not found: {input_dir}")
        sys.exit(1)
    
    # Find all PDFs
    pdf_paths = list(input_dir.glob("*.pdf"))
    if not pdf_paths:
        print(f"No PDF files found in {input_dir}")
        sys.exit(1)
    
    print(f"Found {len(pdf_paths)} PDF files")
    print(f"Running ablation: {args.ablation}")
    
    # Run benchmark
    benchmark = Benchmark()
    
    if args.ablation == "E1":
        results = benchmark.run_ablation(pdf_paths, "native", extract_native)
    elif args.ablation == "E2":
        from src.extraction.ocr import extract_ocr
        results = benchmark.run_ablation(pdf_paths, "ocr", extract_ocr)
    elif args.ablation == "E3":
        from src.extraction.router import route_extraction
        results = benchmark.run_ablation(pdf_paths, "hybrid", route_extraction)
    else:
        print(f"Error: Unknown ablation {args.ablation}")
        print("Valid options: E1 (native), E2 (ocr), E3 (hybrid)")
        sys.exit(1)
    
    # Save results
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to: {args.output}")


def extract_batch_command(args):
    """Extract text from multiple PDFs using both native and OCR methods."""
    from src.extraction.batch_processor import BatchProcessor
    
    input_dir = Path(args.input_dir)
    
    if not input_dir.exists():
        print(f"Error: Directory not found: {input_dir}")
        sys.exit(1)
    
    # Find all PDFs
    pdf_paths = sorted(list(input_dir.glob("*.pdf")))
    if not pdf_paths:
        print(f"No PDF files found in {input_dir}")
        sys.exit(1)
    
    print(f"Found {len(pdf_paths)} PDF files to process")
    print(f"Max pages per PDF: {args.max_pages}")
    print(f"Parallel workers: {args.parallel}")
    print(f"Save images: {args.save_images}")
    print()

    # Initialize batch processor
    processor = BatchProcessor(
        output_dir=args.output_dir,
        checkpoint_path=args.checkpoint,
        project_name=args.project_name,
        max_pages=args.max_pages,
        parallel_workers=args.parallel,
        save_images=args.save_images,
        ocr_dpi=args.ocr_dpi,
        ocr_timeout=args.ocr_timeout,
        method=getattr(args, 'method', 'hybrid')
    )

    # Process batch (limit caps how many NEW files per run, after checkpoint filtering)
    results = processor.process_batch(
        pdf_paths=[str(p) for p in pdf_paths],
        limit=args.limit,
        limit_pages_per_pdf=args.limit_pages
    )
    
    print(f"\n✓ Processing complete!")
    print(f"Results saved to: {args.output_dir}/results/")
    
    # Show failed files if any
    failed = processor.get_failed_files()
    if failed:
        print(f"\n⚠ {len(failed)} files failed:")
        for filename, error in list(failed.items())[:5]:
            print(f"  - {filename}: {error}")
    
    # Show skipped files if any
    skipped = processor.get_skipped_files()
    if skipped:
        print(f"\n⊘ {len(skipped)} files skipped:")
        for filename, reason in list(skipped.items())[:5]:
            print(f"  - {filename}: {reason}")


def evaluate_command(args):
    """Evaluate extraction against ground truth."""
    # Load predictions and ground truth
    with open(args.predictions, 'r', encoding='utf-8') as f:
        predictions = json.load(f)
    
    with open(args.ground_truth, 'r', encoding='utf-8') as f:
        ground_truth = json.load(f)
    
    # Calculate metrics
    metrics = calculate_all_metrics(predictions['text'], ground_truth['text'])
    
    print("Evaluation Results:")
    print("="*80)
    print(f"Character Error Rate (CER): {metrics['cer']:.2%}")
    print(f"Word Error Rate (WER):      {metrics['wer']:.2%}")
    print(f"Text Similarity:            {metrics['similarity']:.2%}")
    
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(metrics, f, indent=2)
        print(f"\nMetrics saved to: {args.output}")


def kg_init_command(args):
    """Initialize Neo4j knowledge graph schema."""
    from src.kg import Neo4jClient
    
    print("Initializing Neo4j knowledge graph...")
    
    # Create client
    client = Neo4jClient()
    
    # Connect to Neo4j
    if not client.connect():
        print("Error: Failed to connect to Neo4j")
        print("Make sure Neo4j is running and accessible")
        sys.exit(1)
    
    try:
        # Initialize schema (constraints and indexes)
        if client.init_schema():
            print("✓ Schema initialized successfully")
            print("  - Created constraints for unique IDs")
            print("  - Created indexes for performance")
        else:
            print("⚠ Schema initialization had issues")
        
        # Show stats
        stats = client.get_stats()
        print("\nDatabase Statistics:")
        print(f"  Node counts by label: {stats.get('node_counts_by_label', {})}")
        print(f"  Relation counts by type: {stats.get('relation_counts_by_type', {})}")
        
    finally:
        client.close()


def kg_extract_command(args):
    """Extract entities from documents and import to Neo4j."""
    from src.llm import get_client, EntityExtractionChain
    from src.kg import BulkImporter, get_client as get_kg_client
    from src.extraction import BatchProcessor
    
    print("Knowledge Graph Extraction")
    print("="*80)
    
    # Initialize LLM client with specified provider
    llm_client = get_client()
    if args.provider:
        print(f"Using LLM provider: {args.provider}")
        llm_client.switch_provider(args.provider)
    else:
        print(f"Using default provider: {llm_client.get_current_provider()}")
    
    # Initialize KG client
    kg_client = get_kg_client()
    if not kg_client.connect():
        print("Error: Failed to connect to Neo4j")
        sys.exit(1)
    
    # Ensure schema exists
    kg_client.init_schema()
    
    # Initialize extraction chain
    extraction_chain = EntityExtractionChain(
        llm_client=llm_client,
        min_confidence=args.min_confidence,
        enable_fallback=True,
    )
    
    # Initialize bulk importer
    importer = BulkImporter(
        client=kg_client,
        batch_size=args.batch_size,
    )
    
    input_path = Path(args.input)
    
    try:
        if input_path.is_file():
            # Process single file
            print(f"\nProcessing file: {input_path}")
            
            # For PDFs, extract text first
            if input_path.suffix.lower() == '.pdf':
                processor = BatchProcessor(
                    output_dir=str(input_path.parent),
                    max_pages=args.max_pages,
                    parallel_workers=1,
                )
                
                results = processor.process_batch([str(input_path)])

                # Load full result from saved file on disk
                if results and results[0].get('status') == 'complete':
                    result_file = results[0].get('result_file')
                    if result_file:
                        with open(result_file, 'r', encoding='utf-8') as f:
                            full_result = json.load(f)
                        text_parts = []
                        for page_data in full_result.get('pages', []):
                            if page_data.get('ocr', {}).get('text'):
                                text_parts.append(page_data['ocr']['text'])
                            elif page_data.get('native', {}).get('text'):
                                text_parts.append(page_data['native']['text'])
                        text = "\n\n".join(text_parts)
                    else:
                        print("Error: Failed to extract text from PDF")
                        sys.exit(1)
                else:
                    print("Error: Failed to extract text from PDF")
                    sys.exit(1)
            else:
                # Read text file directly
                with open(input_path, 'r', encoding='utf-8') as f:
                    text = f.read()
            
            # Extract entities
            print("Extracting entities with LLM...")
            extraction_result = extraction_chain.extract(
                text=text,
                document_id=str(input_path)
            )
            
            print(f"  Found {len(extraction_result.entities)} entities")
            print(f"  Found {len(extraction_result.relations)} relations")
            
            # Import to Neo4j
            print("Importing to Neo4j...")
            importer.import_extraction_result(extraction_result)
            
        elif input_path.is_dir():
            # Process directory
            print(f"\nProcessing directory: {input_path}")
            
            # Find PDFs and text files
            files = []
            for pattern in ['*.pdf', '*.txt']:
                files.extend(input_path.glob(pattern))
            
            if not files:
                print(f"No PDF or text files found in {input_path}")
                sys.exit(1)
            
            print(f"Found {len(files)} files to process")
            
            # Process each file
            for i, file_path in enumerate(files, 1):
                print(f"\n[{i}/{len(files)}] Processing: {file_path.name}")
                
                try:
                    if file_path.suffix.lower() == '.pdf':
                        # Quick extraction for PDFs
                        from src.extraction import extract_ocr
                        from src.extraction.pdf_converter import convert_pdf_to_images
                        import tempfile
                        
                        with tempfile.TemporaryDirectory() as tmpdir:
                            images = convert_pdf_to_images(str(file_path), tmpdir, dpi=150)
                            texts = [extract_ocr(img, max_tokens=2048) for img in images[:5]]  # Limit pages
                            text = "\n\n".join(texts)
                    else:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            text = f.read()
                    
                    # Truncate if too long
                    if len(text) > 10000:
                        text = text[:10000] + "\n\n[truncated for processing]"
                    
                    # Extract entities
                    extraction_result = extraction_chain.extract(
                        text=text,
                        document_id=str(file_path)
                    )
                    
                    print(f"  Entities: {len(extraction_result.entities)}, Relations: {len(extraction_result.relations)}")
                    
                    # Import
                    importer.import_extraction_result(extraction_result)
                    
                except Exception as e:
                    print(f"  Error processing {file_path.name}: {e}")
                    continue
        
        # Show final stats
        print("\n" + "="*80)
        print("Extraction Complete!")
        print("="*80)
        print(f"Documents processed: {importer.stats.documents_processed}")
        print(f"Documents failed: {importer.stats.documents_failed}")
        print(f"Entities created: {importer.stats.entities_created}")
        print(f"Relations created: {importer.stats.relations_created}")
        print(f"Total processing time: {importer.stats.processing_time_ms/1000:.1f}s")
        
        # Show database stats
        db_stats = kg_client.get_stats()
        print(f"\nDatabase now contains:")
        for label, count in db_stats.get('node_counts_by_label', {}).items():
            print(f"  {label}: {count} nodes")
        
        # Save extraction results if requested
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # We can't easily get all extraction results back, but we could modify
            # the pipeline to save them. For now, just save stats.
            with open(output_path, 'w') as f:
                json.dump(importer.stats.to_dict(), f, indent=2)
            print(f"\nStats saved to: {output_path}")
        
    finally:
        kg_client.close()


def kg_import_command(args):
    """Import extraction results from JSON files to Neo4j."""
    from src.kg import BulkImporter, get_client as get_kg_client
    
    print("Importing to Neo4j Knowledge Graph")
    print("="*80)
    
    # Initialize KG client
    kg_client = get_kg_client()
    if not kg_client.connect():
        print("Error: Failed to connect to Neo4j")
        sys.exit(1)
    
    # Ensure schema exists
    kg_client.init_schema()
    
    # Initialize bulk importer
    importer = BulkImporter(
        client=kg_client,
        batch_size=args.batch_size,
    )
    
    input_path = Path(args.input)
    
    try:
        if input_path.is_file():
            # Import single file
            print(f"\nImporting file: {input_path}")
            stats = importer.import_from_json(str(input_path))
            
        elif input_path.is_dir():
            # Import directory
            print(f"\nImporting directory: {input_path}")
            stats = importer.import_from_directory(
                str(input_path),
                pattern=args.pattern,
                progress_bar=True,
            )
        else:
            print(f"Error: Input path not found: {input_path}")
            sys.exit(1)
        
        # Show stats
        print("\n" + "="*80)
        print("Import Complete!")
        print("="*80)
        print(f"Documents processed: {stats.documents_processed}")
        print(f"Documents failed: {stats.documents_failed}")
        print(f"Entities created: {stats.entities_created}")
        print(f"Relations created: {stats.relations_created}")
        print(f"Entities failed: {stats.entities_failed}")
        print(f"Relations failed: {stats.relations_failed}")
        print(f"Total time: {stats.processing_time_ms/1000:.1f}s")
        
        if stats.errors and args.verbose:
            print(f"\nErrors ({len(stats.errors)}):")
            for error in stats.errors[:10]:
                print(f"  - {error}")
        
        # Show database stats
        db_stats = kg_client.get_stats()
        print(f"\nDatabase now contains:")
        for label, count in db_stats.get('node_counts_by_label', {}).items():
            print(f"  {label}: {count} nodes")
        for rel_type, count in db_stats.get('relation_counts_by_type', {}).items():
            print(f"  {rel_type}: {count} relations")
        
    finally:
        kg_client.close()


def kg_stats_command(args):
    """Show Neo4j knowledge graph statistics."""
    from src.kg import get_client as get_kg_client
    
    print("Neo4j Knowledge Graph Statistics")
    print("="*80)
    
    kg_client = get_kg_client()
    if not kg_client.connect():
        print("Error: Failed to connect to Neo4j")
        sys.exit(1)
    
    try:
        stats = kg_client.get_stats()
        
        print("\nNode Counts by Label:")
        node_counts = stats.get('node_counts_by_label', {})
        if node_counts:
            for label, count in sorted(node_counts.items(), key=lambda x: x[1], reverse=True):
                print(f"  {label}: {count}")
        else:
            print("  No nodes found")
        
        print("\nRelation Counts by Type:")
        rel_counts = stats.get('relation_counts_by_type', {})
        if rel_counts:
            for rel_type, count in sorted(rel_counts.items(), key=lambda x: x[1], reverse=True):
                print(f"  {rel_type}: {count}")
        else:
            print("  No relations found")
        
        total_nodes = sum(node_counts.values())
        total_rels = sum(rel_counts.values())
        
        print(f"\nTotal: {total_nodes} nodes, {total_rels} relations")
        
        # Sample query if nodes exist
        if total_nodes > 0:
            print("\nSample nodes:")
            sample = kg_client.run_query("MATCH (n) RETURN n LIMIT 5")
            for i, record in enumerate(sample, 1):
                node = record.get('n', {})
                labels = list(node.keys())[:3]  # Show first few properties
                print(f"  {i}. {dict(list(node.items())[:3])}")
        
    finally:
        kg_client.close()


def kg_integrity_command(args):
    """Run knowledge graph integrity checks."""
    from src.kg import get_client as get_kg_client
    from src.evaluation.kg_integrity import run_integrity_check
    import json

    print("Knowledge Graph Integrity Check")
    print("=" * 80)

    kg_client = get_kg_client()
    if not kg_client.connect():
        print("Error: Failed to connect to Neo4j")
        sys.exit(1)

    try:
        report = run_integrity_check(kg_client)
        report.print_report()

        if args.output:
            with open(args.output, 'w') as f:
                json.dump(report.to_dict(), f, indent=2)
            print(f"\nReport saved to: {args.output}")
    finally:
        kg_client.close()


def kg_canonicalize_command(args):
    """Merge duplicate entity nodes using fuzzy name matching."""
    from scripts.canonicalize_entities import run_canonicalization
    run_canonicalization(
        threshold=args.threshold,
        dry_run=args.dry_run,
        label=args.label,
    )


def rag_index_command(args):
    """Build or rebuild the RAG index (ChromaDB + BM25)."""
    from src.rag.indexer import RAGIndexer

    print("Building RAG index")
    print("=" * 80)
    indexer = RAGIndexer()
    stats = indexer.build_index(force_rebuild=getattr(args, "force", False))
    print(f"Documents indexed: {stats.get('documents', 0)}")
    print(f"Pages processed:   {stats.get('pages', 0)}")
    print(f"Chunks created:    {stats.get('chunks', 0)}")
    idx_stats = indexer.get_stats()
    print(f"\nVector store:  {idx_stats['vector_chunks']} chunks  ({idx_stats['persist_directory']})")
    print(f"BM25 index:    {idx_stats['bm25_chunks']} chunks  ({idx_stats['bm25_path']})")


def rag_stats_command(args):
    """Show RAG index statistics."""
    from src.rag.indexer import RAGIndexer

    indexer = RAGIndexer()
    stats = indexer.get_stats()
    print("RAG Index Statistics")
    print("=" * 80)
    print(f"Vector store chunks : {stats['vector_chunks']}")
    print(f"BM25 index chunks   : {stats['bm25_chunks']}")
    print(f"Vector persist dir  : {stats['persist_directory']}")
    print(f"BM25 path           : {stats['bm25_path']}")


def rag_query_command(args):
    """Run a one-shot RAG query (no UI)."""
    from src.rag.indexer import RAGIndexer
    from src.rag.vector_store import VectorStore
    from src.rag.bm25 import BM25Index
    from src.rag.hybrid import HybridRetriever
    from src.rag.chain import RAGChain
    from src.llm.client import get_client as get_llm_client
    import yaml
    from pathlib import Path as _Path

    cfg_path = _Path(__file__).parent.parent / "config" / "rag.yaml"
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f) or {}

    vec_cfg = cfg.get("vector", {})
    bm_cfg = cfg.get("bm25", {})

    vs = VectorStore(
        collection_name=vec_cfg.get("collection_name", "pdf_chunks"),
        embedding_model=vec_cfg.get("embedding_model", "all-MiniLM-L6-v2"),
        persist_directory=vec_cfg.get("persist_directory", "data/rag/chromadb"),
    )

    bm25 = BM25Index(k1=bm_cfg.get("k1", 1.5), b=bm_cfg.get("b", 0.75))
    bm25.load(bm_cfg.get("persist_path", "data/rag/bm25_index.json"))

    graph_ret = None
    try:
        from src.kg.client import get_client as get_kg_client
        from src.rag.graph_retriever import GraphRetriever
        kg = get_kg_client()
        kg.connect()
        ret_cfg = cfg.get("retrieval", {})
        graph_ret = GraphRetriever(
            kg_client=kg,
            max_entities=ret_cfg.get("graph_max_entities", 5),
        )
    except Exception:
        pass

    retriever = HybridRetriever(
        vector_store=vs, bm25_index=bm25, graph_retriever=graph_ret, config=cfg
    )

    provider = getattr(args, "provider", None) or "ollama"
    llm = get_llm_client(provider_name=provider)
    chain = RAGChain(retriever=retriever, llm_client=llm, config=cfg)

    query = args.query
    print(f"Query: {query}")
    print("=" * 80)
    answer, results = chain.query(query)
    print(answer)
    print(f"\n[Retrieved {len(results)} chunks from {', '.join({r.source for r in results})}]")


def rag_chat_command(args):
    """Launch the Gradio chatbot UI."""
    from src.web.chatbot import main as chatbot_main
    chatbot_main()


def rag_eval_command(args):
    """Evaluate RAG retrieval quality (Recall@K, MRR, latency)."""
    from src.rag.vector_store import VectorStore
    from src.rag.bm25 import BM25Index
    from src.rag.hybrid import HybridRetriever
    from src.evaluation.rag_evaluator import load_eval_queries, evaluate_retriever, evaluate_all_tiers
    import yaml
    import json
    from pathlib import Path as _Path

    cfg_path = _Path(__file__).parent.parent / "config" / "rag.yaml"
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f) or {}

    vec_cfg = cfg.get("vector", {})
    bm_cfg = cfg.get("bm25", {})

    vs = VectorStore(
        collection_name=vec_cfg.get("collection_name", "pdf_chunks"),
        embedding_model=vec_cfg.get("embedding_model", "all-MiniLM-L6-v2"),
        persist_directory=vec_cfg.get("persist_directory", "data/rag/chromadb"),
    )
    bm25 = BM25Index(k1=bm_cfg.get("k1", 1.5), b=bm_cfg.get("b", 0.75))
    bm25.load(bm_cfg.get("persist_path", "data/rag/bm25_index.json"))

    graph_ret = None
    try:
        from src.kg.client import get_client as get_kg_client
        from src.rag.graph_retriever import GraphRetriever
        kg = get_kg_client()
        kg.connect()
        ret_cfg = cfg.get("retrieval", {})
        graph_ret = GraphRetriever(kg_client=kg, max_entities=ret_cfg.get("graph_max_entities", 5))
    except Exception:
        pass

    hybrid = HybridRetriever(vector_store=vs, bm25_index=bm25, graph_retriever=graph_ret, config=cfg)

    k_values = [int(k) for k in args.k_values.split(",")]
    queries = load_eval_queries(args.queries)
    print(f"Loaded {len(queries)} evaluation queries from {args.queries}")

    if args.tiers:
        reports = evaluate_all_tiers(vs, bm25, graph_ret, hybrid, queries, k_values)
        for tier_name, report in reports.items():
            report.print_report()
        if args.output:
            output_data = {name: r.to_dict() for name, r in reports.items()}
            with open(args.output, "w") as f:
                json.dump(output_data, f, indent=2)
            print(f"\nReport saved to: {args.output}")
    else:
        report = evaluate_retriever(hybrid, queries, k_values, tier_name="hybrid_graph")
        report.print_report()
        if args.output:
            with open(args.output, "w") as f:
                json.dump(report.to_dict(), f, indent=2)
            print(f"\nReport saved to: {args.output}")


def eval_entity_tool_command(args):
    """Launch the Gold Set B entity/relation annotation Streamlit UI."""
    import subprocess
    import sys
    from pathlib import Path as _Path
    tool_path = _Path(__file__).parent / "evaluation" / "entity_annotation_tool.py"
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(tool_path)], check=True)


def eval_entity_report_command(args):
    """Print aggregate Entity/Relation F1 from Gold Set B annotations."""
    import json
    from pathlib import Path as _Path
    from src.evaluation.entity_annotation_tool import EntityAnnotationStore
    from src.evaluation.entity_metrics import compute_gold_set_b_report

    store = EntityAnnotationStore()
    all_anns = store.get_all()
    if not all_anns:
        print("No Gold Set B annotations found. Run the entity annotation tool first.")
        return

    report = compute_gold_set_b_report(all_anns)
    print("\nGold Set B — Entity/Relation F1 Report")
    print("=" * 50)
    print(f"Pages annotated:          {report['total_pages_annotated']}")
    print(f"\nEntity:")
    e = report["entity"]
    print(f"  Precision:              {e['mean_precision']:.4f}")
    print(f"  Recall:                 {e['mean_recall']:.4f}")
    print(f"  F1:                     {e['mean_f1']:.4f}")
    print(f"  Hallucination rate:     {e['mean_hallucination_rate']:.4f}")
    print(f"\nRelation:")
    r = report["relation"]
    print(f"  Precision:              {r['mean_precision']:.4f}")
    print(f"  Recall:                 {r['mean_recall']:.4f}")
    print(f"  F1:                     {r['mean_f1']:.4f}")
    print(f"  Hallucination rate:     {r['mean_hallucination_rate']:.4f}")
    print(f"\nMean schema validity:     {report['mean_schema_validity_rate']:.4f}")
    print("=" * 50)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2)
        print(f"Report saved to: {args.output}")


def main():
    parser = argparse.ArgumentParser(
        description="PDF/OCR Extraction and Knowledge Graph Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Extract text from a PDF using hybrid method
  python -m src.cli extract input.pdf --method hybrid --output result.json
  
  # Run native-only benchmark (E1)
  python -m src.cli benchmark data/batch3 --ablation E1 --output benchmark.json
  
  # Process batch with both native and OCR
  python -m src.cli extract-batch data/batch3/MOZILLA \\
    --limit 10 --max-pages 20 --parallel 3 --save-images
  
  # Evaluate extraction quality
  python -m src.cli evaluate --predictions pred.json --ground_truth truth.json
  
  # Knowledge Graph operations
  python -m src.cli kg init                    # Initialize Neo4j schema
  python -m src.cli kg extract input.pdf         # Extract entities from PDF
  python -m src.cli kg extract data/batch3/ \\
    --provider claude --max-pages 3            # Process directory with Claude
  python -m src.cli kg import extraction.json    # Import to Neo4j
  python -m src.cli kg stats                     # Show graph statistics
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Extract command
    extract_parser = subparsers.add_parser('extract', help='Extract text from single PDF')
    extract_parser.add_argument('input', help='Input PDF file')
    extract_parser.add_argument('--method', choices=['native', 'ocr', 'hybrid'], 
                               default='hybrid', help='Extraction method')
    extract_parser.add_argument('--output', '-o', help='Output JSON file')
    extract_parser.add_argument('--threshold', type=float, default=0.8,
                               help='Native coverage threshold for hybrid routing')
    extract_parser.add_argument('--max-tokens', type=int, default=4096,
                               help='Max tokens for OCR (default: 4096)')
    extract_parser.add_argument('--preview', action='store_true',
                               help='Show text preview')
    extract_parser.set_defaults(func=extract_command)
    
    # Benchmark command
    benchmark_parser = subparsers.add_parser('benchmark', help='Run benchmark ablations')
    benchmark_parser.add_argument('input_dir', help='Directory containing PDF files')
    benchmark_parser.add_argument('--ablation', choices=['E1', 'E2', 'E3'], required=True,
                                 help='Ablation: E1 (native), E2 (ocr), E3 (hybrid)')
    benchmark_parser.add_argument('--output', '-o', help='Output results file')
    benchmark_parser.set_defaults(func=benchmark_command)
    
    # Extract-batch command
    batch_parser = subparsers.add_parser('extract-batch', help='Process multiple PDFs with both methods')
    batch_parser.add_argument('input_dir', help='Directory containing PDF files')
    batch_parser.add_argument('--method', choices=['native', 'ocr', 'hybrid'], default='hybrid',
                             help='Extraction method: native (fast), ocr, or hybrid (default)')
    batch_parser.add_argument('--limit', type=int, default=None,
                             help='Limit to first N PDFs (for testing)')
    batch_parser.add_argument('--limit-pages', type=int, default=None,
                             help='Limit each PDF to first N pages')
    batch_parser.add_argument('--max-pages', type=int, default=20,
                             help='Skip PDFs with more than N pages')
    batch_parser.add_argument('--parallel', type=int, default=3,
                             help='Number of parallel workers (default: 3)')
    batch_parser.add_argument('--output-dir', default='data/processed/mozilla',
                             help='Output directory for results and images')
    batch_parser.add_argument('--checkpoint', default='data/processed/mozilla/checkpoint.json',
                             help='Checkpoint file path')
    batch_parser.add_argument('--project-name', default='mozilla_batch',
                             help='Project name for checkpoint tracking')
    batch_parser.add_argument('--save-images', action='store_true', default=True,
                             help='Save converted images (default: True)')
    batch_parser.add_argument('--ocr-dpi', type=int, default=200,
                             help='DPI for OCR image conversion (default: 200)')
    batch_parser.add_argument('--ocr-timeout', type=int, default=300,
                             help='OCR request timeout in seconds (default: 300)')
    batch_parser.set_defaults(func=extract_batch_command)
    
    # Evaluate command
    eval_parser = subparsers.add_parser('evaluate', help='Evaluate against ground truth')
    eval_parser.add_argument('--predictions', required=True, help='Predictions JSON file')
    eval_parser.add_argument('--ground-truth', required=True, help='Ground truth JSON file')
    eval_parser.add_argument('--output', '-o', help='Output metrics file')
    eval_parser.set_defaults(func=evaluate_command)
    
    # Knowledge Graph commands
    kg_parser = subparsers.add_parser('kg', help='Knowledge Graph operations')
    kg_subparsers = kg_parser.add_subparsers(dest='kg_command', help='KG subcommands')
    
    # kg-init command
    kg_init_parser = kg_subparsers.add_parser('init', help='Initialize Neo4j schema')
    kg_init_parser.set_defaults(func=kg_init_command)
    
    # kg-extract command
    kg_extract_parser = kg_subparsers.add_parser('extract', help='Extract entities from documents')
    kg_extract_parser.add_argument('input', help='Input file or directory (PDFs or text files)')
    kg_extract_parser.add_argument('--provider', choices=['ollama', 'claude', 'openai', 'gemini'],
                                   help='LLM provider to use (default: from config)')
    kg_extract_parser.add_argument('--min-confidence', type=float, default=0.7,
                                    help='Minimum confidence threshold (default: 0.7)')
    kg_extract_parser.add_argument('--batch-size', type=int, default=1000,
                                    help='Batch size for imports (default: 1000)')
    kg_extract_parser.add_argument('--max-pages', type=int, default=5,
                                    help='Max pages to process per PDF (default: 5)')
    kg_extract_parser.add_argument('--output', '-o', help='Output stats file')
    kg_extract_parser.set_defaults(func=kg_extract_command)
    
    # kg-import command
    kg_import_parser = kg_subparsers.add_parser('import', help='Import extraction results to Neo4j')
    kg_import_parser.add_argument('input', help='Input JSON file or directory')
    kg_import_parser.add_argument('--pattern', default='*.json',
                                   help='File pattern for directory import (default: *.json)')
    kg_import_parser.add_argument('--batch-size', type=int, default=1000,
                                   help='Batch size for imports (default: 1000)')
    kg_import_parser.add_argument('--verbose', '-v', action='store_true',
                                   help='Show detailed error output')
    kg_import_parser.set_defaults(func=kg_import_command)
    
    # kg-stats command
    kg_stats_parser = kg_subparsers.add_parser('stats', help='Show Neo4j statistics')
    kg_stats_parser.set_defaults(func=kg_stats_command)

    # kg-integrity command
    kg_integrity_parser = kg_subparsers.add_parser('integrity', help='Run graph integrity checks')
    kg_integrity_parser.add_argument('--output', '-o', help='Save report to JSON file')
    kg_integrity_parser.add_argument('--verbose', '-v', action='store_true', help='Show full details')
    kg_integrity_parser.set_defaults(func=kg_integrity_command)

    # kg canonicalize
    kg_canon_parser = kg_subparsers.add_parser(
        'canonicalize', help='Merge duplicate entity nodes via fuzzy name matching'
    )
    kg_canon_parser.add_argument(
        '--threshold', type=float, default=0.85,
        help='Levenshtein similarity threshold (default: 0.85)'
    )
    kg_canon_parser.add_argument(
        '--dry-run', action='store_true',
        help='Show what would merge without writing to Neo4j'
    )
    kg_canon_parser.add_argument(
        '--label',
        choices=['Person', 'Organization', 'Technology', 'Topic', 'Location'],
        default=None,
        help='Restrict to one entity label (default: all)'
    )
    kg_canon_parser.set_defaults(func=kg_canonicalize_command)

    # RAG commands
    rag_parser = subparsers.add_parser('rag', help='RAG chatbot operations')
    rag_subparsers = rag_parser.add_subparsers(dest='rag_command', help='RAG subcommands')

    # rag index
    rag_index_parser = rag_subparsers.add_parser('index', help='Build/rebuild the RAG index')
    rag_index_parser.add_argument('--force', action='store_true',
                                  help='Force rebuild even if index exists')
    rag_index_parser.set_defaults(func=rag_index_command)

    # rag stats
    rag_stats_parser = rag_subparsers.add_parser('stats', help='Show RAG index statistics')
    rag_stats_parser.set_defaults(func=rag_stats_command)

    # rag query
    rag_query_parser = rag_subparsers.add_parser('query', help='One-shot RAG query')
    rag_query_parser.add_argument('query', help='Question to ask')
    rag_query_parser.add_argument('--provider', choices=['ollama', 'claude', 'openai', 'gemini'],
                                  help='LLM provider (default: from config)')
    rag_query_parser.set_defaults(func=rag_query_command)

    # rag chat
    rag_chat_parser = rag_subparsers.add_parser('chat', help='Launch Gradio chatbot UI')
    rag_chat_parser.set_defaults(func=rag_chat_command)

    # rag eval
    rag_eval_parser = rag_subparsers.add_parser('eval', help='Evaluate RAG retrieval (Recall@K, MRR)')
    rag_eval_parser.add_argument('--queries', default='data/evaluation/rag_eval_queries.json',
                                 help='Path to evaluation queries JSON (default: data/evaluation/rag_eval_queries.json)')
    rag_eval_parser.add_argument('--k-values', default='1,3,5,10',
                                 help='Comma-separated K values for Recall@K (default: 1,3,5,10)')
    rag_eval_parser.add_argument('--tiers', action='store_true',
                                 help='Run full E7-E10 ablation across all retrieval tiers')
    rag_eval_parser.add_argument('--output', '-o', help='Save report to JSON file')
    rag_eval_parser.set_defaults(func=rag_eval_command)

    # Entity evaluation commands (Gold Set B)
    eval_gb_parser = subparsers.add_parser('eval', help='Gold Set B entity/relation evaluation')
    eval_gb_subparsers = eval_gb_parser.add_subparsers(dest='eval_command', help='Eval subcommands')

    eval_tool_parser = eval_gb_subparsers.add_parser('entity-tool', help='Launch entity annotation Streamlit UI')
    eval_tool_parser.set_defaults(func=eval_entity_tool_command)

    eval_report_parser = eval_gb_subparsers.add_parser('entity-report', help='Compute aggregate Entity/Relation F1')
    eval_report_parser.add_argument('--annotations', help='Path to annotations JSON (uses default if omitted)')
    eval_report_parser.add_argument('--output', '-o', help='Save report to JSON file')
    eval_report_parser.set_defaults(func=eval_entity_report_command)

    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Handle kg subcommands
    if args.command == 'kg':
        if not args.kg_command:
            kg_parser.print_help()
            sys.exit(1)
        args.func(args)
    elif args.command == 'rag':
        if not args.rag_command:
            rag_parser.print_help()
            sys.exit(1)
        args.func(args)
    elif args.command == 'eval':
        if not args.eval_command:
            eval_gb_parser.print_help()
            sys.exit(1)
        args.func(args)
    else:
        args.func(args)


if __name__ == '__main__':
    main()
