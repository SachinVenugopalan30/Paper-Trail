"""Neo4j Graph Database Client Module.

Provides connection management and operations for the Neo4j knowledge graph.
"""

import logging
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from pathlib import Path
import yaml
import os

try:
    from neo4j import GraphDatabase, Driver, Session, Transaction
    from neo4j.exceptions import ServiceUnavailable, AuthError, ClientError
except ImportError:
    GraphDatabase = None
    Driver = None
    Session = None
    Transaction = None
    ServiceUnavailable = Exception
    AuthError = Exception
    ClientError = Exception

from src.kg.schema import (
    get_cypher_merge_node,
    get_cypher_merge_relation,
    get_all_entity_types,
)

logger = logging.getLogger(__name__)


@dataclass
class Neo4jConfig:
    """Neo4j connection configuration."""
    
    uri: str = "bolt://localhost:7687"
    username: str = "neo4j"
    password: str = "password"
    database: str = "neo4j"
    max_connection_pool_size: int = 50
    connection_timeout: int = 30
    
    @classmethod
    def from_yaml(cls, config_path: Optional[str] = None) -> "Neo4jConfig":
        """Load configuration from YAML file."""
        if config_path is None:
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "config" / "neo4j.yaml"
        else:
            config_path = Path(config_path)
        
        if not config_path.exists():
            logger.warning(f"Neo4j config not found: {config_path}, using defaults")
            return cls()
        
        with open(config_path, 'r') as f:
            raw_config = yaml.safe_load(f)
        
        conn = raw_config.get("connection", {})
        
        # Handle password from environment variable
        password = conn.get("password", "password")
        if isinstance(password, str) and password.startswith("${"):
            # Extract env var name with optional default
            # Format: ${VAR} or ${VAR:-default}
            env_match = password[2:-1] if password.endswith("}") else password[2:]
            if ":-" in env_match:
                env_var, default = env_match.split(":-", 1)
                password = os.getenv(env_var, default)
            else:
                password = os.getenv(env_match, "password")
        
        return cls(
            uri=conn.get("uri", "bolt://localhost:7687"),
            username=conn.get("username", "neo4j"),
            password=password,
            database=conn.get("database", "neo4j"),
            max_connection_pool_size=conn.get("max_connection_pool_size", 50),
            connection_timeout=conn.get("connection_timeout", 30),
        )


