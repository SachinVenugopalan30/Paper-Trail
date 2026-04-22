"""Bulk Import Pipeline Module.

Provides efficient bulk import of entities and relations into Neo4j.
Supports batching, checkpointing, and resumable imports.
"""

import logging
from typing import Dict, Any, List, Optional, Iterator
from dataclasses import dataclass, field
from pathlib import Path
import json
import time
from tqdm import tqdm

from src.kg.client import Neo4jClient, get_client
from src.llm.chains import ExtractionResult, Entity, Relation

logger = logging.getLogger(__name__)


@dataclass
class ImportStats:
    """Statistics for import operation."""
    
    entities_created: int = 0
    entities_updated: int = 0
    entities_failed: int = 0
    relations_created: int = 0
    relations_failed: int = 0
    documents_processed: int = 0
    documents_failed: int = 0
    processing_time_ms: float = 0.0
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entities_created": self.entities_created,
            "entities_updated": self.entities_updated,
            "entities_failed": self.entities_failed,
            "relations_created": self.relations_created,
            "relations_failed": self.relations_failed,
            "documents_processed": self.documents_processed,
            "documents_failed": self.documents_failed,
            "processing_time_ms": self.processing_time_ms,
            "error_count": len(self.errors),
        }


class BulkImporter:
    """Bulk import pipeline for Neo4j knowledge graph."""
    
    def __init__(
        self,
        client: Optional[Neo4jClient] = None,
        batch_size: int = 1000,
        max_retries: int = 3,
        skip_duplicates: bool = True,
    ):
        """Initialize bulk importer.
        
        Args:
            client: Neo4j client. If None, uses singleton.
            batch_size: Number of entities/relations per batch
            max_retries: Maximum retry attempts for failed operations
            skip_duplicates: Whether to skip duplicate entities silently
        """
        self.client = client or get_client()
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.skip_duplicates = skip_duplicates
        self.stats = ImportStats()
        
    def import_extraction_result(
        self,
        result: ExtractionResult,
        create_relations: bool = True
    ) -> bool:
        """Import a single extraction result into Neo4j.
        
        Args:
            result: Extraction result with entities and relations
            create_relations: Whether to also create relations
            
        Returns:
            True if successful
        """
        start_time = time.time()
        
        try:
            # Import entities first
            entity_map = self._import_entities(result.entities)
            
            # Then import relations if requested
            if create_relations and entity_map:
                self._import_relations(result.relations, entity_map)
            
            self.stats.documents_processed += 1
            return True
            
        except Exception as e:
            logger.error(f"Failed to import extraction result for {result.source_document}: {e}")
            self.stats.documents_failed += 1
            self.stats.errors.append(f"{result.source_document}: {str(e)}")
            return False
        finally:
            self.stats.processing_time_ms += (time.time() - start_time) * 1000
    
    def _import_entities(self, entities: List[Entity]) -> Dict[str, str]:
        """Import entities and return name -> (neo4j_id, label, match_prop) mapping.

        Returns:
            Dictionary mapping entity name to Neo4j internal ID
        """
        entity_map = {}

        # Which property to MERGE on, keyed by entity type
        MATCH_PROPERTIES = {
            "Document": "doc_id",
            "Reference": "value",
        }

        for entity in entities:
            # Guard: skip entities with empty/invalid type or name
            if not entity.type or not entity.type.strip():
                logger.warning(f"Skipping entity with empty type (name={entity.name!r})")
                self.stats.entities_failed += 1
                continue
            if not entity.name or not entity.name.strip():
                logger.warning(f"Skipping entity with empty name (type={entity.type!r})")
                self.stats.entities_failed += 1
                continue
            # Guard: reject multi-word labels (spaces or dots in type) — invalid Cypher
            if ' ' in entity.type or (entity.type.count('.') > 0 and not entity.type[0].isupper()):
                logger.warning(f"Skipping entity with invalid label '{entity.type}' (name={entity.name!r})")
                self.stats.entities_failed += 1
                continue
            try:
                match_property = MATCH_PROPERTIES.get(entity.type, "name")
                match_value = entity.properties.get(match_property, entity.name)

                result = self._retry_operation(
                    lambda e=entity, mp=match_property, mv=match_value: self.client.merge_node(
                        label=e.type,
                        match_property=mp,
                        properties={
                            mp: mv,
                            **e.properties,
                            "_confidence": e.confidence,
                            "_source_text": e.source_text,
                            "_extraction_method": e.properties.get("extraction_method", "llm"),
                        }
                    )
                )

                if result:
                    # Store (neo4j_id, entity_type, match_property, match_value) so
                    # _import_relations never needs to re-query Neo4j for labels
                    entity_map[entity.name] = {
                        "id": result.get("id", entity.name),
                        "label": entity.type,
                        "match_prop": match_property,
                        "match_value": match_value,
                    }
                    self.stats.entities_created += 1
                else:
                    self.stats.entities_failed += 1

            except Exception as e:
                logger.error(f"Failed to import entity {entity.name}: {e}")
                self.stats.entities_failed += 1
                self.stats.errors.append(f"Entity {entity.name}: {str(e)}")

        return entity_map

    def _import_relations(
        self,
        relations: List[Relation],
        entity_map: Dict[str, str]
    ) -> None:
        """Import relations between entities."""
        for relation in relations:
            # Guard: skip relations with empty type
            if not relation.type or not relation.type.strip():
                logger.warning(f"Skipping relation with empty type: {relation.source!r} -> {relation.target!r}")
                self.stats.relations_failed += 1
                continue
            try:
                src_info = entity_map.get(relation.source)
                tgt_info = entity_map.get(relation.target)

                if not src_info or not tgt_info:
                    logger.debug(f"Skipping relation: {relation.source} -> {relation.target} (missing entities)")
                    continue

                self._retry_operation(
                    lambda s=src_info, t=tgt_info, r=relation: self.client.merge_relation(
                        source_label=s["label"],
                        source_prop=s["match_prop"],
                        source_value=s["match_value"],
                        target_label=t["label"],
                        target_prop=t["match_prop"],
                        target_value=t["match_value"],
                        rel_type=r.type,
                        properties={
                            **r.properties,
                            "_confidence": r.confidence,
                            "_source_text": r.source_text,
                            "_extraction_method": r.properties.get("extraction_method", "llm"),
                        }
                    )
                )

                self.stats.relations_created += 1
                
            except Exception as e:
                logger.error(f"Failed to import relation {relation.source} -> {relation.target}: {e}")
                self.stats.relations_failed += 1
                self.stats.errors.append(f"Relation {relation.source}->{relation.target}: {str(e)}")
    
    def _get_entity_label(self, entity_name: str) -> Optional[str]:
        """Get the label (type) of an entity by name.
        
        Args:
            entity_name: Entity name or ID
            
        Returns:
            Entity label or None if not found
        """
        # Query database for entity label
        query = """
        MATCH (n)
        WHERE n.name = $name OR n.doc_id = $name OR n.value = $name
        RETURN labels(n) as labels
        LIMIT 1
        """
        
        result = self.client.run_query_single(query, {"name": entity_name})
        if result and result.get("labels"):
            return result["labels"][0]  # Return first label
        return None
    
    def _retry_operation(self, operation, *args, **kwargs):
        """Execute operation with retry logic.
        
        Args:
            operation: Callable to execute
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Operation result
            
        Raises:
            Exception: If all retries fail
        """
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                return operation(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.debug(f"Retry {attempt + 1}/{self.max_retries} after {wait_time}s: {e}")
                    time.sleep(wait_time)
        
        raise last_error
    
    def import_batch(
        self,
        results: List[ExtractionResult],
        progress_bar: bool = True
    ) -> ImportStats:
        """Import multiple extraction results in batch.
        
        Args:
            results: List of extraction results
            progress_bar: Whether to show progress bar
            
        Returns:
            Import statistics
        """
        self.stats = ImportStats()  # Reset stats
        
        iterator = tqdm(results, desc="Importing to Neo4j") if progress_bar else results
        
        for result in iterator:
            self.import_extraction_result(result)
            
            # Update progress bar postfix
            if progress_bar and isinstance(iterator, tqdm):
                iterator.set_postfix({
                    "entities": self.stats.entities_created,
                    "relations": self.stats.relations_created,
                })
        
        return self.stats
    
    def import_from_json(
        self,
        json_path: str,
        progress_bar: bool = True
    ) -> ImportStats:
        """Import extraction results from JSON file.
        
        Args:
            json_path: Path to JSON file with extraction results
            progress_bar: Whether to show progress bar
            
        Returns:
            Import statistics
        """
        with open(json_path, 'r') as f:
            data = json.load(f)
        
        # Handle both single result and list of results
        if isinstance(data, list):
            results = [ExtractionResult(**item) for item in data]
        else:
            results = [ExtractionResult(**data)]
        
        return self.import_batch(results, progress_bar)
    
    def import_from_directory(
        self,
        directory: str,
        pattern: str = "*.json",
        progress_bar: bool = True
    ) -> ImportStats:
        """Import all JSON files from a directory.
        
        Args:
            directory: Directory containing JSON files
            pattern: File pattern to match
            progress_bar: Whether to show progress bar
            
        Returns:
            Import statistics
        """
        import glob
        
        self.stats = ImportStats()  # Reset stats
        
        json_files = list(Path(directory).glob(pattern))
        
        if not json_files:
            logger.warning(f"No files matching {pattern} found in {directory}")
            return self.stats
        
        logger.info(f"Found {len(json_files)} files to import from {directory}")
        
        iterator = tqdm(json_files, desc="Processing files") if progress_bar else json_files
        
        for file_path in iterator:
            try:
                file_stats = self.import_from_json(str(file_path), progress_bar=False)
                
                # Aggregate stats
                self.stats.entities_created += file_stats.entities_created
                self.stats.entities_updated += file_stats.entities_updated
                self.stats.entities_failed += file_stats.entities_failed
                self.stats.relations_created += file_stats.relations_created
                self.stats.relations_failed += file_stats.relations_failed
                self.stats.documents_processed += file_stats.documents_processed
                self.stats.documents_failed += file_stats.documents_failed
                self.stats.processing_time_ms += file_stats.processing_time_ms
                self.stats.errors.extend(file_stats.errors)
                
            except Exception as e:
                logger.error(f"Failed to process {file_path}: {e}")
                self.stats.documents_failed += 1
                self.stats.errors.append(f"{file_path}: {str(e)}")
        
        return self.stats


def import_extraction_results(
    results: List[ExtractionResult],
    neo4j_uri: Optional[str] = None,
    neo4j_user: Optional[str] = None,
    neo4j_password: Optional[str] = None,
    batch_size: int = 1000,
) -> ImportStats:
    """Convenience function to import extraction results.
    
    Args:
        results: List of extraction results to import
        neo4j_uri: Neo4j URI (optional, uses config if not provided)
        neo4j_user: Neo4j username (optional)
        neo4j_password: Neo4j password (optional)
        batch_size: Batch size for imports
        
    Returns:
        Import statistics
    """
    # Override config if connection params provided
    if neo4j_uri:
        from src.kg.client import Neo4jConfig
        config = Neo4jConfig(
            uri=neo4j_uri,
            username=neo4j_user or "neo4j",
            password=neo4j_password or "password",
        )
        client = Neo4jClient(config)
    else:
        client = get_client()
    
    # Ensure connection
    if not client.connect():
        raise RuntimeError("Failed to connect to Neo4j")
    
    # Initialize schema
    client.init_schema()
    
    # Import
    importer = BulkImporter(client=client, batch_size=batch_size)
    stats = importer.import_batch(results)
    
    logger.info(f"Import complete: {stats.to_dict()}")
    
    return stats
