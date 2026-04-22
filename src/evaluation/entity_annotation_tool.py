"""Gold Set B Entity/Relation Annotation Tool.

Streamlit UI for annotating LLM-extracted entities and relations per page,
computing Entity F1, Relation F1, hallucination rate, and schema validity.

Usage:
    streamlit run src/evaluation/entity_annotation_tool.py
    # or via CLI:
    python3 -m src.cli eval entity-tool

Data flow:
    scripts/build_knowledge_graph.py  →  data/evaluation/extractions/*.json
    (annotate here)                   →  data/evaluation/gold_set_b_annotations.json
    python3 -m src.cli eval entity-report  →  aggregate F1 report
"""

import json
import sys
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Proposal annotation categories (Section 3.4) — used as the "expected type" dropdown
PROPOSAL_ENTITY_TYPES = [
    "Person", "Organization", "Location", "Date",
    "Concept", "Clause", "Metric", "Other",
]
PROPOSAL_RELATION_TYPES = [
    "mentions", "authored_by", "located_in", "defined_as", "related_to", "other",
]

STORAGE_PATH = Path(__file__).parent.parent.parent / "data" / "evaluation" / "gold_set_b_annotations.json"
EXTRACTIONS_DIR = Path(__file__).parent.parent.parent / "data" / "evaluation" / "extractions"


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class EntityAnnotation:
    entity_name: str
    entity_type: str          # LLM-extracted type (Document, Person, Technology, …)
    expected_type: str        # Annotator-assigned type from proposal categories
    source_text: str
    confidence: float
    judgment: str = ""        # "correct" | "incorrect" | "partial"
    is_hallucinated: bool = False
    notes: str = ""


@dataclass
class RelationAnnotation:
    source: str
    target: str
    relation_type: str        # LLM-extracted relation type
    expected_relation_type: str  # Annotator-assigned type from proposal categories
    source_text: str
    confidence: float
    judgment: str = ""        # "correct" | "incorrect" | "partial"
    is_hallucinated: bool = False
    notes: str = ""


@dataclass
class MissingEntity:
    name: str
    entity_type: str


@dataclass
class MissingRelation:
    source: str
    target: str
    relation_type: str


@dataclass
class PageExtractionAnnotation:
    document_id: str
    page_number: int
    source_file: str
    entity_annotations: List[EntityAnnotation] = field(default_factory=list)
    relation_annotations: List[RelationAnnotation] = field(default_factory=list)
    missing_entities: List[MissingEntity] = field(default_factory=list)
    missing_relations: List[MissingRelation] = field(default_factory=list)
    annotator_notes: str = ""
    timestamp: str = ""
    entity_precision: Optional[float] = None
    entity_recall: Optional[float] = None
    entity_f1: Optional[float] = None
    relation_precision: Optional[float] = None
    relation_recall: Optional[float] = None
    relation_f1: Optional[float] = None
    hallucination_rate: Optional[float] = None
    schema_validity_rate: Optional[float] = None

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


# ── Storage ────────────────────────────────────────────────────────────────────

