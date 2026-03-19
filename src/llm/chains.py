"""Entity Extraction Chains Module.

Provides structured entity and relation extraction using LangChain and Pydantic models.
Includes confidence scoring and fallback to rule-based extraction when LLM confidence is low.
"""

import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
import json
import re

from src.llm.client import UnifiedLLMClient, LLMResponse

logger = logging.getLogger(__name__)


# ==================== Pydantic Models ====================

class Entity(BaseModel):
    """Base entity model with confidence scoring."""
    
    name: str = Field(..., description="Entity name/identifier")
    type: str = Field(..., description="Entity type (e.g., BugReport, Component)")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Additional properties")
    confidence: float = Field(
        default=1.0, 
        ge=0.0, 
        le=1.0,
        description="Confidence score (0.0-1.0)"
    )
    source_text: str = Field(default="", description="Source text that generated this entity")


class Relation(BaseModel):
    """Base relation model with confidence scoring."""
    
    source: str = Field(..., description="Source entity name/ID")
    target: str = Field(..., description="Target entity name/ID")
    type: str = Field(..., description="Relation type (e.g., HAS_COMPONENT)")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Additional properties")
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score (0.0-1.0)"
    )
    source_text: str = Field(default="", description="Source text that generated this relation")


class ExtractionResult(BaseModel):
    """Complete extraction result with entities and relations."""
    
    entities: List[Entity] = Field(default_factory=list, description="Extracted entities")
    relations: List[Relation] = Field(default_factory=list, description="Extracted relations")
    source_document: str = Field(default="", description="Source document identifier")
    processing_metadata: Dict[str, Any] = Field(default_factory=dict, description="Processing metadata")
    
    def get_entities_by_type(self, entity_type: str) -> List[Entity]:
        """Get all entities of a specific type."""
        return [e for e in self.entities if e.type == entity_type]
    
    def get_entities_by_confidence(self, min_confidence: float = 0.7) -> List[Entity]:
        """Get entities above a confidence threshold."""
        return [e for e in self.entities if e.confidence >= min_confidence]
    
    def get_relations_by_type(self, relation_type: str) -> List[Relation]:
        """Get all relations of a specific type."""
        return [r for r in self.relations if r.type == relation_type]
    
    def to_kg_format(self) -> Dict[str, List[Dict[str, Any]]]:
        """Convert to knowledge graph import format."""
        return {
            "entities": [
                {
                    "name": e.name,
                    "type": e.type,
                    "properties": e.properties,
                    "confidence": e.confidence,
                }
                for e in self.entities
            ],
            "relations": [
                {
                    "source": r.source,
                    "target": r.target,
                    "type": r.type,
                    "properties": r.properties,
                    "confidence": r.confidence,
                }
                for r in self.relations
            ],
        }


# ==================== Entity Types ====================

DOCUMENT_SCHEMA = """
Document:
  - doc_id: string (required) - Unique document identifier (set from filename before LLM call)
  - title: string (required) - Brief descriptive title for the document
  - document_type: string (optional) - One of: invoice, purchase_order, contract, marketing,
      technical_report, certificate, test_output, correspondence, form, other
  - language: string (optional) - Primary language (e.g., English, French)
  - summary: string (optional) - One-sentence summary of document content
"""

ENTITY_TYPES = {
    "Document": {
        "description": "The document being processed — any type of PDF",
        "required": ["doc_id", "title"],
        "optional": ["document_type", "language", "summary"],
    },
    "Person": {
        "description": "Person mentioned in the document (author, signatory, contact, etc.)",
        "required": ["name"],
        "optional": ["email", "role", "title"],
    },
    "Organization": {
        "description": "Company, institution, or team mentioned in the document",
        "required": ["name"],
        "optional": ["type", "address", "domain"],
    },
    "Technology": {
        "description": "Software, hardware, standard, or technical system mentioned",
        "required": ["name"],
        "optional": ["type", "version", "vendor"],
    },
    "Topic": {
        "description": "Subject area, concept, or theme covered by the document",
        "required": ["name"],
        "optional": ["description", "category"],
    },
    "Reference": {
        "description": "Identifier or code in the document: PO number, invoice ID, contract ref, etc.",
        "required": ["value"],
        "optional": ["type", "issuer"],
    },
    "Location": {
        "description": "Geographic location, address, or place mentioned in the document",
        "required": ["name"],
        "optional": ["address", "city", "country"],
    },
}

