# Neo4j Knowledge Graph Documentation

## 1. Knowledge Graph Overview

The Neo4j Knowledge Graph is a graph database implementation that stores structured information extracted from bug reports and related software development artifacts. It enables complex relationship queries, pattern detection, and advanced analytics across the bug tracking domain.

### Current Statistics

- **Total Nodes:** 993 nodes
- **Total Relations:** 70 relations
- **Source:** 145 PDF documents processed
- **Entities Extracted:** 1380 entities
- **Relations Extracted:** 343 relations

### Technology Stack

- **Database:** Neo4j 5 Community Edition (Dockerized)
- **Access Ports:**
  - `7474` - Neo4j Browser (Web UI)
  - `7687` - Bolt Protocol (API connections)
- **Authentication:** neo4j / password
- **Extensions:** APOC (Awesome Procedures on Cypher) for graph algorithms

### Why Graph Database?

Graph databases are ideal for bug tracking data because they:
- Model relationships naturally (bugs, components, people, technologies)
- Enable efficient traversal of multi-hop connections
- Support pattern matching across complex networks
- Allow flexible schema evolution
- Provide foundation for RAG (Retrieval Augmented Generation) systems

---

## 2. Schema Definition

### 2.1 Entity Types (10 Total)

#### BugReport
Primary entity representing software bug reports.

| Property | Type | Description |
|----------|------|-------------|
| `id` | string | Unique identifier (UUID) |
| `title` | string | Bug title/summary |
| `description` | string | Detailed bug description |
| `status` | string | Current status (open/closed/in-progress) |
| `severity` | string | Severity level |
| `created_date` | datetime | When reported |
| `resolution_date` | datetime | When resolved (if applicable) |
| `component` | string | Related component name |

#### Component
Software components affected by bugs.

| Property | Type | Description |
|----------|------|-------------|
| `name` | string | Component name |
| `description` | string | Component description |
| `category` | string | Component category |
| `product` | string | Associated product |

#### Technology
Technologies mentioned in bug reports.

| Property | Type | Description |
|----------|------|-------------|
| `name` | string | Technology name |
| `type` | string | Type (framework, library, tool) |
| `version` | string | Version mentioned |
| `description` | string | Description |

#### Severity
Bug severity classification.

| Property | Type | Description |
|----------|------|-------------|
| `level` | string | Severity level (critical/high/medium/low) |
| `description` | string | Description of severity |

#### Status
Bug status tracking.

| Property | Type | Description |
|----------|------|-------------|
| `status` | string | Status value |
| `is_open` | boolean | Whether bug is open |
| `is_resolved` | boolean | Whether bug is resolved |

#### Person
People mentioned in bug reports (reporters, assignees, etc.).

| Property | Type | Description |
|----------|------|-------------|
| `name` | string | Person's name |
| `email` | string | Email address |
| `role` | string | Role (reporter, assignee, etc.) |
| `organization` | string | Organization name |

#### Organization
Organizations involved with bugs.

| Property | Type | Description |
|----------|------|-------------|
| `name` | string | Organization name |
| `type` | string | Type (company, team, etc.) |
| `description` | string | Description |

#### CodeReference
References to code in bug reports.

| Property | Type | Description |
|----------|------|-------------|
| `reference` | string | Code reference identifier |
| `file_path` | string | Path to file |
| `line_number` | integer | Line number mentioned |

#### ErrorMessage
Error messages mentioned in bugs.

| Property | Type | Description |
|----------|------|-------------|
| `message` | string | Error message text |
| `error_type` | string | Type of error |
| `stack_trace` | string | Stack trace (truncated) |

#### Feature
Features affected by or related to bugs.

| Property | Type | Description |
|----------|------|-------------|
| `name` | string | Feature name |
| `description` | string | Feature description |
| `category` | string | Feature category |

### 2.2 Relation Types (15 Total)

| Relation | From | To | Description |
|----------|------|-----|-------------|
| `HAS_COMPONENT` | BugReport | Component | Bug affects component |
| `HAS_SEVERITY` | BugReport | Severity | Bug severity level |
| `HAS_STATUS` | BugReport | Status | Bug current status |
| `MENTIONS` | BugReport | Technology | Bug mentions technology |
| `MENTIONS_TECH` | BugReport | Technology | Alternative tech mention |
| `RELATED_TO` | BugReport | BugReport | Related bugs |
| `REPORTED_BY` | BugReport | Person | Who reported |
| `ASSIGNED_TO` | BugReport | Person | Who is assigned |
| `AFFECTS` | BugReport | Component | Component affected |
| `BLOCKS` | BugReport | BugReport | Bug blocks another |
| `DUPLICATE_OF` | BugReport | BugReport | Duplicate relationship |
| `DEPENDS_ON` | BugReport | BugReport | Dependency relationship |
| `HAS_ERROR` | BugReport | ErrorMessage | Error in bug |
| `AFFECTS_FEATURE` | BugReport | Feature | Feature affected |
| `MENTIONS_PERSON` | BugReport | Person | Person mentioned |

---

## 3. Entity Extraction Pipeline

### LLM-Powered Extraction

