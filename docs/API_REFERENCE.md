# API Reference

Complete Python API reference for all major modules in the PDF/OCR extraction pipeline.

## Table of Contents

- [src.extraction](#srcextraction) - PDF extraction modules
- [src.evaluation](#srcevaluation) - Metrics and benchmarking
- [src.kg](#srckg) - Knowledge graph operations
- [src.llm](#srcllm) - LLM integration

---

## src.extraction

PDF extraction modules providing native, OCR, and hybrid extraction capabilities.

### extract_native

Extract text, tables, and metadata from PDFs using pdfplumber with per-page analysis.

**Function Signature:**
```python
def extract_native(pdf_path: str) -> Dict[str, Any]
```

**Parameters:**
- `pdf_path` (str): Path to the input PDF file

**Returns:**
```python
{
    "pages": [
        {
            "text": str,              # Extracted text for this page
            "tables": List[List],     # Tables on this page
            "coverage": float,        # Text coverage (0.0-1.0)
            "word_count": int,        # Number of words
            "char_count": int         # Number of characters
        }
    ],
    "metadata": Dict,             # PDF metadata
    "total_pages": int,           # Total number of pages
    "overall_coverage": float     # Average coverage across all pages
}
```

**Raises:**
- `FileNotFoundError`: If PDF file does not exist
- `Exception`: For other extraction errors

**Example:**
```python
from src.extraction import extract_native

result = extract_native("data/batch3/MOZILLA/bug_report.pdf")
print(f"Total pages: {result['total_pages']}")
print(f"Overall coverage: {result['overall_coverage']:.2%}")

for page in result['pages']:
    print(f"Page {page['page_number']}: {page['word_count']} words")
```

---

### extract_ocr

Extract text from images using GLM-OCR HTTP API with retry logic.

**Function Signature:**
```python
def extract_ocr(
    image_path: str,
    max_tokens: int = 4096,
    max_retries: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    timeout: int = 300
) -> str
```

**Parameters:**
- `image_path` (str): Path to image file (PNG, JPEG, etc.)
- `max_tokens` (int): Maximum tokens to generate (default: 4096)
- `max_retries` (int): Maximum retry attempts (default: 3)
- `base_delay` (float): Initial retry delay in seconds (default: 2.0)
- `max_delay` (float): Maximum retry delay (default: 60.0)
- `timeout` (int): Request timeout in seconds (default: 300)

**Returns:**
- `str`: Extracted text content

**Raises:**
- `FileNotFoundError`: Image file not found
- `GLMOCRConnectionError`: Cannot connect to OCR server
- `GLMOCRServerError`: Server returned error after all retries

**Example:**
```python
from src.extraction import extract_ocr

try:
    text = extract_ocr(
        "document_page_1.png",
        max_tokens=4096,
        timeout=300
    )
    print(f"Extracted {len(text)} characters")
except GLMOCRConnectionError:
    print("OCR server not running. Start with: mlx_vlm.server --trust-remote-code")
```

**Exception Classes:**
```python
from src.extraction import GLMOCRClientError, GLMOCRServerError, GLMOCRConnectionError
```

---

### BatchProcessor

Process multiple PDFs in parallel with checkpoint management.

**Class:** `BatchProcessor`

**Constructor:**
```python
def __init__(
    self,
    output_dir: str,
    checkpoint_path: str,
    project_name: str,
    max_pages: int = 20,
    parallel_workers: int = 3,
    save_images: bool = True,
    ocr_dpi: int = 200,
    ocr_timeout: int = 300
)
```

**Parameters:**
- `output_dir` (str): Base output directory
- `checkpoint_path` (str): Path to checkpoint JSON file
- `project_name` (str): Name of processing project
- `max_pages` (int): Maximum pages per PDF (skip if exceeded)
- `parallel_workers` (int): Number of parallel workers
- `save_images` (bool): Save converted images
- `ocr_dpi` (int): DPI for image conversion
- `ocr_timeout` (int): OCR request timeout

**Methods:**

#### process_batch
```python
def process_batch(
    self,
    pdf_paths: List[str],
    limit: Optional[int] = None,
    limit_pages_per_pdf: Optional[int] = None
) -> List[Dict]
```

Process a batch of PDFs with parallel workers.

**Example:**
```python
from src.extraction import BatchProcessor

processor = BatchProcessor(
    output_dir="data/processed/mozilla",
    checkpoint_path="data/processed/mozilla/checkpoint.json",
    project_name="mozilla_batch",
    max_pages=20,
    parallel_workers=3,
    save_images=True
)

pdf_paths = ["doc1.pdf", "doc2.pdf", "doc3.pdf"]
results = processor.process_batch(pdf_paths, limit=10)

for result in results:
    print(f"{result['source_pdf']}: {result['status']}")
```

#### get_failed_files
```python
def get_failed_files(self) -> Dict[str, str]
```

Get dictionary of failed files with error messages.

#### get_skipped_files
```python
def get_skipped_files(self) -> Dict[str, str]
```

Get dictionary of skipped files with reasons.

---

### CheckpointManager

Track processing progress and enable resume capability.

**Class:** `CheckpointManager`

**Constructor:**
```python
def __init__(self, checkpoint_path: str, project_name: str)
```

**Methods:**

#### is_processed
```python
def is_processed(self, pdf_path: str) -> bool
```

Check if a file has been completely processed.

#### mark_file_complete
```python
def mark_file_complete(self, pdf_path: str)
```

Mark entire file as completely processed.

#### mark_file_failed
```python
def mark_file_failed(self, pdf_path: str, error: str, stage: str = "unknown")
```

Mark file as failed with error message.

#### mark_file_skipped
```python
def mark_file_skipped(
    self, 
    pdf_path: str, 
    reason: str, 
    extra_info: Optional[Dict] = None
)
```

Mark file as skipped with reason.

#### get_stats
```python
def get_stats(self) -> Dict[str, int]
```

Get processing statistics.

**Returns:**
```python
{
    "processed": int,    # Number of successfully processed files
    "failed": int,       # Number of failed files
    "skipped": int,      # Number of skipped files
    "in_progress": int   # Number of files currently being processed
}
```

#### reset_file
```python
def reset_file(self, pdf_path: str)
```

Reset a file to reprocess it.

#### reset_all
```python
def reset_all(self)
```

Reset entire checkpoint (use with caution!).

**Example:**
```python
from src.extraction import CheckpointManager

checkpoint = CheckpointManager(
    checkpoint_path="data/processed/checkpoint.json",
    project_name="my_batch"
)

# Check if file is already processed
if not checkpoint.is_processed("document.pdf"):
    # Process file...
    checkpoint.mark_file_complete("document.pdf")

# Get statistics
stats = checkpoint.get_stats()
print(f"Processed: {stats['processed']}, Failed: {stats['failed']}")

# Reset failed files to retry
for pdf_path in checkpoint.get_failed_files():
    checkpoint.reset_file(pdf_path)
```

---

## src.evaluation

Evaluation framework for PDF text extraction quality assessment.

### calculate_cer

Calculate Character Error Rate (CER) between predicted and ground truth text.

**Formula:** CER = (Substitutions + Insertions + Deletions) / Total Characters

**Function Signature:**
```python
def calculate_cer(predicted: str, ground_truth: str) -> float
```

**Parameters:**
- `predicted` (str): The predicted/extracted text
- `ground_truth` (str): The reference/ground truth text

**Returns:**
- `float`: Character Error Rate (0.0-1.0)

**Example:**
```python
from src.evaluation import calculate_cer

cer = calculate_cer("hello", "hallo")
print(f"CER: {cer:.3f}")  # 0.200 (1 substitution out of 5 chars)

cer = calculate_cer("test", "test")
print(f"CER: {cer:.3f}")  # 0.000 (identical)
```

---

### calculate_wer

Calculate Word Error Rate (WER) between predicted and ground truth text.

**Formula:** WER = (Substitutions + Insertions + Deletions) / Total Words

**Function Signature:**
```python
def calculate_wer(predicted: str, ground_truth: str) -> float
```

**Parameters:**
- `predicted` (str): The predicted/extracted text
- `ground_truth` (str): The reference/ground truth text

**Returns:**
- `float`: Word Error Rate (0.0-1.0)

**Example:**
```python
from src.evaluation import calculate_wer

wer = calculate_wer("the quick brown fox", "the fast brown fox")
print(f"WER: {wer:.3f}")  # 0.250 (1 word substitution out of 4)
```

---

### calculate_all_metrics

Calculate all available metrics at once.

**Function Signature:**
```python
def calculate_all_metrics(predicted: str, ground_truth: str) -> dict
```

**Returns:**
```python
{
    "cer": float,                # Character Error Rate
    "wer": float,                # Word Error Rate
    "similarity": float,         # Text similarity (0.0-1.0)
    "pred_length": int,          # Length of predicted text
    "gt_length": int,            # Length of ground truth text
    "pred_words": int,           # Word count of predicted
    "gt_words": int              # Word count of ground truth
}
```

**Example:**
```python
from src.evaluation import calculate_all_metrics

metrics = calculate_all_metrics("extracted text", "ground truth text")
print(f"CER: {metrics['cer']:.3%}")
print(f"WER: {metrics['wer']:.3%}")
print(f"Similarity: {metrics['similarity']:.3%}")
```

---

### Benchmark

Comprehensive benchmarking framework for extraction methods.

**Class:** `Benchmark`

**Constructor:**
```python
def __init__(self, output_dir: Optional[str] = None)
```

**Parameters:**
- `output_dir` (str, optional): Directory to save results (default: ./benchmark_results)

**Methods:**

#### run_ablation
```python
def run_ablation(
    self,
    pdf_paths: List[str],
    method: str,
    extract_fn: Callable[[str], Dict[str, Any]],
    ground_truth_fn: Optional[Callable[[str], str]] = None
) -> List[BenchmarkResult]
```

Run ablation experiment for a specific extraction method.

**Parameters:**
- `pdf_paths` (List[str]): List of PDF file paths
- `method` (str): Extraction method ('native', 'ocr', or 'hybrid')
- `extract_fn` (Callable): Function that takes PDF path and returns extraction result
- `ground_truth_fn` (Callable, optional): Function to retrieve ground truth text

**Supported Methods:**
- `'native'`: Native-only extraction
- `'ocr'`: OCR-only extraction
- `'hybrid'`: Smart routing based on coverage

**Example:**
```python
from src.evaluation import Benchmark
from src.extraction import extract_native

def custom_extract(pdf_path: str) -> Dict[str, Any]:
    result = extract_native(pdf_path)
    return {
        'text': '\n\n'.join([p['text'] for p in result['pages']]),
        'total_pages': result['total_pages']
    }

def get_ground_truth(pdf_path: str) -> str:
    # Load from annotation file
    with open(f"ground_truth/{Path(pdf_path).stem}.txt") as f:
        return f.read()

benchmark = Benchmark(output_dir="./benchmark_results")

# Run ablation
results = benchmark.run_ablation(
    pdf_paths=["doc1.pdf", "doc2.pdf"],
    method='native',
    extract_fn=custom_extract,
    ground_truth_fn=get_ground_truth
)

for result in results:
    print(f"{result.pdf_path}: {result.pages_per_second:.2f} pages/sec")
```

#### compare_methods
```python
def compare_methods(
    self, 
    results: Optional[Dict[str, List[BenchmarkResult]]] = None
) -> ComparisonReport
```

Generate comparison report across multiple methods.

**Example:**
```python
# After running multiple ablations
all_results = {
    'native': native_results,
    'ocr': ocr_results,
    'hybrid': hybrid_results
}

report = benchmark.compare_methods(all_results)

# Print comparison table
from src.evaluation import print_comparison_table
print_comparison_table(report)
```

---

## src.kg

Knowledge graph operations for Neo4j database.

### Neo4jClient

Neo4j graph database client with connection management.

**Class:** `Neo4jClient`

**Constructor:**
```python
def __init__(self, config: Optional[Neo4jConfig] = None)
```

**Parameters:**
- `config` (Neo4jConfig, optional): Configuration object. If None, loads from default config file.

**Methods:**

#### connect
```python
def connect(self) -> bool
```

Establish connection to Neo4j.

**Returns:** `True` if successful, `False` otherwise

**Example:**
```python
from src.kg import Neo4jClient

client = Neo4jClient()
if client.connect():
    print("Connected to Neo4j")
    # ... use client
    client.close()
else:
    print("Failed to connect")
```

#### close
```python
def close(self) -> None
```

Close database connection.

#### run_query
```python
def run_query(
    self, 
    query: str, 
    parameters: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]
```

Execute a Cypher query.

**Parameters:**
- `query` (str): Cypher query string
- `parameters` (dict, optional): Query parameters

**Returns:** List of records as dictionaries

**Example:**
```python
# Find all bug reports
results = client.run_query(
    "MATCH (n:BugReport) RETURN n LIMIT 10"
)
for record in results:
    print(record['n']['title'])
```

#### init_schema
```python
def init_schema(self, config_path: Optional[str] = None) -> bool
```

Initialize database schema (constraints and indexes).

**Example:**
```python
# Create constraints and indexes
client.init_schema()
```

#### get_stats
```python
def get_stats(self) -> Dict[str, Any]
```

Get database statistics.

**Returns:**
```python
{
    "node_counts_by_label": {
        "BugReport": int,
        "Component": int,
        # ... other entity types
    },
    "relation_counts_by_type": {
        "HAS_COMPONENT": int,
        "RELATED_TO": int,
        # ... other relation types
    }
}
```

**Example:**
```python
stats = client.get_stats()
for label, count in stats['node_counts_by_label'].items():
    print(f"{label}: {count} nodes")
```

#### clear_database
```python
def clear_database(self, confirm: bool = False) -> bool
```

Clear all data from database (DANGEROUS).

**Parameters:**
- `confirm` (bool): Must be True to actually delete

**Example:**
```python
# Clear all data
client.clear_database(confirm=True)
```

---

### BulkImporter

Efficient bulk import pipeline for Neo4j.

**Class:** `BulkImporter`

**Constructor:**
```python
def __init__(
    self,
    client: Optional[Neo4jClient] = None,
    batch_size: int = 1000,
    max_retries: int = 3,
    skip_duplicates: bool = True,
)
```

**Parameters:**
- `client` (Neo4jClient, optional): Neo4j client. If None, uses singleton.
- `batch_size` (int): Number of entities/relations per batch
- `max_retries` (int): Maximum retry attempts for failed operations
- `skip_duplicates` (bool): Skip duplicate entities silently

**Methods:**

#### import_extraction_result
```python
def import_extraction_result(
    self,
    result: ExtractionResult,
    create_relations: bool = True
) -> bool
```

Import a single extraction result into Neo4j.

**Example:**
```python
from src.kg import BulkImporter
from src.llm.chains import ExtractionResult

importer = BulkImporter(client=client, batch_size=100)

# Import single result
success = importer.import_extraction_result(extraction_result)
print(f"Import {'successful' if success else 'failed'}")
```

#### import_batch
```python
def import_batch(
    self,
    results: List[ExtractionResult],
    progress_bar: bool = True
) -> ImportStats
```

Import multiple extraction results in batch.

**Example:**
```python
results = [result1, result2, result3]
stats = importer.import_batch(results, progress_bar=True)

print(f"Entities created: {stats.entities_created}")
print(f"Relations created: {stats.relations_created}")
print(f"Documents processed: {stats.documents_processed}")
```

#### import_from_directory
```python
def import_from_directory(
    self,
    directory: str,
    pattern: str = "*.json",
    progress_bar: bool = True
) -> ImportStats
```

Import all JSON files from a directory.

**Example:**
```python
stats = importer.import_from_directory(
    "data/processed/results",
    pattern="*_results.json"
)
```

---

### Schema Functions

#### get_entity_schema
```python
def get_entity_schema(entity_type: str) -> Optional[EntitySchema]
```

Get schema definition for an entity type.

**Available Entity Types:**
- `BugReport`: Software bug/issue reports
- `Component`: Software components/modules
- `Technology`: Languages, frameworks, libraries
- `Severity`: Bug severity levels
- `Status`: Bug status in workflow
- `Person`: People mentioned in reports
- `Organization`: Companies/teams
- `CodeReference`: File/function references
- `ErrorMessage`: Error messages/stack traces
- `Feature`: Product features

**Example:**
```python
from src.kg import get_entity_schema

schema = get_entity_schema("BugReport")
print(f"Required properties: {schema.required_properties}")
print(f"Optional properties: {schema.optional_properties}")
```

#### get_relation_schema
```python
def get_relation_schema(relation_type: str) -> Optional[RelationSchema]
```

Get schema definition for a relation type.

**Available Relation Types:**
- `HAS_COMPONENT`: Bug -> Component
- `HAS_SEVERITY`: Bug -> Severity
- `HAS_STATUS`: Bug -> Status
- `MENTIONS`: Bug -> AnyEntity
- `RELATED_TO`: Bug -> Bug
- `REPORTED_BY`: Bug -> Person
- `ASSIGNED_TO`: Bug -> Person
- `AFFECTS`: Bug -> Technology
- `BLOCKS`: Bug -> Bug
- `DUPLICATE_OF`: Bug -> Bug
- `DEPENDS_ON`: Bug -> Bug
- `HAS_ERROR`: Bug -> ErrorMessage
- `AFFECTS_FEATURE`: Bug -> Feature

#### get_cypher_merge_node
```python
def get_cypher_merge_node(
    entity_type: str,
    match_property: str,
    properties: Dict[str, Any]
) -> tuple
```

Generate Cypher MERGE statement for idempotent node creation.

**Returns:** Tuple of (query_string, params_dict)

**Example:**
```python
from src.kg import get_cypher_merge_node

query, params = get_cypher_merge_node(
    entity_type="BugReport",
    match_property="id",
    properties={
        "id": "MOZILLA-123456",
        "title": "Crash on startup",
        "status": "RESOLVED"
    }
)

result = client.run_query_single(query, params)
```

#### get_cypher_merge_relation
```python
def get_cypher_merge_relation(
    source_label: str,
    source_prop: str,
    source_value: Any,
    target_label: str,
    target_prop: str,
    target_value: Any,
    rel_type: str,
    properties: Optional[Dict[str, Any]] = None
) -> tuple
```

Generate Cypher MERGE statement for a relationship.

**Example:**
```python
from src.kg import get_cypher_merge_relation

query, params = get_cypher_merge_relation(
    source_label="BugReport",
    source_prop="id",
    source_value="MOZILLA-123456",
    target_label="Component",
    target_prop="name",
    target_value="JavaScript Engine",
    rel_type="HAS_COMPONENT"
)
```

---

## src.llm

LLM integration supporting multiple providers with runtime switching.

### UnifiedLLMClient

Unified client for multiple LLM providers.

**Class:** `UnifiedLLMClient`

**Constructor:**
```python
def __init__(
    self, 
    provider_name: Optional[str] = None, 
    config_path: Optional[str] = None
)
```

**Parameters:**
- `provider_name` (str, optional): Provider to use. If None, uses config default.
- `config_path` (str, optional): Path to LLM config file.

**Supported Providers:**
- `ollama`: Local inference (default)
- `claude`: Anthropic Claude API
- `openai`: OpenAI GPT API
- `gemini`: Google Gemini API

**Methods:**

#### switch_provider
```python
def switch_provider(self, provider_name: str) -> None
```

Switch to a different LLM provider at runtime.

**Example:**
```python
from src.llm import UnifiedLLMClient

client = UnifiedLLMClient()  # Uses default provider

# Switch providers
client.switch_provider("claude")
print(f"Current provider: {client.get_current_provider()}")

# Switch back
client.switch_provider("ollama")
```

#### get_available_providers
```python
def get_available_providers(self) -> List[str]
```

Get list of available (enabled) providers.

#### chat
```python
def chat(self, messages: List[BaseMessage], **kwargs) -> LLMResponse
```

Send chat messages and get response.

**Parameters:**
- `messages` (List[BaseMessage]): List of LangChain messages
- `**kwargs`: Additional arguments for the provider

**Returns:** `LLMResponse` with standardized format

**Example:**
```python
from langchain_core.messages import HumanMessage, SystemMessage

messages = [
    SystemMessage(content="You are a helpful assistant."),
    HumanMessage(content="Extract entities from this text: ...")
]

response = client.chat(messages)
print(f"Response: {response.content}")
print(f"Tokens used: {response.token_usage.total_tokens}")
print(f"Provider: {response.provider}")
print(f"Model: {response.model}")
```

#### chat_text
```python
def chat_text(
    self, 
    prompt: str, 
    system_prompt: Optional[str] = None, 
    **kwargs
) -> LLMResponse
```

Send text prompt (convenience method).

**Example:**
```python
response = client.chat_text(
    prompt="What are the main topics in this document?",
    system_prompt="You are a document analysis expert."
)
```

#### stream
```python
def stream(
    self, 
    messages: List[BaseMessage], 
    **kwargs
) -> Generator[str, None, None]
```

Stream response tokens.

**Example:**
```python
messages = [HumanMessage(content="Tell me a story.")]

for chunk in client.stream(messages):
    print(chunk, end="", flush=True)
```

#### stream_text
```python
def stream_text(
    self, 
    prompt: str, 
    system_prompt: Optional[str] = None, 
    **kwargs
) -> Generator[str, None, None]
```

Stream response from text prompt.

---

### EntityExtractionChain

Chain for extracting entities and relations from text using LLM.

**Class:** `EntityExtractionChain`

**Constructor:**
```python
def __init__(
    self,
    llm_client: Optional[UnifiedLLMClient] = None,
    min_confidence: float = 0.7,
    enable_fallback: bool = True,
)
```

**Parameters:**
- `llm_client` (UnifiedLLMClient, optional): LLM client to use
- `min_confidence` (float): Minimum confidence threshold
- `enable_fallback` (bool): Enable rule-based fallback

**Methods:**

#### extract
```python
def extract(self, text: str, document_id: str = "") -> ExtractionResult
```

Extract entities and relations from text.

**Parameters:**
- `text` (str): Text to extract from
- `document_id` (str): Document identifier for tracking

**Returns:** `ExtractionResult` with entities and relations

**Example:**
```python
from src.llm import EntityExtractionChain

chain = EntityExtractionChain(
    llm_client=client,
    min_confidence=0.6,
    enable_fallback=True
)

text = """
Bug 123456: Firefox crashes on startup
Component: JavaScript Engine
Reporter: john@example.com
Status: NEW
Severity: Critical
"""

result = chain.extract(text, document_id="bug123456")

print(f"Found {len(result.entities)} entities:")
for entity in result.entities:
    print(f"  - {entity.name} ({entity.type}) [confidence: {entity.confidence:.2f}]")

print(f"\nFound {len(result.relations)} relations:")
for relation in result.relations:
    print(f"  - {relation.source} -> {relation.target} ({relation.type})")

# Filter by confidence
high_confidence = result.get_entities_by_confidence(min_confidence=0.8)
print(f"\nHigh confidence entities: {len(high_confidence)}")
```

---

### Convenience Functions

#### get_client
```python
def get_client(
    provider_name: Optional[str] = None, 
    config_path: Optional[str] = None
) -> UnifiedLLMClient
```

Get singleton LLM client instance.

**Example:**
```python
from src.llm import get_client

client = get_client()  # Creates or returns existing instance
client = get_client("claude")  # Switch to Claude provider
```

#### extract_entities
```python
def extract_entities(
    text: str,
    document_id: str = "",
    provider: Optional[str] = None,
    min_confidence: float = 0.7,
) -> ExtractionResult
```

Convenience function to extract entities from text.

**Example:**
```python
from src.llm import extract_entities

result = extract_entities(
    text="Bug 789: Memory leak in JavaScript engine",
    document_id="bug789",
    provider="claude",
    min_confidence=0.6
)
```

---

### Data Classes

#### LLMResponse

Standardized LLM response format.

**Attributes:**
```python
content: str                           # Response text
provider: str                         # Provider name (ollama, claude, etc.)
model: str                            # Model name
token_usage: TokenUsage              # Token tracking
processing_time_ms: float            # Processing time in milliseconds
metadata: Dict[str, Any]             # Additional metadata
```

#### TokenUsage

Token usage tracking.

**Attributes:**
```python
prompt_tokens: int       # Tokens in prompt
completion_tokens: int   # Tokens in response
total_tokens: int        # Total tokens used
```

**Methods:**
```python
def to_dict(self) -> Dict[str, int]
```

#### Entity

Extracted entity with confidence scoring.

**Attributes:**
```python
name: str                          # Entity name/identifier
type: str                          # Entity type
properties: Dict[str, Any]          # Additional properties
confidence: float                  # Confidence score (0.0-1.0)
source_text: str                   # Source text that generated this entity
```

#### Relation

Extracted relation with confidence scoring.

**Attributes:**
```python
source: str                        # Source entity name/ID
target: str                        # Target entity name/ID
type: str                          # Relation type
properties: Dict[str, Any]         # Additional properties
confidence: float                  # Confidence score (0.0-1.0)
source_text: str                   # Source text that generated this relation
```

#### ExtractionResult

Complete extraction result.

**Attributes:**
```python
entities: List[Entity]             # Extracted entities
relations: List[Relation]          # Extracted relations
source_document: str                # Source document identifier
processing_metadata: Dict[str, Any] # Processing metadata
```

**Methods:**
```python
def get_entities_by_type(self, entity_type: str) -> List[Entity]
def get_entities_by_confidence(self, min_confidence: float = 0.7) -> List[Entity]
def get_relations_by_type(self, relation_type: str) -> List[Relation]
def to_kg_format(self) -> Dict[str, List[Dict[str, Any]]]
```

---

## Constants and Enums

### Entity Types

```python
from src.llm.chains import ENTITY_TYPES

# Available entity types and their schemas
print(ENTITY_TYPES["BugReport"])
# {
#     "description": "Software bug or issue report",
#     "required": ["bug_id", "title", "description", "status", "severity"],
#     "optional": ["priority", "product", "version", "platform", ...]
# }
```

### Relation Types

```python
from src.llm.chains import RELATION_TYPES

# Available relation types and their descriptions
for name, desc in RELATION_TYPES.items():
    print(f"{name}: {desc}")
```

---

## Error Handling

All modules provide comprehensive error handling:

```python
# Extraction errors
from src.extraction import GLMOCRClientError, GLMOCRServerError, GLMOCRConnectionError

try:
    text = extract_ocr("image.png")
except GLMOCRConnectionError as e:
    print(f"Connection failed: {e}")
except GLMOCRServerError as e:
    print(f"Server error: {e}")

# Knowledge graph errors
from neo4j.exceptions import ServiceUnavailable, AuthError

try:
    client.connect()
except ServiceUnavailable:
    print("Neo4j server not running. Start with: docker-compose up -d neo4j")
except AuthError:
    print("Authentication failed. Check credentials in config/neo4j.yaml")

# LLM errors
from src.llm import get_client

try:
    client = get_client("claude")
    client.switch_provider("openai")
except ValueError as e:
    print(f"Provider error: {e}")
except ImportError as e:
    print(f"Missing dependency: {e}")
```

---

## Configuration Files

### Extraction Configuration

`config/extraction.yaml`:
```yaml
extraction:
  pdf_dpi: 200
  native_threshold: 0.8
  
page_loader:
  max_tokens: 4096
  temperature: 0.7
```

### LLM Configuration

`config/llm.yaml`:
```yaml
providers:
  ollama:
    enabled: true
    base_url: http://localhost:11434
    model: llama3.2:3b
    temperature: 0.7
    max_tokens: 4096
  
  claude:
    enabled: true
    api_key: ${ANTHROPIC_API_KEY}
    model: claude-3-sonnet-20240229
    temperature: 0.7
    max_tokens: 4096

default_provider: ollama
```

### Neo4j Configuration

`config/neo4j.yaml`:
```yaml
connection:
  uri: bolt://localhost:7687
  username: neo4j
  password: ${NEO4J_PASSWORD:-password}
  max_connection_pool_size: 50
  connection_timeout: 30

schema:
  constraints:
    - CREATE CONSTRAINT bug_id_unique IF NOT EXISTS FOR (n:BugReport) REQUIRE n.id IS UNIQUE
  indexes:
    - CREATE INDEX component_name_idx IF NOT EXISTS FOR (n:Component) ON (n.name)
```

---

## Quick Reference

### Import All Major APIs

```python
# Extraction
from src.extraction import (
    extract_native,
    extract_ocr,
    BatchProcessor,
    CheckpointManager,
    GLMOCRClientError,
)

# Evaluation
from src.evaluation import (
    calculate_cer,
    calculate_wer,
    calculate_all_metrics,
    Benchmark,
    print_comparison_table,
)

# Knowledge Graph
from src.kg import (
    Neo4jClient,
    BulkImporter,
    get_entity_schema,
    get_relation_schema,
    get_cypher_merge_node,
    get_cypher_merge_relation,
)

# LLM
from src.llm import (
    UnifiedLLMClient,
    EntityExtractionChain,
    get_client,
    extract_entities,
    LLMResponse,
    TokenUsage,
)
```

### Common Workflows

**Process PDFs and save results:**
```python
from src.extraction import BatchProcessor

processor = BatchProcessor(
    output_dir="data/processed",
    checkpoint_path="data/processed/checkpoint.json",
    project_name="my_batch"
)
results = processor.process_batch(["doc1.pdf", "doc2.pdf"])
```

**Extract entities and import to Neo4j:**
```python
from src.llm import EntityExtractionChain, get_client
from src.kg import BulkImporter, get_client as get_kg_client

llm_client = get_client()
kg_client = get_kg_client()
kg_client.connect()

chain = EntityExtractionChain(llm_client)
importer = BulkImporter(kg_client)

result = chain.extract(text="Bug 123: ...")
importer.import_extraction_result(result)
```

**Benchmark extraction methods:**
```python
from src.evaluation import Benchmark

benchmark = Benchmark()
results = benchmark.run_ablation(
    pdf_paths=["doc1.pdf"],
    method='native',
    extract_fn=custom_extract
)
```

---

**Version:** 1.0  
**Last Updated:** March 18, 2026