class EntityAnnotationStore:
    def __init__(self, storage_path: Path = STORAGE_PATH):
        self.storage_path = storage_path
        self.annotations: Dict[str, PageExtractionAnnotation] = {}
        self._load()

    def _key(self, document_id: str, page_number: int) -> str:
        return f"{document_id}::{page_number}"

    def _load(self):
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for key, d in data.items():
                    d["entity_annotations"] = [EntityAnnotation(**e) for e in d.get("entity_annotations", [])]
                    d["relation_annotations"] = [RelationAnnotation(**r) for r in d.get("relation_annotations", [])]
                    d["missing_entities"] = [MissingEntity(**m) for m in d.get("missing_entities", [])]
                    d["missing_relations"] = [MissingRelation(**m) for m in d.get("missing_relations", [])]
                    self.annotations[key] = PageExtractionAnnotation(**d)
            except Exception as e:
                print(f"Could not load annotations: {e}")

    def save_annotation(self, ann: PageExtractionAnnotation) -> None:
        from src.evaluation.entity_metrics import (
            entity_precision, entity_recall, entity_f1,
            relation_precision, relation_recall, relation_f1,
            hallucination_rate, schema_validity_rate,
        )
        me = len(ann.missing_entities)
        mr = len(ann.missing_relations)

        ep = entity_precision(ann.entity_annotations)
        er = entity_recall(ann.entity_annotations, me)
        ann.entity_precision = round(ep, 4)
        ann.entity_recall = round(er, 4)
        ann.entity_f1 = round(entity_f1(ann.entity_annotations, me), 4)

        rp = relation_precision(ann.relation_annotations)
        rr = relation_recall(ann.relation_annotations, mr)
        ann.relation_precision = round(rp, 4)
        ann.relation_recall = round(rr, 4)
        ann.relation_f1 = round(relation_f1(ann.relation_annotations, mr), 4)

        all_anns = ann.entity_annotations + ann.relation_annotations  # type: ignore
        ann.hallucination_rate = round(hallucination_rate(all_anns), 4)

        all_extracted = (
            [{"type": e.entity_type} for e in ann.entity_annotations] +
            [{"type": r.relation_type} for r in ann.relation_annotations]
        )
        ann.schema_validity_rate = round(schema_validity_rate(all_extracted), 4)

        key = self._key(ann.document_id, ann.page_number)
        self.annotations[key] = ann
        self._save()

    def _save(self):
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = {k: asdict(v) for k, v in self.annotations.items()}
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get(self, document_id: str, page_number: int) -> Optional[PageExtractionAnnotation]:
        return self.annotations.get(self._key(document_id, page_number))

    def get_all(self) -> List[PageExtractionAnnotation]:
        return list(self.annotations.values())

    def aggregate_stats(self) -> Dict[str, Any]:
        anns = self.get_all()
        if not anns:
            return {}
        annotated = [a for a in anns if a.entity_f1 is not None]
        if not annotated:
            return {"total": len(anns), "annotated": 0}

        def _mean(vals):
            return round(sum(vals) / len(vals), 4) if vals else 0.0

        return {
            "total": len(anns),
            "annotated": len(annotated),
            "mean_entity_f1": _mean([a.entity_f1 for a in annotated]),
            "mean_entity_precision": _mean([a.entity_precision for a in annotated if a.entity_precision is not None]),
            "mean_entity_recall": _mean([a.entity_recall for a in annotated if a.entity_recall is not None]),
            "mean_relation_f1": _mean([a.relation_f1 for a in annotated]),
            "mean_relation_precision": _mean([a.relation_precision for a in annotated if a.relation_precision is not None]),
            "mean_relation_recall": _mean([a.relation_recall for a in annotated if a.relation_recall is not None]),
            "mean_hallucination_rate": _mean([a.hallucination_rate for a in annotated if a.hallucination_rate is not None]),
            "mean_schema_validity": _mean([a.schema_validity_rate for a in annotated if a.schema_validity_rate is not None]),
        }


# ── Extraction loader ──────────────────────────────────────────────────────────

class ExtractionResultsLoader:
    def __init__(self, extractions_dir: Path = EXTRACTIONS_DIR):
        self.extractions_dir = extractions_dir

    def get_all_doc_stems(self) -> List[str]:
        if not self.extractions_dir.exists():
            return []
        return sorted(p.stem.replace("_extractions", "") for p in self.extractions_dir.glob("*_extractions.json"))

    def load(self, doc_stem: str) -> Optional[Dict]:
        path = self.extractions_dir / f"{doc_stem}_extractions.json"
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_source_text(self, doc_stem: str, page_index: int) -> str:
        """Load the original extracted text for a page from batch results."""
        data = self.load(doc_stem)
        if not data:
            return ""
        result_file = data.get("result_file", "")
        if not result_file:
            return ""
        result_path = Path(result_file)
        if not result_path.exists():
            return ""
        try:
            with open(result_path, "r", encoding="utf-8") as f:
                result = json.load(f)
            pages = result.get("pages", [])
            if page_index < len(pages):
                page = pages[page_index]
                native = page.get("native", {}).get("text", "")
                ocr = page.get("ocr", {}).get("text", "")
                return ocr if len(ocr) > len(native) else native
        except Exception:
            pass
        return ""


# ── Streamlit UI ───────────────────────────────────────────────────────────────