The system uses `llama3.2:3b` via Ollama for intelligent entity extraction from PDF content.

#### Extraction Strategy

- **Per-Page Extraction:** Each PDF page is processed individually (not combined)
- **Confidence Threshold:** 0.6 (minimum confidence for LLM-extracted entities)
- **Fallback Mechanism:** Rule-based extraction when confidence < 0.6
- **Schema Validation:** All entities validated against ENTITY_SCHEMAS

#### Confidence Scoring

```python
# LLM extraction with confidence threshold
llama3.2:3b extracts entities with confidence scores
if confidence >= 0.6:
    keep_llm_entities()
else:
    fallback_to_rule_based()
```

#### Rule-Based Fallback

When LLM confidence is low, the system uses regex and keyword matching:
- Email pattern matching for Person entities
- Error message patterns (stack traces, exceptions)
- Component name detection
- Technology keyword matching

---

## 4. Docker Setup

### docker-compose.yml Configuration

```yaml
version: '3.8'

services:
  neo4j:
    image: neo4j:5-community
    container_name: neo4j-kg
    ports:
      - "7474:7474"  # Browser
      - "7687:7687"  # Bolt
    environment:
      - NEO4J_AUTH=neo4j/password
      - NEO4J_PLUGINS=["apoc"]
      - NEO4J_dbms_memory_heap_max__size=2G
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs
    restart: unless-stopped

volumes:
  neo4j_data:
  neo4j_logs:
```

### Access Points

- **Neo4j Browser:** http://localhost:7474
- **Bolt Protocol:** bolt://localhost:7687
- **Credentials:** neo4j / password

### APOC Plugin

The APOC (Awesome Procedures on Cypher) plugin provides:
- Graph algorithms (PageRank, centrality measures)
- Data integration utilities
- Advanced Cypher functions
- Graph visualization helpers

---

## 5. Bulk Import Pipeline

### File: `src/kg/bulk_import.py`

The bulk import system processes PDF documents and imports entities/relations into Neo4j efficiently.

#### BatchImporter Class

Key features:
- **Batch Processing:** Imports entities in batches for efficiency
- **Checkpoint System:** Saves progress to resume interrupted imports
- **Parallel Processing:** 3 workers for concurrent PDF processing
- **Resource Management:** Max 15 pages per PDF to control processing time

#### Pipeline Statistics

```python
Processing Summary:
- PDFs Processed: 145
- Entities Extracted: 1380
- Relations Extracted: 343
- Processing Mode: Per-page extraction
- Max Pages: 15 per PDF
- Workers: 3 parallel
```

#### Checkpoint System

Checkpoints are saved to track progress:
- `last_processed_pdf`: Last successfully processed PDF filename
- `completed_pdfs`: List of all completed PDFs
- `entity_counts`: Breakdown by entity type
- `error_log`: Failed PDFs with error messages

---

## 6. Key Python Files

### 6.1 src/kg/client.py - Neo4jClient

Main interface for Neo4j database operations.

```python
from src.kg.client import Neo4jClient

client = Neo4jClient()

# Create entity
client.create_entity("BugReport", {
    "id": "BUG-001",
    "title": "Login failure",
    "status": "open"
})

# Create relation
client.create_relation("BUG-001", "HAS_COMPONENT", "auth-module")

# Query database
results = client.query("MATCH (n) RETURN count(n) as count")
```

### 6.2 src/kg/schema.py - Schema Definitions

Central schema repository for validation.

```python
from src.kg.schema import ENTITY_SCHEMAS, RELATION_SCHEMAS

# Entity schema structure
ENTITY_SCHEMAS = {
    "BugReport": {
        "required": ["id", "title"],
        "optional": ["description", "status", "severity"],
        "properties": {
            "id": {"type": "string"},
            "title": {"type": "string"},
            # ...
        }
    },
    # ... 9 other entity types
}

# Relation schema structure
RELATION_SCHEMAS = {
    "HAS_COMPONENT": {
        "from": "BugReport",
        "to": "Component"
    },
    # ... 14 other relation types
}
```

### 6.3 src/kg/bulk_import.py - BulkImporter

Full pipeline implementation.

```python
from src.kg.bulk_import import BatchImporter

importer = BatchImporter(
    neo4j_uri="bolt://localhost:7687",
    username="neo4j",
    password="password",
    max_workers=3
)

# Process single PDF
importer.process_pdf("/path/to/bug_report.pdf")

# Process directory
importer.process_directory("/path/to/pdfs/")
```

### 6.4 scripts/build_knowledge_graph.py - Pipeline Script

Command-line interface for building the knowledge graph.

```python
# Process all PDFs in directory
python scripts/build_knowledge_graph.py --input-dir data/pdfs/

# Process single PDF
python scripts/build_knowledge_graph.py --input-file report.pdf

# Resume from checkpoint
python scripts/build_knowledge_graph.py --resume
```

---

## 7. Cypher Query Examples

### View All Node Counts by Type

```cypher
MATCH (n)
RETURN labels(n)[0] as node_type, count(n) as count
ORDER BY count DESC
```

