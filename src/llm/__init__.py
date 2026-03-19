"""LLM Integration Package.

Provides unified LLM client supporting multiple providers (Ollama, Claude, OpenAI, Gemini)
with runtime provider switching and token tracking.

Main exports:
    - UnifiedLLMClient: Main client for interacting with LLMs
    - get_client: Get singleton client instance
    - LLMResponse: Standardized response format
    - TokenUsage: Token tracking
    
Entity Extraction:
    - EntityExtractionChain: Chain for extracting entities and relations
    - ExtractionResult: Structured extraction result
    - Entity: Entity model with confidence
    - Relation: Relation model with confidence
    - extract_entities: Convenience function for extraction
    
Configuration:
    - get_config: Load LLM configuration
    - LLMConfig: Configuration container
    - ProviderConfig: Provider-specific settings

Example usage:
    >>> from src.llm import get_client, EntityExtractionChain
    >>> 
    >>> # Initialize client with default provider
    >>> client = get_client()
    >>> 
    >>> # Switch providers at runtime
    >>> client.switch_provider("claude")
    >>> 
    >>> # Get token usage
    >>> response = client.chat_text("Hello, world!")
    >>> print(f"Tokens used: {response.token_usage.total_tokens}")
    >>> 
    >>> # Extract entities
    >>> chain = EntityExtractionChain(client)
    >>> result = chain.extract(text="Bug 123456...", document_id="bug123")
    >>> print(f"Found {len(result.entities)} entities")
"""

# Client imports
from src.llm.client import (
    UnifiedLLMClient,
    LLMResponse,
    TokenUsage,
    get_client,
    reset_client,
)

# Extraction imports
from src.llm.chains import (
    EntityExtractionChain,
    ExtractionResult,
    Entity,
    Relation,
    extract_entities,
    ENTITY_TYPES,
    RELATION_TYPES,
)

# Config imports
from src.llm.config import (
    LLMConfig,
    ProviderConfig,
    ExtractionConfig,
    get_config,
    reload_config,
)

__all__ = [
    # Client
    "UnifiedLLMClient",
    "LLMResponse",
    "TokenUsage",
    "get_client",
    "reset_client",
    # Extraction
    "EntityExtractionChain",
    "ExtractionResult",
    "Entity",
    "Relation",
    "extract_entities",
    "ENTITY_TYPES",
    "RELATION_TYPES",
    # Config
    "LLMConfig",
    "ProviderConfig",
    "ExtractionConfig",
    "get_config",
    "reload_config",
]
