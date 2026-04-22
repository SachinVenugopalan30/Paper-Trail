"""Graph-based retriever: keyword entity matching + multi-hop Neo4j expansion."""

import logging
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)


class GraphRetriever:
    """Retrieve graph context from Neo4j for a given query."""

    def __init__(self, kg_client, max_entities: int = 5, max_hops: int = 2):
        self.kg_client = kg_client
        self.max_entities = max_entities
        self.max_hops = max_hops

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

    def _get_subgraph_context(
        self, entity_name: str, entity_label: str
    ) -> Tuple[str, List[Tuple[str, int]]]:
        """Return (context_string, [(doc_id, hops), ...]) for up to max_hops away.

        Uses variable-length path matching so 2-hop results surface documents
        connected through an intermediate entity node.
        """
        try:
            rows = self.kg_client.run_query(
                "MATCH path = (e {name: $name})-[*1..$max_hops]-(d:Document) "
                "WITH d.doc_id AS doc_id, "
                "     length(path) AS hops, "
                "     [r IN relationships(path) | type(r)] AS rel_types, "
                "     [n IN nodes(path) | COALESCE(n.name, n.doc_id, '')] AS node_names "
                "RETURN DISTINCT doc_id, hops, rel_types, node_names "
                "ORDER BY hops ASC "
                "LIMIT 30",
                {"name": entity_name, "max_hops": self.max_hops},
            )
            if not rows:
                return "", []

            doc_entries: List[Tuple[str, int]] = []   # (doc_id, hops)
            context_parts: List[str] = []

            for row in rows:
                doc_id = row.get("doc_id")
                hops = row.get("hops", 1)
                rel_types = row.get("rel_types") or []
                if not doc_id:
                    continue
                rel_str = ">".join(rel_types) if rel_types else "REL"
                hop_label = f"{hops}-hop"
                context_parts.append(f"{doc_id} [{rel_str}|{hop_label}]")
                doc_entries.append((doc_id, hops))

            if context_parts:
                label_str = entity_label or "Entity"
                context_str = (
                    f'Entity "{entity_name}" ({label_str}) \u2192 '
                    + ", ".join(context_parts[:15])
                )
                return context_str, doc_entries

        except Exception as e:
            logger.debug(f"Subgraph expansion failed for '{entity_name}': {e}")
        return "", []

    def retrieve(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Return graph context results as {document_id, graph_context, score}.

        Scoring uses a hop-penalty decay: score = (1 / (rank + 1)) * (1 / hops).
        1-hop results receive full weight; 2-hop results receive half weight.
        """
        entities = self.extract_query_entities(query)
        results = []
        doc_scores: Dict[str, float] = {}
        doc_context_lines: Dict[str, List[str]] = {}

        for rank, entity in enumerate(entities):
            context_str, doc_entries = self._get_subgraph_context(
                entity["name"], entity["label"]
            )
            if not context_str:
                continue

            for doc_id, hops in doc_entries:
                hop_penalty = 1.0 / max(hops, 1)
                score = (1.0 / (rank + 1)) * hop_penalty
                doc_scores[doc_id] = doc_scores.get(doc_id, 0) + score
                doc_context_lines.setdefault(doc_id, []).append(context_str)

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
