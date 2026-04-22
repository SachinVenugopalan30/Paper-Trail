"""Classical Information Extraction baseline using spaCy NER + dependency rules.

Implements the same ExtractionResult interface as EntityExtractionChain so it
can be used as a drop-in replacement in build_knowledge_graph.py for the
E4-E6 ablation experiments.

Usage:
    from src.extraction.classical_ie import ClassicalExtractor
    extractor = ClassicalExtractor()
    result = extractor.extract(text, document_id="MOZILLA-1000230-0_page_1")
"""

import logging
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Lazy-loaded spaCy model (loaded on first call to avoid startup cost)
_nlp = None

# Map spaCy NER labels → project entity types
SPACY_TO_PROJECT_TYPE: Dict[str, str] = {
    "PERSON": "Person",
    "ORG": "Organization",
    "GPE": "Location",
    "LOC": "Location",
    "PRODUCT": "Technology",
    "DATE": "Reference",
    "MONEY": "Reference",
    "CARDINAL": "Reference",
    "ORDINAL": "Reference",
}

# Document-level relation type for each entity type
DOC_RELATION_FOR_TYPE: Dict[str, str] = {
    "Person": "MENTIONS_PERSON",
    "Organization": "MENTIONS_ORG",
    "Technology": "MENTIONS_TECH",
    "Topic": "COVERS_TOPIC",
    "Reference": "HAS_REFERENCE",
    "Location": "HAS_LOCATION",
}

# Preposition patterns → relation type (for entity-to-entity relations)
PREP_RELATION_MAP: Dict[str, str] = {
    "of": "AFFILIATED_WITH",
    "at": "AFFILIATED_WITH",
    "from": "AFFILIATED_WITH",
    "in": "HAS_LOCATION",
    "for": "AFFILIATED_WITH",
}


def _get_nlp():
    """Load spaCy model on first use."""
    global _nlp
    if _nlp is None:
        try:
            import spacy
            _nlp = spacy.load("en_core_web_sm")
        except OSError:
            raise RuntimeError(
                "spaCy model 'en_core_web_sm' not found. "
                "Run: python -m spacy download en_core_web_sm"
            )
    return _nlp


def _sentence_containing(doc, span) -> str:
    """Return the sentence text that contains *span*."""
    for sent in doc.sents:
        if span.start >= sent.start and span.end <= sent.end:
            return sent.text.strip()
    return span.sent.text.strip() if hasattr(span, "sent") else ""


class ClassicalExtractor:
    """spaCy NER + dependency-pattern relation extractor.

    Produces ExtractionResult objects identical in structure to those from
    EntityExtractionChain, enabling a fair apples-to-apples comparison in
    E4-E6 ablations.
    """

    ENTITY_CONFIDENCE = 0.7
    RELATION_CONFIDENCE = 0.6
    EXTRACTION_METHOD = "classical_spacy"
    SPACY_MODEL = "en_core_web_sm"

    def extract(self, text: str, document_id: str = "") -> "ExtractionResult":
        """Extract entities and relations from *text*.

        Args:
            text: Raw page text.
            document_id: Identifier for the source document (used as the
                Document node name and as the source/target of doc-level
                relations).

        Returns:
            ExtractionResult with entities and relations.
        """
        # Import here to avoid circular deps at module load time
        from src.llm.chains import Entity, ExtractionResult, Relation

        nlp = _get_nlp()
        # spaCy has a token limit; truncate very long texts to avoid OOM
        doc = nlp(text[:100_000])

        # ── 1. Entity extraction via NER ──────────────────────────────────────
        entities: List[Entity] = []
        seen_names: Set[str] = set()          # dedup by (normalized_name, type)

        # Always add a Document entity for the current document
        if document_id:
            entities.append(
                Entity(
                    name=document_id,
                    type="Document",
                    properties={"extraction_method": self.EXTRACTION_METHOD},
                    confidence=1.0,
                    source_text="",
                )
            )
            seen_names.add((document_id.lower(), "Document"))

        for ent in doc.ents:
            entity_type = SPACY_TO_PROJECT_TYPE.get(ent.label_)
            if entity_type is None:
                continue
            name = ent.text.strip()
            if not name:
                continue
            key = (name.lower(), entity_type)
            if key in seen_names:
                continue
            seen_names.add(key)

            props: Dict = {"extraction_method": self.EXTRACTION_METHOD}
            if entity_type == "Reference":
                props["type"] = ent.label_   # keep original spaCy label as ref type

            source_text = _sentence_containing(doc, ent)
            entities.append(
                Entity(
                    name=name,
                    type=entity_type,
                    properties=props,
                    confidence=self.ENTITY_CONFIDENCE,
                    source_text=source_text,
                )
            )

        # ── 2. Relation extraction ─────────────────────────────────────────────
        relations: List[Relation] = []
        seen_rels: Set[Tuple[str, str, str]] = set()  # (source, target, type)

        # Map entity names → their type for quick lookup
        entity_type_map: Dict[str, str] = {e.name: e.type for e in entities}

        def _add_relation(source: str, target: str, rel_type: str, src_text: str = "") -> None:
            key = (source, target, rel_type)
            if key in seen_rels:
                return
            seen_rels.add(key)
            relations.append(
                Relation(
                    source=source,
                    target=target,
                    type=rel_type,
                    properties={"extraction_method": self.EXTRACTION_METHOD},
                    confidence=self.RELATION_CONFIDENCE,
                    source_text=src_text,
                )
            )

        # 2a. Document ↔ Entity relations for every extracted entity
        if document_id:
            for ent_obj in entities:
                if ent_obj.type == "Document":
                    continue
                rel_type = DOC_RELATION_FOR_TYPE.get(ent_obj.type)
                if rel_type:
                    _add_relation(document_id, ent_obj.name, rel_type, ent_obj.source_text)

        # 2b. Dependency-pattern entity-to-entity relations
        for token in doc:
            # Subject–verb–object: both subject and object must be NER entities
            if token.dep_ == "ROOT":
                subj_spans = [c for c in token.children if c.dep_ in ("nsubj", "nsubjpass")]
                obj_spans = [c for c in token.children if c.dep_ in ("dobj", "pobj", "attr")]
                for subj in subj_spans:
                    for obj in obj_spans:
                        subj_name = _resolve_entity_name(subj, doc)
                        obj_name = _resolve_entity_name(obj, doc)
                        if subj_name in entity_type_map and obj_name in entity_type_map:
                            _add_relation(subj_name, obj_name, "RELATED_TO",
                                          token.sent.text.strip())

            # Prepositional patterns: "X <prep> Y"
            if token.dep_ == "prep" and token.text.lower() in PREP_RELATION_MAP:
                head_name = _resolve_entity_name(token.head, doc)
                for child in token.children:
                    if child.dep_ in ("pobj", "pcomp"):
                        child_name = _resolve_entity_name(child, doc)
                        if head_name in entity_type_map and child_name in entity_type_map:
                            rel_type = PREP_RELATION_MAP[token.text.lower()]
                            _add_relation(head_name, child_name, rel_type,
                                          token.sent.text.strip())

        return ExtractionResult(
            entities=entities,
            relations=relations,
            source_document=document_id,
            processing_metadata={
                "method": self.EXTRACTION_METHOD,
                "spacy_model": self.SPACY_MODEL,
                "entity_count": len(entities),
                "relation_count": len(relations),
            },
        )


def _resolve_entity_name(token, doc) -> str:
    """Return the text of the entity span containing *token*, or token text."""
    for ent in doc.ents:
        if ent.start <= token.i < ent.end:
            return ent.text.strip()
    return token.text.strip()
