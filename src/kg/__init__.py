"""Knowledge Graph Package.

Provides Neo4j-based knowledge graph construction and management for diverse
PDF documents. Supports entity extraction, relation building, and bulk import.

Main exports:
    - Neo4jClient: Neo4j database client
    - BulkImporter: Efficient bulk import pipeline
    - ImportStats: Import statistics

Schema Definitions:
    - ENTITY_SCHEMAS: Complete entity type definitions
    - RELATION_SCHEMAS: Complete relation type definitions
    - get_entity_schema: Get schema for entity type
    - get_relation_schema: Get schema for relation type

Cypher Generation:
    - get_cypher_merge_node: Generate MERGE for nodes
    - get_cypher_merge_relation: Generate MERGE for relations

Client Management:
    - get_client: Get singleton Neo4j client
    - reset_client: Reset singleton client

Example usage:
    >>> from src.kg import Neo4jClient, BulkImporter
    >>>
    >>> # Connect and initialize
    >>> client = Neo4jClient()
    >>> client.connect()
    >>> client.init_schema()
    >>>
    >>> # Import extraction results
    >>> importer = BulkImporter(client)
    >>> stats = importer.import_batch(extraction_results)
    >>> print(f"Imported {stats.entities_created} entities")
    >>>
    >>> # Query the graph
    >>> results = client.run_query("MATCH (n:Document) RETURN n LIMIT 10")

Entity Types (7 total):
    - Document: Any PDF document (purchase order, contract, report, etc.)
    - Person: People mentioned in documents
    - Organization: Companies, institutions, or teams
    - Technology: Software, hardware, or technical standards
    - Topic: Subject areas and themes covered by documents
    - Reference: Identifiers such as PO numbers, invoice IDs, contract refs
    - Location: Geographic locations and addresses

Relation Types (9 total):
    - MENTIONS_PERSON: Document -> Person
    - MENTIONS_ORG: Document -> Organization
    - MENTIONS_TECH: Document -> Technology
    - COVERS_TOPIC: Document -> Topic
    - HAS_REFERENCE: Document -> Reference
    - HAS_LOCATION: Document -> Location
    - AFFILIATED_WITH: Person -> Organization
    - RELATED_TO: Document -> Document
    - LOCATED_AT: Organization -> Location
"""

# Client imports
from src.kg.client import (
    Neo4jClient,
    Neo4jConfig,
    get_client,
    reset_client,
)

# Schema imports
from src.kg.schema import (
    EntitySchema,
    RelationSchema,
    ENTITY_SCHEMAS,
    RELATION_SCHEMAS,
    get_entity_schema,
    get_relation_schema,
    get_all_entity_types,
    get_all_relation_types,
    validate_entity,
    get_cypher_merge_node,
    get_cypher_merge_relation,
)

# Import imports
from src.kg.bulk_import import (
    BulkImporter,
    ImportStats,
    import_extraction_results,
)

__all__ = [
    # Client
    "Neo4jClient",
    "Neo4jConfig",
    "get_client",
    "reset_client",
    # Schema
    "EntitySchema",
    "RelationSchema",
    "ENTITY_SCHEMAS",
    "RELATION_SCHEMAS",
    "get_entity_schema",
    "get_relation_schema",
    "get_all_entity_types",
    "get_all_relation_types",
    "validate_entity",
    "get_cypher_merge_node",
    "get_cypher_merge_relation",
    # Import
    "BulkImporter",
    "ImportStats",
    "import_extraction_results",
]