**Result:**
| node_type | count |
|-----------|-------|
| Component | 310 |
| Organization | 157 |
| Person | 144 |
| Technology | 133 |
| BugReport | 99 |
| Feature | 67 |
| Status | 42 |
| Severity | 28 |
| ErrorMessage | 8 |
| CodeReference | 5 |

### Find Bugs by Component

```cypher
MATCH (b:BugReport)-[:HAS_COMPONENT]->(c:Component)
WHERE c.name CONTAINS 'authentication'
RETURN b.title, b.status, c.name
```

### Find People Who Reported Critical Bugs

```cypher
MATCH (b:BugReport)-[:HAS_SEVERITY]->(s:Severity {level: 'critical'})
MATCH (b)-[:REPORTED_BY]->(p:Person)
RETURN p.name, p.email, count(b) as critical_bugs
ORDER BY critical_bugs DESC
```

### View Related Bugs

```cypher
MATCH (b1:BugReport)-[:RELATED_TO|BLOCKS|DUPLICATE_OF]->(b2:BugReport)
WHERE b1.id = 'BUG-001'
RETURN b2.id, b2.title, type(r) as relationship
```

### Find Technology Dependencies

```cypher
MATCH (b:BugReport)-[:MENTIONS]->(t:Technology)
RETURN t.name, t.type, count(b) as bug_count
ORDER BY bug_count DESC
LIMIT 10
```

---

## 8. Current Status

### Node Distribution

| Entity Type | Count | Percentage |
|-------------|-------|------------|
| Component | 310 | 31.2% |
| Organization | 157 | 15.8% |
| Person | 144 | 14.5% |
| Technology | 133 | 13.4% |
| BugReport | 99 | 10.0% |
| Feature | 67 | 6.7% |
| Status | 42 | 4.2% |
| Severity | 28 | 2.8% |
| ErrorMessage | 8 | 0.8% |
| CodeReference | 5 | 0.5% |
| **Total** | **993** | **100%** |

### Relation Statistics

- **Total Relations:** 70
- **Most Common:** HAS_COMPONENT, MENTIONS, HAS_SEVERITY
- **Least Common:** BLOCKS, DUPLICATE_OF, CODE_REF

### Data Quality

- **Extraction Confidence:** Average 0.75
- **Schema Compliance:** 100%
- **Duplicate Entities:** < 5% (merged on name/id)
- **Orphaned Relations:** 0%

---

## 9. Usage Scripts

### build_knowledge_graph.py

Full pipeline script for building the knowledge graph from PDF documents.

#### Process All PDFs

```bash
python scripts/build_knowledge_graph.py \
    --input-dir data/pdfs/ \
    --max-pages 15 \
    --workers 3
```

#### Test Single PDF

```bash
python scripts/build_knowledge_graph.py \
    --input-file data/pdfs/sample_bug.pdf \
    --verbose
```

#### Resume from Checkpoint

```bash
python scripts/build_knowledge_graph.py \
    --input-dir data/pdfs/ \
    --resume
```

#### Dry Run (No Database Write)

```bash
python scripts/build_knowledge_graph.py \
    --input-dir data/pdfs/ \
    --dry-run
```

### Common Options

| Option | Description | Default |
|--------|-------------|---------|
| `--input-dir` | Directory with PDFs | None |
| `--input-file` | Single PDF file | None |
| `--max-pages` | Max pages per PDF | 15 |
| `--workers` | Parallel workers | 3 |
| `--resume` | Resume from checkpoint | False |
| `--dry-run` | No database writes | False |
| `--verbose` | Detailed logging | False |

---

## 10. Next Steps

### Query Optimization

- [ ] Implement query caching layer
- [ ] Add full-text search indices
- [ ] Create materialized views for common queries
- [ ] Optimize traversal patterns

### RAG Integration

- [ ] Connect to vector database for embeddings
- [ ] Implement semantic search over bug reports
- [ ] Create hybrid retrieval (graph + semantic)
- [ ] Build question-answering pipeline

### Graph Visualization

- [ ] Neo4j Bloom integration
- [ ] Interactive web dashboard
- [ ] Custom D3.js visualizations
- [ ] Relationship explorer tool

### Data Enhancement

- [ ] Link to external sources (GitHub, JIRA)
- [ ] Add temporal analysis
- [ ] Implement entity resolution improvements
- [ ] Create automated data quality checks

---

## Appendix: File Locations

```
/Users/sachin/Desktop/Uni Courses/CSE 573 - SWM/2Project/
├── src/kg/
│   ├── __init__.py
│   ├── client.py              # Neo4jClient class
│   ├── schema.py              # Entity/relation schemas
│   ├── bulk_import.py         # BatchImporter class
│   └── entity_extractor.py    # LLM extraction logic
├── scripts/
│   └── build_knowledge_graph.py  # Main pipeline script
├── docs/
│   └── KNOWLEDGE_GRAPH.md     # This documentation
├── data/
│   └── pdfs/                  # Source PDF documents
└── docker-compose.yml          # Neo4j Docker config
```

---

*Last updated: March 2026*
*System: Neo4j 5 Community with APOC*
*Database: 993 nodes, 70 relations*
