"""Knowledge Graph Schema Module.

Defines the complete entity and relation schema for the Neo4j knowledge graph.
Includes 7 entity types and 9 relation types for diverse document processing.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field


@dataclass
class EntitySchema:
    """Schema definition for an entity type."""
    
    name: str
    description: str
    required_properties: List[str] = field(default_factory=list)
    optional_properties: List[str] = field(default_factory=list)
    property_types: Dict[str, str] = field(default_factory=dict)
    
    def get_all_properties(self) -> List[str]:
        """Get all property names (required + optional)."""
        return self.required_properties + self.optional_properties
    
    def validate(self, properties: Dict[str, Any]) -> List[str]:
        """Validate properties against schema, return list of missing required fields."""
        missing = []
        for required in self.required_properties:
            if required not in properties or properties[required] is None:
                missing.append(required)
        return missing


@dataclass
class RelationSchema:
    """Schema definition for a relation type."""
    
    name: str
    description: str
    source_types: List[str] = field(default_factory=list)
    target_types: List[str] = field(default_factory=list)
    required_properties: List[str] = field(default_factory=list)
    optional_properties: List[str] = field(default_factory=list)


# ==================== Entity Schema Definitions ====================

ENTITY_SCHEMAS = {
    "Document": EntitySchema(
        name="Document",
        description="Any PDF document being processed (purchase order, contract, report, etc.)",
        required_properties=["doc_id", "title"],
        optional_properties=[
            "document_type", "language", "page_count",
            "source_tracker", "source_bug_id", "summary",
        ],
        property_types={
            "doc_id": "string",
            "title": "string",
            "document_type": "string",  # invoice, purchase_order, contract, marketing, technical_report, certificate, test_output, correspondence, form, other
            "language": "string",
            "page_count": "integer",
            "source_tracker": "string",  # GHOSTSCRIPT, MOZILLA, TIKA, etc.
            "source_bug_id": "string",
            "summary": "string",
        },
    ),

    "Person": EntitySchema(
        name="Person",
        description="Person mentioned in any document (author, signatory, contact, etc.)",
        required_properties=["name"],
        optional_properties=["email", "role", "title"],
        property_types={
            "name": "string",
            "email": "string",
            "role": "string",
            "title": "string",
        },
    ),

    "Organization": EntitySchema(
        name="Organization",
        description="Company, institution, or team mentioned in documents",
        required_properties=["name"],
        optional_properties=["type", "address", "domain"],
        property_types={
            "name": "string",
            "type": "string",  # company, government, nonprofit, vendor, etc.
            "address": "string",
            "domain": "string",
        },
    ),

    "Technology": EntitySchema(
        name="Technology",
        description="Software, hardware, standard, or technical system mentioned",
        required_properties=["name"],
        optional_properties=["type", "version", "vendor"],
        property_types={
            "name": "string",
            "type": "string",  # language, framework, library, tool, hardware, standard
            "version": "string",
            "vendor": "string",
        },
    ),

    "Topic": EntitySchema(
        name="Topic",
        description="Subject area, concept, or theme covered by a document",
        required_properties=["name"],
        optional_properties=["description", "category"],
        property_types={
            "name": "string",
            "description": "string",
            "category": "string",
        },
    ),

    "Reference": EntitySchema(
        name="Reference",
        description="Identifier or code found in a document (PO number, invoice ID, contract ref, etc.)",
        required_properties=["value"],
        optional_properties=["type", "issuer"],
        property_types={
            "value": "string",
            "type": "string",  # purchase_order, invoice, contract, certificate, tracking_number, other
            "issuer": "string",
        },
    ),

    "Location": EntitySchema(
        name="Location",
        description="Geographic location, address, or place mentioned in documents",
        required_properties=["name"],
        optional_properties=["address", "city", "country"],
        property_types={
            "name": "string",
            "address": "string",
            "city": "string",
            "country": "string",
        },
    ),
}


# ==================== Relation Schema Definitions ====================

RELATION_SCHEMAS = {
    "MENTIONS_PERSON": RelationSchema(
        name="MENTIONS_PERSON",
        description="Document mentions a person",
        source_types=["Document"],
        target_types=["Person"],
    ),

    "MENTIONS_ORG": RelationSchema(
        name="MENTIONS_ORG",
        description="Document mentions an organization",
        source_types=["Document"],
        target_types=["Organization"],
    ),

    "MENTIONS_TECH": RelationSchema(
        name="MENTIONS_TECH",
        description="Document mentions a technology",
        source_types=["Document"],
        target_types=["Technology"],
    ),

    "COVERS_TOPIC": RelationSchema(
        name="COVERS_TOPIC",
        description="Document covers a topic or subject area",
        source_types=["Document"],
        target_types=["Topic"],
    ),

    "HAS_REFERENCE": RelationSchema(
        name="HAS_REFERENCE",
        description="Document contains an identifier or reference code",
        source_types=["Document"],
        target_types=["Reference"],
    ),

    "HAS_LOCATION": RelationSchema(
        name="HAS_LOCATION",
        description="Document mentions a geographic location",
        source_types=["Document"],
        target_types=["Location"],
    ),

    "AFFILIATED_WITH": RelationSchema(
        name="AFFILIATED_WITH",
        description="Person is affiliated with an organization",
        source_types=["Person"],
        target_types=["Organization"],
    ),

    "RELATED_TO": RelationSchema(
        name="RELATED_TO",
        description="Document is related to another document (e.g., amendment, response)",
        source_types=["Document"],
        target_types=["Document"],
    ),

    "LOCATED_AT": RelationSchema(
        name="LOCATED_AT",
        description="Organization is located at a geographic location",
        source_types=["Organization"],
        target_types=["Location"],
    ),
}


# ==================== Schema Utilities ====================

def get_entity_schema(entity_type: str) -> Optional[EntitySchema]:
    """Get schema for an entity type."""
    return ENTITY_SCHEMAS.get(entity_type)


def get_relation_schema(relation_type: str) -> Optional[RelationSchema]:
    """Get schema for a relation type."""
    return RELATION_SCHEMAS.get(relation_type)


def get_all_entity_types() -> List[str]:
    """Get list of all entity type names."""
    return list(ENTITY_SCHEMAS.keys())


def get_all_relation_types() -> List[str]:
    """Get list of all relation type names."""
    return list(RELATION_SCHEMAS.keys())


def validate_entity(entity_type: str, properties: Dict[str, Any]) -> List[str]:
    """Validate entity properties against schema.
    
    Returns:
        List of missing required property names.
    """
    schema = get_entity_schema(entity_type)
    if not schema:
        return [f"Unknown entity type: {entity_type}"]
    return schema.validate(properties)


def get_cypher_create_node(entity_type: str, properties: Dict[str, Any]) -> tuple:
    """Generate Cypher CREATE statement for a node.
    
    Args:
        entity_type: Type of entity (label)
        properties: Entity properties
        
    Returns:
        Tuple of (query_string, params_dict)
    """
    schema = get_entity_schema(entity_type)
    
    # Build property string
    props = []
    params = {}
    
    for key, value in properties.items():
        if value is not None:
            # Skip list types for now (handle separately)
            if schema and schema.property_types.get(key) == "list":
                continue
            props.append(f"{key}: ${key}")
            params[key] = value
    
    prop_string = ", ".join(props)
    query = f"CREATE (n:{entity_type} {{{prop_string}}}) RETURN n"
    
    return query, params


def get_cypher_merge_node(entity_type: str, match_property: str, properties: Dict[str, Any]) -> tuple:
    """Generate Cypher MERGE statement for idempotent node creation.
    
    Args:
        entity_type: Type of entity (label)
        match_property: Property to match on for MERGE
        properties: Entity properties
        
    Returns:
        Tuple of (query_string, params_dict)
    """
    schema = get_entity_schema(entity_type)
    
    # Separate match property from others
    match_value = properties.get(match_property)
    other_props = {k: v for k, v in properties.items() if k != match_property and v is not None}
    
    # Build SET clause for other properties
    set_clauses = []
    params = {match_property: match_value}
    
    for key, value in other_props.items():
        if schema and schema.property_types.get(key) == "list":
            continue
        set_clauses.append(f"n.{key} = ${key}")
        params[key] = value
    
    set_string = " SET " + ", ".join(set_clauses) if set_clauses else ""
    
    query = f"MERGE (n:{entity_type} {{{match_property}: ${match_property}}}){set_string} RETURN n"
    
    return query, params


def get_cypher_merge_relation(
    source_label: str,
    source_prop: str,
    source_value: Any,
    target_label: str,
    target_prop: str,
    target_value: Any,
    rel_type: str,
    properties: Optional[Dict[str, Any]] = None
) -> tuple:
    """Generate Cypher MERGE statement for a relationship.
    
    Args:
        source_label: Source node label
        source_prop: Source node match property
        source_value: Source node match value
        target_label: Target node label
        target_prop: Target node match property
        target_value: Target node match value
        rel_type: Relationship type
        properties: Optional relationship properties
        
    Returns:
        Tuple of (query_string, params_dict)
    """
    props = properties or {}
    
    # Build relationship properties string
    prop_clauses = []
    params = {
        "source_value": source_value,
        "target_value": target_value,
    }
    
    for key, value in props.items():
        if value is not None:
            prop_clauses.append(f"r.{key} = ${key}")
            params[key] = value
    
    rel_props = " SET " + ", ".join(prop_clauses) if prop_clauses else ""
    
    query = f"""
    MATCH (source:{source_label} {{{source_prop}: $source_value}})
    MATCH (target:{target_label} {{{target_prop}: $target_value}})
    MERGE (source)-[r:{rel_type}]->(target)
    {rel_props}
    RETURN r
    """
    
    return query.strip(), params
