"""Graph-based retriever: keyword entity matching + 1-hop Neo4j expansion."""

import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class GraphRetriever:
    """Retrieve graph context from Neo4j for a given query."""

    def __init__(self, kg_client, max_entities: int = 5, max_hops: int = 1):
        self.kg_client = kg_client
        self.max_entities = max_entities
        self.max_hops = max_hops  # currently only 1-hop is implemented

    def extract_query_entities(self, query: str) -> List[Dict[str, Any]]:
        """Find Neo4j entities whose names contain query keywords."""
        keywords = [w for w in query.split() if len(w) > 2]
        seen = set()
        entities = []

        for keyword in keywords:
            try:
                rows = self.kg_client.run_query(
                    "MATCH (n) WHERE toLower(n.name) CONTAINS toLower($keyword) "
                    "RETURN n.name AS name, labels(n)[0] AS label LIMIT 5",
                    {"keyword": keyword},
                )
                for row in rows:
                    name = row.get("name") or row.get("n.name")
                    label = row.get("label") or row.get("labels(n)[0]")
                    if name and name not in seen:
                        seen.add(name)
                        entities.append({"name": name, "label": label})
                        if len(entities) >= self.max_entities:
                            return entities
            except Exception as e:
                logger.debug(f"Entity lookup failed for keyword '{keyword}': {e}")

        return entities

    def _get_subgraph_context(self, entity_name: str, entity_label: str) -> str:
        """Return a human-readable string of 1-hop connections to Document nodes."""
        try:
            rows = self.kg_client.run_query(
                "MATCH (e {name: $name})-[r]-(d:Document) "
                "RETURN d.doc_id AS doc_id, type(r) AS rel_type, labels(e)[0] AS entity_label "
                "LIMIT 20",
                {"name": entity_name},
            )
            if not rows:
                return ""

            doc_rels = []
            for row in rows:
                doc_id = row.get("doc_id") or row.get("d.doc_id")
                rel_type = row.get("rel_type") or row.get("type(r)")
                if doc_id:
                    doc_rels.append(f"{doc_id} [{rel_type}]")

            if doc_rels:
                label_str = entity_label or "Entity"
                return f'Entity "{entity_name}" ({label_str}) → ' + ", ".join(doc_rels[:10])
        except Exception as e:
            logger.debug(f"Subgraph expansion failed for '{entity_name}': {e}")
        return ""

    def retrieve(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Return graph context results as {document_id, graph_context, score}."""
        entities = self.extract_query_entities(query)
        results = []
        doc_scores: Dict[str, float] = {}
        doc_context_lines: Dict[str, List[str]] = {}

        for rank, entity in enumerate(entities):
            context_str = self._get_subgraph_context(entity["name"], entity["label"])
            if not context_str:
                continue

            # Parse doc IDs out of context_str for scoring
            try:
                connections_part = context_str.split("→", 1)[1]
                for part in connections_part.split(","):
                    doc_id = part.strip().split(" [")[0].strip()
                    if doc_id:
                        score = 1.0 / (rank + 1)
                        doc_scores[doc_id] = doc_scores.get(doc_id, 0) + score
                        doc_context_lines.setdefault(doc_id, []).append(context_str)
            except Exception:
                pass

        # Build result list sorted by score
        for doc_id, score in sorted(doc_scores.items(), key=lambda x: -x[1])[:top_k]:
            results.append(
                {
                    "document_id": doc_id,
                    "graph_context": "\n".join(doc_context_lines.get(doc_id, [])),
                    "score": score,
                    "chunk_id": f"graph_{doc_id}",
                    "text": "\n".join(doc_context_lines.get(doc_id, [])),
                    "metadata": {"source": "graph", "document_id": doc_id},
                }
            )
        return results
