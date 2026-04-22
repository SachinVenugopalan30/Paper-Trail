"""Entity Canonicalization — post-import deduplication script.

Merges duplicate Neo4j nodes using string normalization + fuzzy matching
(Levenshtein ratio via rapidfuzz). Run after build_knowledge_graph.py.

Usage:
    python3 scripts/canonicalize_entities.py --dry-run
    python3 scripts/canonicalize_entities.py --threshold 0.85
    python3 scripts/canonicalize_entities.py --label Person --threshold 0.9
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.kg.client import Neo4jClient, Neo4jConfig

try:
    from rapidfuzz import fuzz
except ImportError:
    print("ERROR: rapidfuzz is required. Run: pip install rapidfuzz")
    sys.exit(1)


# Entity labels that have a 'name' property (excludes Document, Reference which use doc_id/value)
CANONICALIZABLE_LABELS = ["Person", "Organization", "Technology", "Topic", "Location"]


def normalize_name(name: str) -> str:
    """Lowercase, strip whitespace, remove punctuation, collapse spaces."""
    name = name.lower().strip()
    name = re.sub(r"[^\w\s]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def fetch_nodes(client: Neo4jClient, label: str) -> List[Dict]:
    """Return all nodes of *label* with their internal IDs and names."""
    rows = client.run_query(
        f"MATCH (n:{label}) RETURN id(n) AS node_id, n.name AS name"
    )
    return [r for r in rows if r.get("name")]


def get_relationship_count(client: Neo4jClient, node_id: int) -> int:
    """Return total number of relationships on a node."""
    rows = client.run_query(
        "MATCH (n)-[r]-() WHERE id(n) = $node_id RETURN count(r) AS cnt",
        {"node_id": node_id},
    )
    return rows[0]["cnt"] if rows else 0


def repoint_outgoing(client: Neo4jClient, dup_id: int, canon_id: int) -> int:
    """Move all outgoing relationships from dup to canon. Returns count moved."""
    rows = client.run_query(
        "MATCH (dup)-[r]->(target) WHERE id(dup) = $dup_id "
        "RETURN id(r) AS rel_id, type(r) AS rel_type, id(target) AS target_id, properties(r) AS props",
        {"dup_id": dup_id},
    )
    moved = 0
    for row in rows:
        rel_type = row["rel_type"]
        target_id = row["target_id"]
        props = row.get("props") or {}
        if target_id == canon_id:
            continue  # skip self-loops that would arise
        # rel_type comes from Neo4j type() — safe to interpolate
        client.run_query(
            f"MATCH (canon) WHERE id(canon) = $canon_id "
            f"MATCH (target) WHERE id(target) = $target_id "
            f"MERGE (canon)-[r2:{rel_type}]->(target) SET r2 += $props",
            {"canon_id": canon_id, "target_id": target_id, "props": props},
        )
        moved += 1
    return moved


def repoint_incoming(client: Neo4jClient, dup_id: int, canon_id: int) -> int:
    """Move all incoming relationships from dup to canon. Returns count moved."""
    rows = client.run_query(
        "MATCH (source)-[r]->(dup) WHERE id(dup) = $dup_id "
        "RETURN id(r) AS rel_id, type(r) AS rel_type, id(source) AS source_id, properties(r) AS props",
        {"dup_id": dup_id},
    )
    moved = 0
    for row in rows:
        rel_type = row["rel_type"]
        source_id = row["source_id"]
        props = row.get("props") or {}
        if source_id == canon_id:
            continue
        client.run_query(
            f"MATCH (source) WHERE id(source) = $source_id "
            f"MATCH (canon) WHERE id(canon) = $canon_id "
            f"MERGE (source)-[r2:{rel_type}]->(canon) SET r2 += $props",
            {"source_id": source_id, "canon_id": canon_id, "props": props},
        )
        moved += 1
    return moved


def merge_nodes(
    client: Neo4jClient,
    canon_id: int,
    dup_id: int,
    dup_name: str,
    dry_run: bool,
) -> None:
    """Merge dup into canon: repoint all rels, store alias, delete dup."""
    if dry_run:
        return
    repoint_outgoing(client, dup_id, canon_id)
    repoint_incoming(client, dup_id, canon_id)
    # Store dup name as alias on canonical node
    client.run_query(
        "MATCH (n) WHERE id(n) = $canon_id "
        "SET n._aliases = CASE WHEN n._aliases IS NULL "
        "THEN [$alias] ELSE n._aliases + $alias END",
        {"canon_id": canon_id, "alias": dup_name},
    )
    # Delete the duplicate (all its rels are already repointed)
    client.run_query(
        "MATCH (n) WHERE id(n) = $dup_id DETACH DELETE n",
        {"dup_id": dup_id},
    )


def build_merge_groups(
    nodes: List[Dict], threshold: float
) -> List[List[Dict]]:
    """Return groups of nodes that should be merged together.

    First pass: exact match on normalized name.
    Second pass: fuzzy match among remaining nodes.
    """
    # Group by normalized name (exact)
    exact: Dict[str, List[Dict]] = {}
    for node in nodes:
        key = normalize_name(node["name"])
        exact.setdefault(key, []).append(node)

    groups: List[List[Dict]] = []
    singletons: List[Dict] = []

    for members in exact.values():
        if len(members) > 1:
            groups.append(members)
        else:
            singletons.append(members[0])

    # Fuzzy match among singletons
    merged_flags = [False] * len(singletons)
    for i in range(len(singletons)):
        if merged_flags[i]:
            continue
        group = [singletons[i]]
        norm_i = normalize_name(singletons[i]["name"])
        for j in range(i + 1, len(singletons)):
            if merged_flags[j]:
                continue
            norm_j = normalize_name(singletons[j]["name"])
            if fuzz.ratio(norm_i, norm_j) / 100.0 >= threshold:
                group.append(singletons[j])
                merged_flags[j] = True
        if len(group) > 1:
            groups.append(group)

    return groups


def canonicalize_label(
    client: Neo4jClient,
    label: str,
    threshold: float,
    dry_run: bool,
) -> Tuple[int, int]:
    """Process one entity label. Returns (nodes_before, nodes_merged)."""
    nodes = fetch_nodes(client, label)
    before = len(nodes)
    if before == 0:
        return 0, 0

    groups = build_merge_groups(nodes, threshold)
    merged_total = 0

    for group in groups:
        # Pick canonical = node with most relationships
        scored = []
        for node in group:
            cnt = get_relationship_count(client, node["node_id"])
            scored.append((cnt, node))
        scored.sort(key=lambda x: -x[0])
        canon = scored[0][1]
        duplicates = [n for _, n in scored[1:]]

        canonical_display = canon["name"]
        dup_display = ", ".join(d["name"] for d in duplicates)
        print(f"  {'[DRY-RUN] ' if dry_run else ''}Merge into '{canonical_display}': {dup_display}")

        for dup in duplicates:
            merge_nodes(client, canon["node_id"], dup["node_id"], dup["name"], dry_run)
            merged_total += 1

    return before, merged_total


def run_canonicalization(
    threshold: float = 0.85,
    dry_run: bool = False,
    label: Optional[str] = None,
) -> None:
    """Entry point — usable both as a script and from src/cli.py."""
    labels = [label] if label else CANONICALIZABLE_LABELS
    config = Neo4jConfig.from_yaml()
    client = Neo4jClient(config)

    if not client.connect():
        print("ERROR: Could not connect to Neo4j. Is it running?")
        sys.exit(1)

    try:
        print(f"\nEntity Canonicalization (threshold={threshold}, dry_run={dry_run})")
        print("=" * 60)
        total_before = 0
        total_merged = 0

        for lbl in labels:
            print(f"\n[{lbl}]")
            before, merged = canonicalize_label(client, lbl, threshold, dry_run)
            after = before - merged
            total_before += before
            total_merged += merged
            print(f"  Before: {before}  Merged away: {merged}  After: {after}")

        print("\n" + "=" * 60)
        print(f"Total nodes before: {total_before}")
        print(f"Total merged away:  {total_merged}")
        print(f"Total nodes after:  {total_before - total_merged}")
        if dry_run:
            print("(dry-run — no changes written)")
        print("=" * 60)
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Canonicalize duplicate entity nodes in Neo4j using fuzzy name matching."
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.85,
        help="Levenshtein similarity threshold for fuzzy merge (default: 0.85)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would merge without writing to Neo4j",
    )
    parser.add_argument(
        "--label",
        choices=CANONICALIZABLE_LABELS,
        default=None,
        help="Restrict to one entity label (default: all)",
    )
    args = parser.parse_args()
    run_canonicalization(
        threshold=args.threshold,
        dry_run=args.dry_run,
        label=args.label,
    )


if __name__ == "__main__":
    main()