RELATION_TYPES = {
    "MENTIONS_PERSON": "Document -> Person - Document mentions this person",
    "MENTIONS_ORG":    "Document -> Organization - Document mentions this organization",
    "MENTIONS_TECH":   "Document -> Technology - Document mentions this technology",
    "COVERS_TOPIC":    "Document -> Topic - Document covers this topic",
    "HAS_REFERENCE":   "Document -> Reference - Document contains this identifier/code",
    "HAS_LOCATION":    "Document -> Location - Document mentions this location",
    "AFFILIATED_WITH": "Person -> Organization - Person is affiliated with this organization",
    "RELATED_TO":      "Document -> Document - Document is related to another document",
    "LOCATED_AT":      "Organization -> Location - Organization is located at this place",
}


# ==================== Extraction Chain ====================

SYSTEM_PROMPT_TEMPLATE = """You are an expert at extracting structured information from diverse documents.

ENTITY TYPES you must extract:
{entity_types}

RELATION TYPES you must extract:
{relation_types}

RULES:
1. Always create exactly ONE Document entity whose name equals the DOCUMENT ID given by the user.
2. Classify document_type as one of: invoice, purchase_order, contract, marketing, technical_report, certificate, test_output, correspondence, form, other.
3. Extract every Person, Organization, Technology, Topic, Reference, and Location you can find.
4. Assign confidence 0.0-1.0 per entity/relation. Include even low-confidence extractions.
5. Use the exact name/value as it appears in the text.
6. Include a short source_text snippet (max 80 chars) for each extraction.
7. Respond ONLY with a single JSON object — no explanation, no markdown fences, no thinking text.

JSON FORMAT:
{{
  "entities": [
    {{"name": "...", "type": "Document|Person|Organization|Technology|Topic|Reference|Location", "properties": {{}}, "confidence": 0.9, "source_text": "..."}},
    ...
  ],
  "relations": [
    {{"source": "...", "target": "...", "type": "MENTIONS_PERSON|MENTIONS_ORG|...", "properties": {{}}, "confidence": 0.9, "source_text": "..."}},
    ...
  ],
  "source_document": "DOCUMENT_ID",
  "processing_metadata": {{}}
}}"""