class Neo4jClient:
    """Neo4j graph database client."""
    
    def __init__(self, config: Optional[Neo4jConfig] = None):
        """Initialize Neo4j client.
        
        Args:
            config: Neo4j configuration. If None, loads from default config file.
        """
        if GraphDatabase is None:
            raise ImportError(
                "neo4j package not installed. Run: pip install neo4j"
            )
        
        self.config = config or Neo4jConfig.from_yaml()
        self._driver: Optional[Driver] = None
        
    def connect(self) -> bool:
        """Establish connection to Neo4j.
        
        Returns:
            True if connection successful, False otherwise.
        """
        try:
            self._driver = GraphDatabase.driver(
                self.config.uri,
                auth=(self.config.username, self.config.password),
                max_connection_pool_size=self.config.max_connection_pool_size,
                connection_timeout=self.config.connection_timeout,
            )
            
            # Verify connection
            self._driver.verify_connectivity()
            logger.info(f"Connected to Neo4j at {self.config.uri}")
            return True
            
        except ServiceUnavailable as e:
            logger.error(f"Cannot connect to Neo4j: {e}")
            return False
        except AuthError as e:
            logger.error(f"Authentication failed: {e}")
            return False
    
    def close(self) -> None:
        """Close database connection."""
        if self._driver:
            self._driver.close()
            self._driver = None
            logger.info("Neo4j connection closed")
    
    def __enter__(self) -> "Neo4jClient":
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
    
    def _get_session(self) -> Session:
        """Get database session."""
        if not self._driver:
            raise RuntimeError("Not connected to Neo4j. Call connect() first.")
        return self._driver.session(database=self.config.database)
    
    def run_query(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Execute a Cypher query.
        
        Args:
            query: Cypher query string
            parameters: Query parameters
            
        Returns:
            List of records as dictionaries
        """
        parameters = parameters or {}
        
        with self._get_session() as session:
            result = session.run(query, parameters)
            return [record.data() for record in result]
    
    def run_query_single(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Execute a Cypher query and return single result.
        
        Args:
            query: Cypher query string
            parameters: Query parameters
            
        Returns:
            Single record as dictionary or None
        """
        results = self.run_query(query, parameters)
        return results[0] if results else None
    
    def init_schema(self, config_path: Optional[str] = None) -> bool:
        """Initialize database schema (constraints and indexes).
        
        Args:
            config_path: Path to config with schema definitions
            
        Returns:
            True if successful
        """
        if config_path is None:
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "config" / "neo4j.yaml"
        else:
            config_path = Path(config_path)
        
        if not config_path.exists():
            logger.warning(f"Schema config not found: {config_path}")
            return False
        
        with open(config_path, 'r') as f:
            raw_config = yaml.safe_load(f)
        
        schema_config = raw_config.get("schema", {})
        
        # Create constraints
        constraints = schema_config.get("constraints", [])
        for constraint_query in constraints:
            try:
                self.run_query(constraint_query)
                logger.info(f"Created constraint: {constraint_query[:50]}...")
            except ClientError as e:
                if "already exists" in str(e).lower():
                    logger.debug(f"Constraint already exists: {constraint_query[:50]}...")
                else:
                    logger.error(f"Failed to create constraint: {e}")
        
        # Create indexes
        indexes = schema_config.get("indexes", [])
        for index_query in indexes:
            try:
                self.run_query(index_query)
                logger.info(f"Created index: {index_query[:50]}...")
            except ClientError as e:
                if "already exists" in str(e).lower():
                    logger.debug(f"Index already exists: {index_query[:50]}...")
                else:
                    logger.error(f"Failed to create index: {e}")
        
        return True
    
    def clear_database(self, confirm: bool = False) -> bool:
        """Clear all data from database (DANGEROUS).
        
        Args:
            confirm: Must be True to actually delete
            
        Returns:
            True if successful
        """
        if not confirm:
            logger.warning("Database clear not confirmed. Pass confirm=True to proceed.")
            return False
        
        try:
            self.run_query("MATCH (n) DETACH DELETE n")
            logger.info("Database cleared successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to clear database: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics.
        
        Returns:
            Dictionary with node counts, relation counts, etc.
        """
        # Node counts by label
        node_query = """
        CALL apoc.meta.stats() YIELD labels, relTypesCount
        RETURN labels, relTypesCount
        """
        
        try:
            result = self.run_query_single(node_query)
            if result:
                return {
                    "node_counts_by_label": result.get("labels", {}),
                    "relation_counts_by_type": result.get("relTypesCount", {}),
                }
        except ClientError:
            # APOC not available, use alternative query
            pass
        
        # Fallback query
        fallback_query = """
        MATCH (n)
        RETURN labels(n) as labels, count(*) as count
        """
        
        node_results = self.run_query(fallback_query)
        node_counts = {}
        for record in node_results:
            for label in record.get("labels", []):
                node_counts[label] = node_counts.get(label, 0) + record.get("count", 0)
        
        # Relation counts
        rel_query = """
        MATCH ()-[r]->()
        RETURN type(r) as rel_type, count(*) as count
        """
        
        rel_results = self.run_query(rel_query)
        rel_counts = {r.get("rel_type"): r.get("count") for r in rel_results}
        
        return {
            "node_counts_by_label": node_counts,
            "relation_counts_by_type": rel_counts,
        }
    
    def merge_node(
        self,
        label: str,
        match_property: str,
        properties: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Merge (create or update) a node.
        
        Args:
            label: Node label (entity type)
            match_property: Property to match on
            properties: All node properties
            
        Returns:
            Created/merged node data or None
        """
        query, params = get_cypher_merge_node(label, match_property, properties)
        result = self.run_query_single(query, params)
        return result.get("n") if result else None
    
    def merge_relation(
        self,
        source_label: str,
        source_prop: str,
        source_value: Any,
        target_label: str,
        target_prop: str,
        target_value: Any,
        rel_type: str,
        properties: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Merge (create or update) a relationship.
        
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
            Created/merged relationship data or None
        """
        query, params = get_cypher_merge_relation(
            source_label, source_prop, source_value,
            target_label, target_prop, target_value,
            rel_type, properties
        )
        result = self.run_query_single(query, params)
        return result.get("r") if result else None
    
    def search_nodes(
        self,
        label: Optional[str] = None,
        property_name: Optional[str] = None,
        property_value: Optional[Any] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Search for nodes.
        
        Args:
            label: Node label to filter by
            property_name: Property name to filter by
            property_value: Property value to match
            limit: Maximum results
            
        Returns:
            List of matching nodes
        """
        conditions = []
        params = {"limit": limit}
        
        if label:
            label_clause = f":{label}"
        else:
            label_clause = ""
        
        if property_name and property_value is not None:
            conditions.append(f"n.{property_name} = ${property_name}")
            params[property_name] = property_value
        
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        
        query = f"""
        MATCH (n{label_clause})
        {where_clause}
        RETURN n
        LIMIT $limit
        """
        
        results = self.run_query(query, params)
        return [r.get("n") for r in results if r.get("n")]
    
    def get_node_neighbors(
        self,
        label: str,
        property_name: str,
        property_value: Any,
        rel_types: Optional[List[str]] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Get neighbors of a node.
        
        Args:
            label: Node label
            property_name: Match property name
            property_value: Match property value
            rel_types: Optional list of relationship types to filter
            
        Returns:
            Dictionary with 'incoming' and 'outgoing' neighbor lists
        """
        rel_filter = ""
        if rel_types:
            rel_filter = f"AND type(r) IN {rel_types}"
        
        # Outgoing
        outgoing_query = f"""
        MATCH (n:{label} {{{property_name}: $value}})-[r]->(m)
        {rel_filter}
        RETURN m, type(r) as rel_type, properties(r) as rel_props
        """
        
        outgoing = self.run_query(outgoing_query, {"value": property_value})
        
        # Incoming
        incoming_query = f"""
        MATCH (n:{label} {{{property_name}: $value}})<-[r]-(m)
        {rel_filter}
        RETURN m, type(r) as rel_type, properties(r) as rel_props
        """
        
        incoming = self.run_query(incoming_query, {"value": property_value})
        
        return {
            "outgoing": [
                {
                    "node": r.get("m"),
                    "relation_type": r.get("rel_type"),
                    "relation_properties": r.get("rel_props"),
                }
                for r in outgoing
            ],
            "incoming": [
                {
                    "node": r.get("m"),
                    "relation_type": r.get("rel_type"),
                    "relation_properties": r.get("rel_props"),
                }
                for r in incoming
            ],
        }


# Singleton instance
_client: Optional[Neo4jClient] = None


def get_client(config_path: Optional[str] = None) -> Neo4jClient:
    """Get singleton Neo4j client instance.
    
    Args:
        config_path: Optional path to config file
        
    Returns:
        Neo4jClient instance
    """
    global _client
    if _client is None:
        config = Neo4jConfig.from_yaml(config_path)
        _client = Neo4jClient(config)
    return _client


def reset_client() -> None:
    """Reset singleton client."""
    global _client
    if _client:
        _client.close()
    _client = None