def run_streamlit_app():
    import streamlit as st

    st.set_page_config(page_title="Gold Set B — Entity/Relation Annotation", layout="wide")
    st.title("Gold Set B: Entity & Relation Annotation")

    loader = ExtractionResultsLoader()
    store = EntityAnnotationStore()

    doc_stems = loader.get_all_doc_stems()
    if not doc_stems:
        st.warning(
            "No extraction files found in `data/evaluation/extractions/`. "
            "Run `python3 scripts/build_knowledge_graph.py --all` to generate them."
        )
        return

    # ── Sidebar ────────────────────────────────────────────────────────────────
    with st.sidebar:
        st.header("Document Selection")

        selected_doc = st.selectbox("Document", doc_stems, key="selected_doc")
        doc_data = loader.load(selected_doc)

        if not doc_data:
            st.error("Could not load extraction data.")
            return

        extractions = doc_data.get("extractions", [])
        page_labels = [e["source_document"] for e in extractions]
        if not page_labels:
            st.warning("No pages in this document.")
            return

        selected_page_label = st.selectbox("Page", page_labels, key="selected_page")
        page_index = page_labels.index(selected_page_label)
        page_data = extractions[page_index]
        document_id = page_data["source_document"]

        # Nav buttons
        col1, col2 = st.columns(2)
        if col1.button("◀ Prev") and page_index > 0:
            st.session_state["selected_page"] = page_labels[page_index - 1]
            st.rerun()
        if col2.button("Next ▶") and page_index < len(page_labels) - 1:
            st.session_state["selected_page"] = page_labels[page_index + 1]
            st.rerun()

        st.divider()
        st.header("Aggregate Stats")
        stats = store.aggregate_stats()
        if stats:
            st.metric("Annotated Pages", f"{stats.get('annotated', 0)} / {stats.get('total', 0)}")
            st.metric("Mean Entity F1", f"{stats.get('mean_entity_f1', 0):.3f}")
            st.metric("Mean Relation F1", f"{stats.get('mean_relation_f1', 0):.3f}")
            st.metric("Hallucination Rate", f"{stats.get('mean_hallucination_rate', 0):.3f}")
            st.metric("Schema Validity", f"{stats.get('mean_schema_validity', 0):.3f}")
        else:
            st.info("No annotations yet.")

    # ── Main area ──────────────────────────────────────────────────────────────
    entities = page_data.get("entities", [])
    relations = page_data.get("relations", [])
    source_text = loader.get_source_text(selected_doc, page_index)

    # Load any existing annotation for this page
    existing = store.get(document_id, page_index + 1)

    st.subheader(f"Source Text — {document_id}")
    st.text_area("Extracted text (read-only)", value=source_text, height=150, disabled=True,
                 key=f"src_{document_id}_{page_index}")

    st.divider()

    # ── Entity annotation ──────────────────────────────────────────────────────
    st.subheader(f"Entities ({len(entities)})")

    entity_anns: List[EntityAnnotation] = []
    if entities:
        for i, ent in enumerate(entities):
            with st.expander(f"[{ent.get('type', '?')}] {ent.get('name', '?')}  (conf: {ent.get('confidence', 0):.2f})", expanded=False):
                cols = st.columns([2, 2, 1, 1])
                with cols[0]:
                    st.caption("Source snippet")
                    st.text(ent.get("source_text", "")[:200])
                with cols[1]:
                    prev_expected = ""
                    if existing and i < len(existing.entity_annotations):
                        prev_expected = existing.entity_annotations[i].expected_type
                    expected_type = st.selectbox(
                        "Expected type",
                        PROPOSAL_ENTITY_TYPES,
                        index=PROPOSAL_ENTITY_TYPES.index(prev_expected) if prev_expected in PROPOSAL_ENTITY_TYPES else 0,
                        key=f"ent_etype_{document_id}_{i}",
                    )
                with cols[2]:
                    prev_judgment = "correct"
                    if existing and i < len(existing.entity_annotations):
                        prev_judgment = existing.entity_annotations[i].judgment or "correct"
                    judgment = st.radio(
                        "Judgment",
                        ["correct", "partial", "incorrect"],
                        index=["correct", "partial", "incorrect"].index(prev_judgment),
                        key=f"ent_judg_{document_id}_{i}",
                    )
                with cols[3]:
                    prev_halluc = False
                    if existing and i < len(existing.entity_annotations):
                        prev_halluc = existing.entity_annotations[i].is_hallucinated
                    is_halluc = st.checkbox(
                        "Hallucinated?",
                        value=prev_halluc,
                        key=f"ent_halluc_{document_id}_{i}",
                    )
                entity_anns.append(EntityAnnotation(
                    entity_name=ent.get("name", ""),
                    entity_type=ent.get("type", ""),
                    expected_type=expected_type,
                    source_text=ent.get("source_text", ""),
                    confidence=ent.get("confidence", 0.0),
                    judgment=judgment,
                    is_hallucinated=is_halluc,
                ))
    else:
        st.info("No entities extracted for this page.")

    # ── Relation annotation ────────────────────────────────────────────────────
    st.subheader(f"Relations ({len(relations)})")

    relation_anns: List[RelationAnnotation] = []
    if relations:
        for i, rel in enumerate(relations):
            label = f"{rel.get('source','?')} --[{rel.get('type','?')}]--> {rel.get('target','?')}  (conf: {rel.get('confidence',0):.2f})"
            with st.expander(label, expanded=False):
                cols = st.columns([2, 2, 1, 1])
                with cols[0]:
                    st.caption("Source snippet")
                    st.text(rel.get("source_text", "")[:200])
                with cols[1]:
                    prev_expected = ""
                    if existing and i < len(existing.relation_annotations):
                        prev_expected = existing.relation_annotations[i].expected_relation_type
                    expected_rel_type = st.selectbox(
                        "Expected relation type",
                        PROPOSAL_RELATION_TYPES,
                        index=PROPOSAL_RELATION_TYPES.index(prev_expected) if prev_expected in PROPOSAL_RELATION_TYPES else 0,
                        key=f"rel_etype_{document_id}_{i}",
                    )
                with cols[2]:
                    prev_judgment = "correct"
                    if existing and i < len(existing.relation_annotations):
                        prev_judgment = existing.relation_annotations[i].judgment or "correct"
                    judgment = st.radio(
                        "Judgment",
                        ["correct", "partial", "incorrect"],
                        index=["correct", "partial", "incorrect"].index(prev_judgment),
                        key=f"rel_judg_{document_id}_{i}",
                    )
                with cols[3]:
                    prev_halluc = False
                    if existing and i < len(existing.relation_annotations):
                        prev_halluc = existing.relation_annotations[i].is_hallucinated
                    is_halluc = st.checkbox(
                        "Hallucinated?",
                        value=prev_halluc,
                        key=f"rel_halluc_{document_id}_{i}",
                    )
                relation_anns.append(RelationAnnotation(
                    source=rel.get("source", ""),
                    target=rel.get("target", ""),
                    relation_type=rel.get("type", ""),
                    expected_relation_type=expected_rel_type,
                    source_text=rel.get("source_text", ""),
                    confidence=rel.get("confidence", 0.0),
                    judgment=judgment,
                    is_hallucinated=is_halluc,
                ))
    else:
        st.info("No relations extracted for this page.")

    # ── Add missing items ──────────────────────────────────────────────────────
    with st.expander("Add Missing Entities / Relations (for recall)", expanded=False):
        st.caption("Add entities or relations that were present in the text but NOT extracted by the LLM.")
        missing_ents_raw = st.text_area(
            "Missing entities (one per line: name | type)",
            value="\n".join(f"{m.name} | {m.entity_type}" for m in (existing.missing_entities if existing else [])),
            key=f"missing_ents_{document_id}_{page_index}",
        )
        missing_rels_raw = st.text_area(
            "Missing relations (one per line: source | target | type)",
            value="\n".join(f"{m.source} | {m.target} | {m.relation_type}" for m in (existing.missing_relations if existing else [])),
            key=f"missing_rels_{document_id}_{page_index}",
        )

    # Parse missing items
    missing_entities: List[MissingEntity] = []
    for line in missing_ents_raw.strip().splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 2 and parts[0]:
            missing_entities.append(MissingEntity(name=parts[0], entity_type=parts[1]))

    missing_relations: List[MissingRelation] = []
    for line in missing_rels_raw.strip().splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 3 and parts[0]:
            missing_relations.append(MissingRelation(source=parts[0], target=parts[1], relation_type=parts[2]))

    # ── Notes + Save ──────────────────────────────────────────────────────────
    st.divider()
    notes = st.text_input(
        "Annotator notes (optional)",
        value=existing.annotator_notes if existing else "",
        key=f"notes_{document_id}_{page_index}",
    )

    if st.button("Save Annotation", type="primary"):
        ann = PageExtractionAnnotation(
            document_id=document_id,
            page_number=page_index + 1,
            source_file=str(EXTRACTIONS_DIR / f"{selected_doc}_extractions.json"),
            entity_annotations=entity_anns,
            relation_annotations=relation_anns,
            missing_entities=missing_entities,
            missing_relations=missing_relations,
            annotator_notes=notes,
        )
        store.save_annotation(ann)
        st.success(
            f"Saved! Entity F1: {ann.entity_f1:.3f} | "
            f"Relation F1: {ann.relation_f1:.3f} | "
            f"Hallucination: {ann.hallucination_rate:.3f} | "
            f"Schema validity: {ann.schema_validity_rate:.3f}"
        )
        st.rerun()

    # Show current saved metrics if available
    if existing and existing.entity_f1 is not None:
        st.info(
            f"Last saved — Entity F1: {existing.entity_f1:.3f} | "
            f"Relation F1: {existing.relation_f1:.3f} | "
            f"Hallucination: {existing.hallucination_rate:.3f} | "
            f"Schema validity: {existing.schema_validity_rate:.3f}"
        )


if __name__ == "__main__":
    run_streamlit_app()