class EntityExtractionChain:
    """Chain for extracting entities and relations from text."""
    
    def __init__(
        self,
        llm_client: Optional[UnifiedLLMClient] = None,
        min_confidence: float = 0.7,
        enable_fallback: bool = True,
    ):
        """Initialize extraction chain.
        
        Args:
            llm_client: LLM client to use. If None, creates default.
            min_confidence: Minimum confidence threshold for accepting LLM extraction
            enable_fallback: Whether to enable rule-based fallback for low-confidence extractions
        """
        self.llm_client = llm_client or UnifiedLLMClient()
        self.min_confidence = min_confidence
        self.enable_fallback = enable_fallback
        self.parser = PydanticOutputParser(pydantic_object=ExtractionResult)
        
    def _format_entity_types(self) -> str:
        """Format entity types for prompt."""
        lines = []
        for name, schema in ENTITY_TYPES.items():
            lines.append(f"  {name}: {schema['description']}")
            lines.append(f"    Required: {', '.join(schema['required'])}")
            if schema['optional']:
                lines.append(f"    Optional: {', '.join(schema['optional'])}")
        return "\n".join(lines)
    
    def _format_relation_types(self) -> str:
        """Format relation types for prompt."""
        lines = []
        for name, description in RELATION_TYPES.items():
            lines.append(f"  {name}: {description}")
        return "\n".join(lines)
    
    def _build_prompt(self, text: str, document_id: str = "") -> str:
        """Build extraction prompt."""
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            entity_types=self._format_entity_types(),
            relation_types=self._format_relation_types(),
        )
        
        user_prompt = f"""DOCUMENT ID: {document_id}

TEXT:
{text}

Extract all entities and relations. Return JSON only."""
        return system_prompt, user_prompt
    
    def extract(self, text: str, document_id: str = "") -> ExtractionResult:
        """Extract entities and relations from text.
        
        Args:
            text: Text to extract from
            document_id: Document identifier for tracking
            
        Returns:
            ExtractionResult with entities and relations
        """
        system_prompt, user_prompt = self._build_prompt(text, document_id)
        
        # Call LLM
        response = self.llm_client.chat_text(
            prompt=user_prompt,
            system_prompt=system_prompt,
        )
        
        # Parse response
        try:
            result = self._parse_response(response.content, document_id)
            result.processing_metadata = {
                "llm_provider": response.provider,
                "llm_model": response.model,
                "token_usage": response.token_usage.to_dict(),
                "processing_time_ms": response.processing_time_ms,
            }
        except Exception as e:
            logger.error(f"Failed to parse LLM response: {e}")
            logger.debug(f"Raw response: {response.content}")
            
            # Fallback to rule-based if enabled
            if self.enable_fallback:
                logger.info("Falling back to rule-based extraction")
                result = self._rule_based_extraction(text, document_id)
            else:
                result = ExtractionResult(
                    source_document=document_id,
                    processing_metadata={"error": str(e)},
                )
        
        return result
    
    def _parse_response(self, content: str, document_id: str) -> ExtractionResult:
        """Parse LLM response into ExtractionResult."""
        # Strip Qwen3 / DeepSeek thinking blocks (<think>...</think>)
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()

        # Strip markdown fences
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        if not content:
            logger.warning(f"Empty content after stripping for document '{document_id}' — model returned only a think block or empty response")
            raise ValueError("Empty response after stripping think blocks and markdown fences")

        # Try parsing as JSON
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            logger.debug(f"Raw content that failed JSON parse (first 500 chars): {content[:500]}")
            # Try to extract JSON from markdown
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                raise
        
        # Valid entity types — anything else is rejected
        VALID_TYPES = {"Document", "Person", "Organization", "Technology", "Topic", "Reference", "Location"}

        # Common hallucinated type → canonical type remapping
        TYPE_REMAP = {
            # case variants
            "PERSON": "Person", "ORGANIZATION": "Organization", "LOCATION": "Location",
            # geo subtypes → Location
            "City": "Location", "Country": "Location", "Building": "Location",
            "Office": "Location", "Address": "Location", "Region": "Location",
            # numeric/value types → Reference
            "Date": "Reference", "DATE": "Reference", "Number": "Reference",
            "MonetaryValue": "Reference", "Quantity": "Reference", "Dimension": "Reference",
            "Certificate": "Reference", "Currency": "Reference", "ID": "Reference",
            # org subtypes → Organization
            "Bank": "Organization", "Company": "Organization", "Institution": "Organization",
            # tech/topic subtypes
            "Website": "Technology", "Software": "Technology", "Hardware": "Technology",
            "Product": "Technology", "PRODUCT": "Technology",
            "Material": "Topic", "Book": "Topic", "Form": "Topic",
            "Process": "Topic", "Concept": "Topic", "Category": "Topic",
        }

        # Convert to ExtractionResult
        entities = []
        for e_data in data.get("entities", []):
            raw_type = e_data.get("type", "")
            raw_name = e_data.get("name", "")
            entity_type = TYPE_REMAP.get(raw_type, raw_type)
            if not raw_name or not raw_name.strip():
                logger.debug(f"Skipping entity with empty name (type={raw_type!r})")
                continue
            if entity_type not in VALID_TYPES:
                logger.debug(f"Skipping entity with unknown type '{raw_type}': {raw_name}")
                continue
            entity = Entity(
                name=raw_name,
                type=entity_type,
                properties=e_data.get("properties", {}),
                confidence=e_data.get("confidence", 0.5),
                source_text=e_data.get("source_text", ""),
            )
            # Clean up entity names
            entity = self._clean_entity_name(entity, document_id)
            entities.append(entity)

        # Ensure a Document entity always exists for this document_id
        entity_names = {e.name for e in entities}
        if document_id and document_id not in entity_names:
            entities.append(Entity(
                name=document_id,
                type="Document",
                properties={"doc_id": document_id, "title": document_id},
                confidence=1.0,
                source_text="",
            ))
            entity_names.add(document_id)

        # Valid relation types
        VALID_RELATION_TYPES = {
            "MENTIONS_PERSON", "MENTIONS_ORG", "MENTIONS_TECH",
            "COVERS_TOPIC", "HAS_REFERENCE", "HAS_LOCATION",
            "AFFILIATED_WITH", "RELATED_TO", "LOCATED_AT",
        }
        RELATION_REMAP = {
            "MENTIONS": "RELATED_TO",
            "RELATED": "RELATED_TO",
            "HAS_LOCATION": "HAS_LOCATION",
        }

        # Keep relations where both endpoints exist; also accept document_id as implicit endpoint
        valid_names = entity_names | {document_id}
        relations = []
        for r_data in data.get("relations", []):
            source = r_data.get("source", "")
            target = r_data.get("target", "")
            raw_rel_type = r_data.get("type", "")
            rel_type = RELATION_REMAP.get(raw_rel_type, raw_rel_type)

            if not rel_type or not rel_type.strip():
                logger.debug(f"Skipping relation with empty type: {source!r} -> {target!r}")
                continue
            if not source or not target:
                logger.debug(f"Skipping relation with empty source/target: {source!r} -> {target!r}")
                continue
            if rel_type not in VALID_RELATION_TYPES:
                logger.debug(f"Skipping relation with unknown type '{raw_rel_type}': {source} -> {target}")
                continue

            if source in valid_names and target in valid_names:
                relations.append(Relation(
                    source=source,
                    target=target,
                    type=rel_type,
                    properties=r_data.get("properties", {}),
                    confidence=r_data.get("confidence", 0.5),
                    source_text=r_data.get("source_text", ""),
                ))
        
        return ExtractionResult(
            entities=entities,
            relations=relations,
            source_document=document_id,
        )
    
    def _clean_entity_name(self, entity: Entity, document_id: str) -> Entity:
        """Clean up entity names to ensure they're valid and meaningful.

        For Document entities the name must equal the doc_id so downstream
        relation lookups work correctly.
        """
        if not entity.name:
            return entity

        # Document name must equal the document_id supplied to the chain
        if entity.type == "Document":
            entity.name = document_id or entity.properties.get("doc_id", entity.name)
            if not entity.properties.get("doc_id"):
                entity.properties["doc_id"] = entity.name

        # Remove characters that cause Cypher issues
        entity.name = entity.name.replace('"', '').replace("'", "").strip()

        return entity

    def _rule_based_extraction(self, text: str, document_id: str) -> ExtractionResult:
        """Fallback rule-based extraction for when LLM fails or has low confidence.

        Creates one Document entity always, then extracts emails as Person and
        common reference patterns as Reference entities.
        """
        entities = []
        relations = []

        # Always create a Document entity
        entities.append(Entity(
            name=document_id,
            type="Document",
            properties={"doc_id": document_id, "title": document_id},
            confidence=1.0,
            source_text="",
        ))

        # Extract email addresses → Person
        email_pattern = r'[\w.\-]+@[\w.\-]+\.\w+'
        seen_emails: set = set()
        for match in re.finditer(email_pattern, text):
            email = match.group()
            if email in seen_emails:
                continue
            seen_emails.add(email)
            person_name = email.split('@')[0]
            entities.append(Entity(
                name=person_name,
                type="Person",
                properties={"email": email},
                confidence=0.6,
                source_text=email,
            ))
            relations.append(Relation(
                source=document_id,
                target=person_name,
                type="MENTIONS_PERSON",
                confidence=0.6,
                source_text=email,
            ))

        # Extract reference patterns: PO#, Invoice No., Contract ID, etc.
        ref_patterns = [
            (r'(?:P\.?O\.?|Purchase Order)[#\s:No.]*([A-Z0-9\-]{4,})', "purchase_order"),
            (r'(?:Invoice|INV)[#\s:No.]*([A-Z0-9\-]{4,})', "invoice"),
            (r'(?:Contract)[#\s:ID]*([A-Z0-9\-]{4,})', "contract"),
        ]
        seen_refs: set = set()
        for pattern, ref_type in ref_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                value = match.group(1).strip()
                if value in seen_refs:
                    continue
                seen_refs.add(value)
                entities.append(Entity(
                    name=value,
                    type="Reference",
                    properties={"value": value, "type": ref_type},
                    confidence=0.6,
                    source_text=match.group(),
                ))
                relations.append(Relation(
                    source=document_id,
                    target=value,
                    type="HAS_REFERENCE",
                    confidence=0.6,
                    source_text=match.group(),
                ))

        return ExtractionResult(
            entities=entities,
            relations=relations,
            source_document=document_id,
            processing_metadata={"method": "rule_based_fallback"},
        )


# ==================== Convenience Functions ====================

def extract_entities(
    text: str,
    document_id: str = "",
    provider: Optional[str] = None,
    min_confidence: float = 0.7,
) -> ExtractionResult:
    """Convenience function to extract entities from text.
    
    Args:
        text: Text to extract from
        document_id: Document identifier
        provider: LLM provider to use (None for default)
        min_confidence: Minimum confidence threshold
        
    Returns:
        ExtractionResult
    """
    from src.llm.client import get_client
    
    client = get_client()
    if provider:
        client.switch_provider(provider)
    
    chain = EntityExtractionChain(
        llm_client=client,
        min_confidence=min_confidence,
    )
    
    return chain.extract(text, document_id)
