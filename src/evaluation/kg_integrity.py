"""Knowledge Graph Integrity Evaluation Module.

Checks the Neo4j graph for structural and schema quality issues:
- Orphan nodes (no relationships)
- Duplicate relations (same source/target/type)
- Schema conformance (required properties missing)
- Invalid predicates (relation types outside schema)
- Provenance completeness (edges missing _source_text)
- Entity fragmentation (near-duplicate node names)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
import json
from datetime import datetime

from src.kg.client import Neo4jClient
from src.kg.schema import ENTITY_SCHEMAS, RELATION_SCHEMAS


@dataclass
class IntegrityReport:
    total_nodes: int = 0
    total_relations: int = 0

    orphan_nodes: int = 0
    orphan_ratio: float = 0.0
    orphan_details: List[Dict] = field(default_factory=list)

    duplicate_relations: int = 0
    duplicate_ratio: float = 0.0
    duplicate_details: List[Dict] = field(default_factory=list)

    schema_violations: List[Dict] = field(default_factory=list)
    schema_violation_count: int = 0

    invalid_predicates: List[str] = field(default_factory=list)
    invalid_predicate_count: int = 0
    invalid_predicate_ratio: float = 0.0

    missing_provenance_count: int = 0
    missing_provenance_ratio: float = 0.0
    missing_provenance_by_type: Dict[str, int] = field(default_factory=dict)

    fragmented_entities: List[Dict] = field(default_factory=list)
    fragmented_entity_count: int = 0

    node_label_distribution: Dict[str, int] = field(default_factory=dict)
    relation_type_distribution: Dict[str, int] = field(default_factory=dict)

    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "summary": {
                "total_nodes": self.total_nodes,
                "total_relations": self.total_relations,
                "orphan_nodes": self.orphan_nodes,
                "orphan_ratio": round(self.orphan_ratio, 4),
                "duplicate_relations": self.duplicate_relations,
                "duplicate_ratio": round(self.duplicate_ratio, 4),
                "schema_violations": self.schema_violation_count,
                "invalid_predicates": self.invalid_predicate_count,
                "invalid_predicate_ratio": round(self.invalid_predicate_ratio, 4),
                "missing_provenance": self.missing_provenance_count,
                "missing_provenance_ratio": round(self.missing_provenance_ratio, 4),
                "fragmented_entities": self.fragmented_entity_count,
            },
            "node_label_distribution": self.node_label_distribution,
            "relation_type_distribution": self.relation_type_distribution,
            "orphan_details": self.orphan_details,
            "duplicate_details": self.duplicate_details,
            "schema_violations": self.schema_violations,
            "invalid_predicates": self.invalid_predicates,
            "missing_provenance_by_type": self.missing_provenance_by_type,
            "fragmented_entities": self.fragmented_entities,
        }

    def print_report(self) -> None:
        print("\n" + "=" * 60)
        print("KNOWLEDGE GRAPH INTEGRITY REPORT")
        print(f"Generated: {self.timestamp}")
        print("=" * 60)

        print(f"\n{'Totals':}")
        print(f"  Nodes:     {self.total_nodes}")
        print(f"  Relations: {self.total_relations}")

        print(f"\nNode Label Distribution:")
        for label, count in sorted(self.node_label_distribution.items(), key=lambda x: -x[1]):
            print(f"  {label:<20} {count}")

        print(f"\nRelation Type Distribution:")
        for rel_type, count in sorted(self.relation_type_distribution.items(), key=lambda x: -x[1]):
            print(f"  {rel_type:<30} {count}")

        print(f"\n{'Orphan Nodes':<30} {self.orphan_nodes} / {self.total_nodes}  ({self.orphan_ratio:.1%})")
        if self.orphan_details:
            for d in self.orphan_details[:5]:
                print(f"    - [{d.get('label', '?')}] {d.get('name', d.get('value', '?'))}")
            if len(self.orphan_details) > 5:
                print(f"    ... and {len(self.orphan_details) - 5} more")

        print(f"\n{'Duplicate Relations':<30} {self.duplicate_relations}  ({self.duplicate_ratio:.1%})")
        if self.duplicate_details:
            for d in self.duplicate_details[:5]:
                print(f"    - {d['source']} --[{d['type']}]--> {d['target']}  (x{d['count']})")
            if len(self.duplicate_details) > 5:
                print(f"    ... and {len(self.duplicate_details) - 5} more")

        print(f"\n{'Schema Violations':<30} {self.schema_violation_count}")
        if self.schema_violations:
            for v in self.schema_violations[:5]:
                print(f"    - [{v['label']}] {v['name']}: missing {v['missing_properties']}")
            if len(self.schema_violations) > 5:
                print(f"    ... and {len(self.schema_violations) - 5} more")

        print(f"\n{'Invalid Predicates':<30} {self.invalid_predicate_count}  ({self.invalid_predicate_ratio:.1%})")
        if self.invalid_predicates:
            for p in self.invalid_predicates:
                print(f"    - {p}")

        print(f"\n{'Missing Provenance':<30} {self.missing_provenance_count} / {self.total_relations}  ({self.missing_provenance_ratio:.1%})")
        if self.missing_provenance_by_type:
            for rel_type, count in sorted(self.missing_provenance_by_type.items(), key=lambda x: -x[1])[:5]:
                print(f"    - {rel_type}: {count}")

        print(f"\n{'Fragmented Entities':<30} {self.fragmented_entity_count} groups")
        if self.fragmented_entities:
            for f in self.fragmented_entities[:5]:
                print(f"    - [{f['label']}] '{f['normalized']}': {f['variants']}")
            if len(self.fragmented_entities) > 5:
                print(f"    ... and {len(self.fragmented_entities) - 5} more groups")

        print("\n" + "=" * 60)


def check_orphan_nodes(client: Neo4jClient) -> tuple:
    """Find nodes with no relationships."""
    count_result = client.run_query_single(
        "MATCH (n) WHERE NOT (n)--() RETURN count(n) AS cnt"
    )
    count = count_result["cnt"] if count_result else 0

    details_result = client.run_query(
        "MATCH (n) WHERE NOT (n)--() "
        "RETURN labels(n)[0] AS label, "
        "COALESCE(n.name, n.doc_id, n.value, toString(id(n))) AS name "
        "LIMIT 50"
    )
    details = [{"label": r["label"], "name": r["name"]} for r in details_result]
    return count, details


def check_duplicate_relations(client: Neo4jClient) -> tuple:
    """Find (source, target, type) triples that appear more than once."""
    result = client.run_query(
        "MATCH (a)-[r]->(b) "
        "WITH COALESCE(a.name, a.doc_id, a.value, toString(id(a))) AS src, "
        "     COALESCE(b.name, b.doc_id, b.value, toString(id(b))) AS tgt, "
        "     type(r) AS rel_type, count(r) AS cnt "
        "WHERE cnt > 1 "
        "RETURN src, tgt, rel_type, cnt "
        "ORDER BY cnt DESC "
        "LIMIT 50"
    )
    count = len(result)
    details = [{"source": r["src"], "target": r["tgt"], "type": r["rel_type"], "count": r["cnt"]} for r in result]
    return count, details


def check_schema_conformance(client: Neo4jClient) -> List[Dict]:
    """Check that nodes have all required properties for their label."""
    violations = []
    for label, schema in ENTITY_SCHEMAS.items():
        for prop in schema.required_properties:
            result = client.run_query(
                f"MATCH (n:{label}) WHERE n.{prop} IS NULL "
                f"RETURN COALESCE(n.name, n.doc_id, n.value, toString(id(n))) AS name "
                f"LIMIT 20"
            )
            for row in result:
                violations.append({
                    "label": label,
                    "name": row["name"],
                    "missing_properties": [prop],
                })
    return violations


def check_invalid_predicates(client: Neo4jClient) -> tuple:
    """Find relation types that are not in the schema."""
    result = client.run_query(
        "MATCH ()-[r]->() RETURN DISTINCT type(r) AS rel_type"
    )
    all_types = [r["rel_type"] for r in result]
    valid_types = set(RELATION_SCHEMAS.keys())
    invalid = [t for t in all_types if t not in valid_types]

    total_distinct = len(all_types)
    ratio = len(invalid) / total_distinct if total_distinct > 0 else 0.0
    return invalid, ratio


def check_provenance(client: Neo4jClient) -> tuple:
    """Find edges missing _source_text (provenance)."""
    total_result = client.run_query_single(
        "MATCH ()-[r]->() RETURN count(r) AS cnt"
    )
    total = total_result["cnt"] if total_result else 0

    missing_result = client.run_query_single(
        "MATCH ()-[r]->() WHERE r._source_text IS NULL RETURN count(r) AS cnt"
    )
    missing = missing_result["cnt"] if missing_result else 0

    by_type_result = client.run_query(
        "MATCH ()-[r]->() WHERE r._source_text IS NULL "
        "RETURN type(r) AS rel_type, count(r) AS cnt "
        "ORDER BY cnt DESC"
    )
    by_type = {r["rel_type"]: r["cnt"] for r in by_type_result}

    ratio = missing / total if total > 0 else 0.0
    return missing, ratio, by_type


def check_entity_fragmentation(client: Neo4jClient) -> List[Dict]:
    """Find near-duplicate entity names (same normalized name, multiple nodes)."""
    fragmented = []
    for label in ENTITY_SCHEMAS:
        name_prop = "doc_id" if label == "Document" else ("value" if label == "Reference" else "name")
        result = client.run_query(
            f"MATCH (n:{label}) "
            f"WITH toLower(trim(n.{name_prop})) AS norm, collect(n.{name_prop}) AS variants "
            f"WHERE size(variants) > 1 AND norm IS NOT NULL AND norm <> '' "
            f"RETURN norm, variants "
            f"LIMIT 20"
        )
        for row in result:
            fragmented.append({
                "label": label,
                "normalized": row["norm"],
                "variants": row["variants"],
            })
    return fragmented


def run_integrity_check(client: Neo4jClient) -> IntegrityReport:
    """Run all integrity checks and return a consolidated IntegrityReport."""
    report = IntegrityReport()

    # Node and relation counts + distributions
    node_count_result = client.run_query_single("MATCH (n) RETURN count(n) AS cnt")
    report.total_nodes = node_count_result["cnt"] if node_count_result else 0

    rel_count_result = client.run_query_single("MATCH ()-[r]->() RETURN count(r) AS cnt")
    report.total_relations = rel_count_result["cnt"] if rel_count_result else 0

    label_dist = client.run_query(
        "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS cnt ORDER BY cnt DESC"
    )
    report.node_label_distribution = {r["label"]: r["cnt"] for r in label_dist if r["label"]}

    rel_dist = client.run_query(
        "MATCH ()-[r]->() RETURN type(r) AS rel_type, count(r) AS cnt ORDER BY cnt DESC"
    )
    report.relation_type_distribution = {r["rel_type"]: r["cnt"] for r in rel_dist}

    # Orphan nodes
    report.orphan_nodes, report.orphan_details = check_orphan_nodes(client)
    report.orphan_ratio = report.orphan_nodes / report.total_nodes if report.total_nodes > 0 else 0.0

    # Duplicate relations
    report.duplicate_relations, report.duplicate_details = check_duplicate_relations(client)
    report.duplicate_ratio = report.duplicate_relations / report.total_relations if report.total_relations > 0 else 0.0

    # Schema conformance
    report.schema_violations = check_schema_conformance(client)
    report.schema_violation_count = len(report.schema_violations)

    # Invalid predicates
    report.invalid_predicates, report.invalid_predicate_ratio = check_invalid_predicates(client)
    report.invalid_predicate_count = len(report.invalid_predicates)

    # Provenance completeness
    report.missing_provenance_count, report.missing_provenance_ratio, report.missing_provenance_by_type = check_provenance(client)

    # Entity fragmentation
    report.fragmented_entities = check_entity_fragmentation(client)
    report.fragmented_entity_count = len(report.fragmented_entities)

    return report
