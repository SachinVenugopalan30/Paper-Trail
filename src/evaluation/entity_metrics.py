"""Entity and Relation F1 Metrics for Gold Set B Evaluation.

Computes precision, recall, F1, hallucination rate, and schema validity
from PageExtractionAnnotation objects produced by the annotation tool.
"""

from typing import List, Dict, Any, TYPE_CHECKING

from src.kg.schema import ENTITY_SCHEMAS, RELATION_SCHEMAS

if TYPE_CHECKING:
    from src.evaluation.entity_annotation_tool import (
        EntityAnnotation,
        RelationAnnotation,
        PageExtractionAnnotation,
    )


# ── Core metric helpers ────────────────────────────────────────────────────────

def _safe_f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def entity_precision(annotations: List["EntityAnnotation"]) -> float:
    """Fraction of extracted entities judged correct (or partial)."""
    if not annotations:
        return 0.0
    correct = sum(1 for a in annotations if a.judgment in ("correct", "partial"))
    return correct / len(annotations)


def entity_recall(annotations: List["EntityAnnotation"], missing_count: int) -> float:
    """Fraction of true entities that were extracted.

    correct / (correct + missing), where missing_count is the number of
    entities the annotator added manually (present in text but not extracted).
    """
    correct = sum(1 for a in annotations if a.judgment in ("correct", "partial"))
    denominator = correct + missing_count
    return correct / denominator if denominator > 0 else 0.0


def entity_f1(annotations: List["EntityAnnotation"], missing_count: int) -> float:
    p = entity_precision(annotations)
    r = entity_recall(annotations, missing_count)
    return _safe_f1(p, r)


def relation_precision(annotations: List["RelationAnnotation"]) -> float:
    if not annotations:
        return 0.0
    correct = sum(1 for a in annotations if a.judgment in ("correct", "partial"))
    return correct / len(annotations)


def relation_recall(annotations: List["RelationAnnotation"], missing_count: int) -> float:
    correct = sum(1 for a in annotations if a.judgment in ("correct", "partial"))
    denominator = correct + missing_count
    return correct / denominator if denominator > 0 else 0.0


def relation_f1(annotations: List["RelationAnnotation"], missing_count: int) -> float:
    p = relation_precision(annotations)
    r = relation_recall(annotations, missing_count)
    return _safe_f1(p, r)


def hallucination_rate(annotations: list) -> float:
    """Fraction of extracted items (entities or relations) marked as hallucinated."""
    if not annotations:
        return 0.0
    hallucinated = sum(1 for a in annotations if getattr(a, "is_hallucinated", False))
    return hallucinated / len(annotations)


def schema_validity_rate(extractions: List[Dict[str, Any]]) -> float:
    """Fraction of extracted entities/relations with valid types per the KG schema.

    Args:
        extractions: list of dicts with 'type' key (entity or relation dicts
                     as produced by EntityExtractionChain).
    """
    if not extractions:
        return 1.0
    valid_entity_types = set(ENTITY_SCHEMAS.keys())
    valid_relation_types = set(RELATION_SCHEMAS.keys())
    valid_count = 0
    for item in extractions:
        t = item.get("type", "")
        if t in valid_entity_types or t in valid_relation_types:
            valid_count += 1
    return valid_count / len(extractions)


# ── Aggregate reporting ────────────────────────────────────────────────────────

def compute_gold_set_b_report(all_annotations: List["PageExtractionAnnotation"]) -> Dict[str, Any]:
    """Aggregate P/R/F1, hallucination rate, and schema validity across all annotated pages."""
    if not all_annotations:
        return {}

    entity_p_vals, entity_r_vals, entity_f1_vals = [], [], []
    relation_p_vals, relation_r_vals, relation_f1_vals = [], [], []
    entity_halluc_vals, relation_halluc_vals = [], []
    schema_vals = []

    for ann in all_annotations:
        missing_ents = len(ann.missing_entities)
        missing_rels = len(ann.missing_relations)

        ep = entity_precision(ann.entity_annotations)
        er = entity_recall(ann.entity_annotations, missing_ents)
        ef1 = _safe_f1(ep, er)
        entity_p_vals.append(ep)
        entity_r_vals.append(er)
        entity_f1_vals.append(ef1)

        rp = relation_precision(ann.relation_annotations)
        rr = relation_recall(ann.relation_annotations, missing_rels)
        rf1 = _safe_f1(rp, rr)
        relation_p_vals.append(rp)
        relation_r_vals.append(rr)
        relation_f1_vals.append(rf1)

        entity_halluc_vals.append(hallucination_rate(ann.entity_annotations))
        relation_halluc_vals.append(hallucination_rate(ann.relation_annotations))

        all_extracted = (
            [{"type": e.entity_type} for e in ann.entity_annotations] +
            [{"type": r.relation_type} for r in ann.relation_annotations]
        )
        schema_vals.append(schema_validity_rate(all_extracted))

    def _mean(vals):
        return round(sum(vals) / len(vals), 4) if vals else 0.0

    return {
        "total_pages_annotated": len(all_annotations),
        "entity": {
            "mean_precision": _mean(entity_p_vals),
            "mean_recall": _mean(entity_r_vals),
            "mean_f1": _mean(entity_f1_vals),
            "mean_hallucination_rate": _mean(entity_halluc_vals),
        },
        "relation": {
            "mean_precision": _mean(relation_p_vals),
            "mean_recall": _mean(relation_r_vals),
            "mean_f1": _mean(relation_f1_vals),
            "mean_hallucination_rate": _mean(relation_halluc_vals),
        },
        "mean_schema_validity_rate": _mean(schema_vals),
    }
