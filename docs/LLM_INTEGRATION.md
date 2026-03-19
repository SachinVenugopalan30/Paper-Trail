# LLM Integration Documentation

Comprehensive guide for the multi-provider LLM architecture with unified interface, runtime provider switching, and entity extraction capabilities.

## Table of Contents

1. [Multi-Provider LLM Architecture](#multi-provider-llm-architecture)
2. [Configuration](#configuration)
3. [Key Components](#key-components)
4. [Provider Implementations](#provider-implementations)
5. [Token Usage Tracking](#token-usage-tracking)
6. [Entity Extraction](#entity-extraction)
7. [Runtime Provider Switching](#runtime-provider-switching)
8. [API Examples](#api-examples)
9. [Key Files](#key-files)
10. [Usage Patterns](#usage-patterns)

---

## Multi-Provider LLM Architecture

The system provides a unified interface for multiple LLM providers with seamless runtime switching capabilities.

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    UnifiedLLMClient                        │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │   Ollama     │  │    Claude    │  │    OpenAI    │        │
│  │  Provider    │  │   Provider   │  │   Provider   │        │
│  └──────────────┘  └──────────────┘  └──────────────┘        │
│  ┌──────────────┐                                            │
│  │    Gemini    │                                            │
│  │  Provider    │                                            │
│  └──────────────┘                                            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │  Token Tracking  │
                    │  Streaming API   │
                    └──────────────────┘
```

### Design Principles

- **Unified Interface**: Single API for all providers
- **Runtime Switching**: Change providers without code changes
- **Token Tracking**: Monitor usage across all providers
- **Streaming Support**: Real-time response streaming
- **Fallback Mechanisms**: Graceful degradation

---

## Configuration

### config/llm.yaml

```yaml
llm:
  # Default provider selection
  default_provider: ollama
  
  # Provider configurations
  providers:
    ollama:
      model: llama3.2:3b
      base_url: http://localhost:11434
      timeout: 30
      temperature: 0.7
      max_tokens: 2048
    
    claude:
      model: claude-3-sonnet-20240229
      temperature: 0.7
      max_tokens: 4096
      timeout: 60
    
    openai:
      model: gpt-4-turbo-preview
      temperature: 0.7
      max_tokens: 4096
      timeout: 60
    
    gemini:
      model: gemini-pro
      temperature: 0.7
      max_tokens: 4096
      timeout: 60
  
  # Entity extraction settings
  entity_extraction:
    confidence_threshold: 0.6
    max_entities_per_page: 100
    max_relations_per_page: 150
```

### Environment Variables

```bash
# Required API Keys
export ANTHROPIC_API_KEY=your_claude_api_key_here
export OPENAI_API_KEY=your_openai_api_key_here
export GOOGLE_API_KEY=your_gemini_api_key_here

# Optional: Override default provider
export DEFAULT_LLM_PROVIDER=claude

# Optional: Ollama configuration
export OLLAMA_BASE_URL=http://localhost:11434
export OLLAMA_MODEL=llama3.2:3b
```

---

## Key Components

### UnifiedLLMClient (src/llm/client.py)

The main entry point for LLM interactions providing a unified interface.

```python
from src.llm import get_client

# Get singleton client instance
client = get_client()

# Basic chat completion
response = await client.chat(
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is entity extraction?"}
    ]
)

print(response.content)
print(f"Tokens used: {response.usage.total_tokens}")
```

**Key Features:**

- **Provider Switching**: Runtime provider changes
- **Token Tracking**: Automatic per-request tracking
- **Streaming Support**: Async streaming responses
- **Error Handling**: Graceful fallbacks

**Methods:**

| Method | Description |
|--------|-------------|
| `chat()` | Synchronous chat completion |
| `chat_stream()` | Streaming chat completion |
| `switch_provider()` | Change active provider |
| `get_usage()` | Get token usage statistics |
| `extract_entities()` | Structured entity extraction |

### EntityExtractionChain (src/llm/chains.py)

Specialized chain for extracting structured entities from text using Pydantic models.

```python
from src.llm.chains import EntityExtractionChain

chain = EntityExtractionChain(client)

# Extract entities from text
entities = await chain.extract(
    text="John works at Google in Mountain View. He leads the AI team.",
    entity_types=["PERSON", "ORGANIZATION", "LOCATION"]
)

# Access structured results
for entity in entities:
    print(f"{entity.type}: {entity.text} (confidence: {entity.confidence:.2f})")
```

**Features:**

- **Pydantic Models**: Type-safe entity definitions
- **Confidence Scoring**: Reliability metrics (0.0 - 1.0)
- **Fallback Extraction**: Regex-based backup extraction
- **10 Entity Types**: Comprehensive entity taxonomy
- **15 Relation Types**: Relationship extraction

### LLMConfig (src/llm/config.py)

Configuration management with YAML loading and environment variable substitution.

```python
from src.llm.config import LLMConfig

# Load configuration
config = LLMConfig.from_yaml("config/llm.yaml")

# Access provider settings
ollama_settings = config.get_provider_config("ollama")
print(ollama_settings.model)  # "llama3.2:3b"

# Environment variable substitution
api_key = config.get_env("ANTHROPIC_API_KEY")
```

**Capabilities:**

- **YAML Loading**: Structured configuration files
- **Environment Substitution**: `${VAR_NAME}` syntax support
- **Validation**: Schema validation for settings
- **Hot Reloading**: Runtime configuration updates

---

## Provider Implementations

### OllamaProvider - Local Inference

```python
from src.llm.providers import OllamaProvider

provider = OllamaProvider(
    model="llama3.2:3b",
    base_url="http://localhost:11434"
)

# Local inference - no API key required
response = await provider.chat(messages=[...])
```

**Characteristics:**
- **Local Execution**: Runs on local machine
- **No API Costs**: Free inference
- **Privacy**: Data never leaves machine
- **Models**: llama3.2:3b, mistral, codellama, etc.

### ClaudeProvider - Anthropic API

```python
from src.llm.providers import ClaudeProvider

provider = ClaudeProvider(
    model="claude-3-sonnet-20240229",
    api_key=os.environ["ANTHROPIC_API_KEY"]
)

# High-quality responses
response = await provider.chat(messages=[...])
```

**Characteristics:**
- **High Quality**: State-of-the-art reasoning
- **Large Context**: Up to 200K tokens
- **Vision**: Image understanding capabilities
- **Models**: claude-3-opus, claude-3-sonnet, claude-3-haiku

### OpenAIProvider - OpenAI API

```python
from src.llm.providers import OpenAIProvider

provider = OpenAIProvider(
    model="gpt-4-turbo-preview",
    api_key=os.environ["OPENAI_API_KEY"]
)

# GPT-4 level performance
response = await provider.chat(messages=[...])
```

**Characteristics:**
- **Proven Reliability**: Production-ready
- **Function Calling**: Tool use capabilities
- **JSON Mode**: Structured output support
- **Models**: gpt-4, gpt-4-turbo, gpt-3.5-turbo

### GeminiProvider - Google API

```python
from src.llm.providers import GeminiProvider

provider = GeminiProvider(
    model="gemini-pro",
    api_key=os.environ["GOOGLE_API_KEY"]
)

# Google's latest models
response = await provider.chat(messages=[...])
```

**Characteristics:**
- **Multimodal**: Text, image, video understanding
- **Long Context**: 1M+ token context window
- **Fast Inference**: Optimized for speed
- **Models**: gemini-pro, gemini-pro-vision, gemini-ultra

---

## Token Usage Tracking

### TokenUsage Dataclass

```python
from src.llm.types import TokenUsage

usage = TokenUsage(
    prompt_tokens=150,
    completion_tokens=75,
    total_tokens=225
)

print(f"Cost estimate: ${usage.total_tokens * 0.00001:.4f}")
```

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `prompt_tokens` | int | Tokens in the input |
| `completion_tokens` | int | Tokens in the output |
| `total_tokens` | int | Total tokens used |

### Per-Request Tracking

```python
from src.llm import get_client

client = get_client()

# Track usage automatically
response = await client.chat(messages=[...])

# Access usage from response
usage = response.usage
print(f"Prompt: {usage.prompt_tokens}")
print(f"Completion: {usage.completion_tokens}")
print(f"Total: {usage.total_tokens}")

# Get cumulative usage
total_usage = client.get_usage()
print(f"Session total: {total_usage.total_tokens}")
```

### Display in UI

```python
# Gradio UI integration
import gradio as gr

async def chat_with_tracking(message, history):
    response = await client.chat(messages=[...])
    
    # Format usage for display
    usage_text = f"📊 Tokens: {response.usage.total_tokens} " \
                 f"(↑{response.usage.prompt_tokens} ↓{response.usage.completion_tokens})"
    
    return response.content, usage_text

# Display usage alongside response
gr.ChatInterface(
    chat_with_tracking,
    additional_outputs=[gr.Textbox(label="Token Usage")]
)
```

### LLMResponse Metadata

```python
from src.llm.types import LLMResponse

response = LLMResponse(
    content="Hello, world!",
    usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    model="claude-3-sonnet-20240229",
    provider="claude",
    latency_ms=850,
    timestamp=datetime.now()
)

# Access metadata
print(f"Model: {response.model}")
print(f"Provider: {response.provider}")
print(f"Latency: {response.latency_ms}ms")
```

---

## Entity Extraction

### 10 Entity Types

| Type | Description | Examples |
|------|-------------|----------|
| `PERSON` | Human names | "John Smith", "Marie Curie" |
| `ORGANIZATION` | Companies, institutions | "Google", "MIT" |
| `LOCATION` | Geographic places | "Mountain View", "Paris" |
| `DATE` | Temporal references | "January 15, 2024", "Q3 2023" |
| `MONEY` | Monetary values | "$50 million", "€100" |
| `PERCENT` | Percentage values | "25%", "fifty percent" |
| `PRODUCT` | Product names | "iPhone 15", "ChatGPT" |
| `EVENT` | Named events | "WWDC 2024", "COP29" |
| `TECHNOLOGY` | Technical terms | "machine learning", "Kubernetes" |
| `CONCEPT` | Abstract concepts | "inflation", "democracy" |

### 15 Relation Types

| Relation | Description | Example |
|----------|-------------|---------|
| `WORKS_AT` | Employment | "John works at Google" |
| `LOCATED_IN` | Geographic | "Google in Mountain View" |
| `FOUNDED_BY` | Founder relationship | "SpaceX founded by Elon" |
| `ACQUIRED` | Acquisition | "Google acquired YouTube" |
| `PARTNER` | Partnership | "Microsoft and OpenAI partner" |
| `COMPETE` | Competition | "AWS competes with Azure" |
| `INVESTED_IN` | Investment | "Sequoia invested in Stripe" |
| `PRODUCES` | Production | "Apple produces iPhone" |
| `LEADS` | Leadership | "CEO leads company" |
| `STUDIED_AT` | Education | "studied at Stanford" |
| `ALIAS` | Alternative name | "Alphabet, formerly Google" |
| `SUBSIDIARY` | Parent-child | "YouTube subsidiary of Google" |
| `SUPPLIER` | Supply chain | "TSMC supplier to Apple" |
| `CUSTOMER` | Customer relationship | "Netflix customer of AWS" |
| `PART_OF` | Membership | "California part of USA" |

### Confidence Threshold: 0.6

```python
# Only entities with confidence >= 0.6 are included
entities = await chain.extract(
    text=page_text,
    min_confidence=0.6  # Configurable threshold
)

# Filter by confidence
high_confidence = [e for e in entities if e.confidence >= 0.8]
medium_confidence = [e for e in entities if 0.6 <= e.confidence < 0.8]
```

### Per-Page Extraction

```python
from src.llm.chains import EntityExtractionChain

chain = EntityExtractionChain(client)

# Process each page independently
for page_num, page_text in enumerate(document_pages):
    entities = await chain.extract(
        text=page_text,
        page_number=page_num,
        max_entities=100,  # Per-page limit
        max_relations=150
    )
    
    # Merge with global entity list
    all_entities.extend(entities)
```

### Structured Output with Pydantic

```python
from pydantic import BaseModel
from typing import List, Optional

class Entity(BaseModel):
    id: str
    type: str
    text: str
    start_pos: int
    end_pos: int
    confidence: float
    page_number: int
    metadata: Optional[dict] = None

class Relation(BaseModel):
    source_id: str
    target_id: str
    relation_type: str
    confidence: float
    evidence: Optional[str] = None

class ExtractionResult(BaseModel):
    entities: List[Entity]
    relations: List[Relation]
    processing_time_ms: float
    model_version: str
```

---

## Runtime Provider Switching

### Basic Switching

```python
from src.llm import get_client

client = get_client()

# Switch to Claude
client.switch_provider("claude")
response = await client.chat(messages=[...])

# Switch to OpenAI
client.switch_provider("openai")
response = await client.chat(messages=[...])

# Switch to Ollama (local)
client.switch_provider("ollama")
response = await client.chat(messages=[...])
```

### Config-Driven Switching

```python
# Switch with custom configuration
client.switch_provider("claude", config_override={
    "model": "claude-3-opus-20240229",
    "temperature": 0.5,
    "max_tokens": 8192
})
```

### Fallback Behavior

```python
# Automatic fallback on failure
client = get_client(fallback_enabled=True)

# If Claude fails, automatically tries OpenAI, then Gemini, then Ollama
response = await client.chat_with_fallback(
    messages=[...],
    preferred_order=["claude", "openai", "gemini", "ollama"]
)
```

### Provider Comparison

```python
async def compare_providers(prompt: str):
    client = get_client()
    results = {}
    
    for provider in ["ollama", "claude", "openai", "gemini"]:
        client.switch_provider(provider)
        
        start = time.time()
        response = await client.chat(messages=[
            {"role": "user", "content": prompt}
        ])
        latency = (time.time() - start) * 1000
        
        results[provider] = {
            "content": response.content,
            "latency_ms": latency,
            "tokens": response.usage.total_tokens
        }
    
    return results
```

---

## API Examples

### Chat Completion

```python
from src.llm import get_client

client = get_client()

# Simple completion
response = await client.chat(
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Explain entity extraction."}
    ],
    temperature=0.7,
    max_tokens=500
)

print(response.content)
```

### Streaming Responses

```python
# Streaming for real-time display
async for chunk in client.chat_stream(
    messages=[{"role": "user", "content": "Write a story about AI."}]
):
    print(chunk.content, end="", flush=True)
    
    # Access usage after stream completes
    if chunk.is_final:
        print(f"\nTotal tokens: {chunk.usage.total_tokens}")
```

### Entity Extraction

```python
from src.llm.chains import EntityExtractionChain

chain = EntityExtractionChain(client)

# Extract from text
text = """
Apple Inc. is planning to open a new office in Austin, Texas. 
Tim Cook, the CEO, announced the expansion at WWDC 2024.
"""

result = await chain.extract(text)

# Process entities
for entity in result.entities:
    print(f"Entity: {entity.text} ({entity.type})")
    
# Process relations
for relation in result.relations:
    source = next(e for e in result.entities if e.id == relation.source_id)
    target = next(e for e in result.entities if e.id == relation.target_id)
    print(f"Relation: {source.text} --{relation.relation_type}--> {target.text}")
```

### Token Usage Retrieval

```python
# Get current session usage
usage = client.get_usage()
print(f"Session tokens: {usage.total_tokens}")

# Reset usage tracking
client.reset_usage()

# Get usage breakdown by provider
breakdown = client.get_usage_by_provider()
for provider, usage in breakdown.items():
    print(f"{provider}: {usage.total_tokens} tokens")
```

---

## Key Files

### src/llm/__init__.py

Entry point and public API exports.

```python
from src.llm import get_client, LLMResponse, TokenUsage

# Main exports:
# - get_client(): Returns singleton UnifiedLLMClient
# - LLMResponse: Response dataclass
# - TokenUsage: Usage tracking dataclass
```

### src/llm/client.py

Core client implementation with provider management.

**Key Classes:**
- `UnifiedLLMClient`: Main client class
- `ProviderRegistry`: Provider factory and registry

### src/llm/chains.py

Specialized chains for entity extraction and other tasks.

**Key Classes:**
- `EntityExtractionChain`: Structured entity extraction
- `SummarizationChain`: Document summarization
- `ClassificationChain`: Text classification

### src/llm/config.py

Configuration management and validation.

**Key Classes:**
- `LLMConfig`: Configuration loader
- `ProviderConfig`: Provider-specific settings
- `EntityExtractionConfig`: Extraction parameters

---

## Usage Patterns

### Basic Chat

```python
from src.llm import get_client

async def basic_chat():
    client = get_client()
    
    response = await client.chat(
        messages=[
            {"role": "user", "content": "What is machine learning?"}
        ]
    )
    
    return response.content
```

### Entity Extraction

```python
from src.llm import get_client
from src.llm.chains import EntityExtractionChain

async def extract_from_document(text: str):
    client = get_client()
    chain = EntityExtractionChain(client)
    
    # Extract entities
    result = await chain.extract(text)
    
    # Return structured data
    return {
        "entities": [e.dict() for e in result.entities],
        "relations": [r.dict() for r in result.relations],
        "usage": result.usage.total_tokens
    }
```

### Provider Comparison

```python
async def benchmark_providers(test_prompts: List[str]):
    client = get_client()
    results = []
    
    for provider in ["ollama", "claude", "openai", "gemini"]:
        client.switch_provider(provider)
        
        provider_results = []
        for prompt in test_prompts:
            start = time.time()
            response = await client.chat(messages=[
                {"role": "user", "content": prompt}
            ])
            latency = time.time() - start
            
            provider_results.append({
                "latency": latency,
                "tokens": response.usage.total_tokens,
                "content_length": len(response.content)
            })
        
        results.append({
            "provider": provider,
            "avg_latency": sum(r["latency"] for r in provider_results) / len(provider_results),
            "avg_tokens": sum(r["tokens"] for r in provider_results) / len(provider_results)
        })
    
    return results
```

### Token Tracking

```python
class TokenTracker:
    def __init__(self):
        self.client = get_client()
        self.history = []
    
    async def tracked_chat(self, messages):
        response = await self.client.chat(messages=messages)
        
        # Record usage
        self.history.append({
            "timestamp": datetime.now(),
            "tokens": response.usage.total_tokens,
            "provider": response.provider,
            "model": response.model
        })
        
        return response
    
    def get_daily_usage(self, date: datetime) -> int:
        return sum(
            h["tokens"] 
            for h in self.history 
            if h["timestamp"].date() == date.date()
        )
    
    def get_cost_estimate(self, rate_per_1k: float = 0.03) -> float:
        total_tokens = sum(h["tokens"] for h in self.history)
        return (total_tokens / 1000) * rate_per_1k
```

---

## Best Practices

1. **Use Ollama for Development**: Local inference is free and fast for testing
2. **Switch to Cloud for Production**: Use Claude/OpenAI for production workloads
3. **Monitor Token Usage**: Track usage to manage costs
4. **Set Confidence Thresholds**: Adjust based on your precision/recall needs
5. **Use Streaming for UX**: Stream responses for better user experience
6. **Implement Fallbacks**: Configure fallback providers for reliability
7. **Cache Results**: Cache entity extractions for repeated queries

---

## Troubleshooting

### Common Issues

**Ollama Connection Failed**
```bash
# Ensure Ollama is running
curl http://localhost:11434/api/tags

# Pull required model
ollama pull llama3.2:3b
```

**API Key Errors**
```bash
# Verify environment variables
echo $ANTHROPIC_API_KEY
echo $OPENAI_API_KEY
echo $GOOGLE_API_KEY
```

**Provider Not Found**
```python
# Check available providers
from src.llm.client import ProviderRegistry
print(ProviderRegistry.list_providers())
```

---

## Additional Resources

- [Ollama Documentation](https://ollama.ai)
- [Anthropic API Docs](https://docs.anthropic.com)
- [OpenAI API Docs](https://platform.openai.com)
- [Google Gemini Docs](https://ai.google.dev)
