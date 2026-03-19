"""Unified LLM Client Module.

Provides a single interface for multiple LLM providers (Ollama, Claude, OpenAI, Gemini)
with runtime provider switching and token tracking.
"""

import logging
from typing import Dict, Any, Optional, List, Callable, Generator
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
import time

# LangChain imports
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage, BaseMessage
from langchain_core.outputs import ChatResult

# Provider-specific imports (lazy loaded to avoid import errors)
try:
    from langchain_anthropic import ChatAnthropic
except ImportError:
    ChatAnthropic = None

try:
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatOpenAI = None

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except ImportError:
    ChatGoogleGenerativeAI = None

try:
    from langchain_ollama import ChatOllama
except ImportError:
    ChatOllama = None

from src.llm.config import get_config, LLMConfig, ProviderConfig

logger = logging.getLogger(__name__)


@dataclass
class TokenUsage:
    """Token usage tracking."""
    
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    
    def to_dict(self) -> Dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass
class LLMResponse:
    """Standardized LLM response."""
    
    content: str
    provider: str
    model: str
    token_usage: TokenUsage
    processing_time_ms: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "provider": self.provider,
            "model": self.model,
            "token_usage": self.token_usage.to_dict(),
            "processing_time_ms": self.processing_time_ms,
            "metadata": self.metadata,
        }


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    def chat(self, messages: List[BaseMessage], **kwargs) -> LLMResponse:
        """Send chat messages and return response."""
        pass
    
    @abstractmethod
    def stream(self, messages: List[BaseMessage], **kwargs) -> Generator[str, None, None]:
        """Stream response tokens."""
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """Return provider name."""
        pass


class OllamaProvider(LLMProvider):
    """Ollama provider implementation."""
    
    def __init__(self, config: ProviderConfig):
        if ChatOllama is None:
            raise ImportError("langchain-ollama not installed. Run: pip install langchain-ollama")
        
        self.config = config
        self.client = ChatOllama(
            base_url=config.base_url or "http://localhost:11434",
            model=config.model,
            temperature=config.temperature,
            num_predict=config.max_tokens,
        )
        
    def chat(self, messages: List[BaseMessage], **kwargs) -> LLMResponse:
        start_time = time.time()
        
        response = self.client.invoke(messages, **kwargs)
        content = response.content if hasattr(response, 'content') else str(response)
        
        # Ollama doesn't provide token counts, estimate
        prompt_text = "\n".join([m.content for m in messages if hasattr(m, 'content')])
        estimated_prompt_tokens = len(prompt_text) // 4
        estimated_completion_tokens = len(content) // 4
        
        processing_time = (time.time() - start_time) * 1000
        
        return LLMResponse(
            content=content,
            provider="ollama",
            model=self.config.model,
            token_usage=TokenUsage(
                prompt_tokens=estimated_prompt_tokens,
                completion_tokens=estimated_completion_tokens,
                total_tokens=estimated_prompt_tokens + estimated_completion_tokens,
            ),
            processing_time_ms=processing_time,
        )
    
    def stream(self, messages: List[BaseMessage], **kwargs) -> Generator[str, None, None]:
        for chunk in self.client.stream(messages, **kwargs):
            yield chunk.content if hasattr(chunk, 'content') else str(chunk)
    
    def get_name(self) -> str:
        return "ollama"


class ClaudeProvider(LLMProvider):
    """Anthropic Claude provider implementation."""
    
    def __init__(self, config: ProviderConfig):
        if ChatAnthropic is None:
            raise ImportError("langchain-anthropic not installed. Run: pip install langchain-anthropic")
        
        api_key = config.get_api_key()
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
            
        self.config = config
        self.client = ChatAnthropic(
            api_key=api_key,
            model=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )
        
    def chat(self, messages: List[BaseMessage], **kwargs) -> LLMResponse:
        start_time = time.time()
        
        response = self.client.invoke(messages, **kwargs)
        content = response.content
        
        # Extract token usage if available
        usage = TokenUsage()
        if hasattr(response, 'usage_metadata'):
            meta = response.usage_metadata
            usage.prompt_tokens = meta.get('input_tokens', 0)
            usage.completion_tokens = meta.get('output_tokens', 0)
            usage.total_tokens = usage.prompt_tokens + usage.completion_tokens
        
        processing_time = (time.time() - start_time) * 1000
        
        return LLMResponse(
            content=content,
            provider="claude",
            model=self.config.model,
            token_usage=usage,
            processing_time_ms=processing_time,
        )
    
    def stream(self, messages: List[BaseMessage], **kwargs) -> Generator[str, None, None]:
        for chunk in self.client.stream(messages, **kwargs):
            yield chunk.content if hasattr(chunk, 'content') else str(chunk)
    
    def get_name(self) -> str:
        return "claude"


class OpenAIProvider(LLMProvider):
    """OpenAI provider implementation."""
    
    def __init__(self, config: ProviderConfig):
        if ChatOpenAI is None:
            raise ImportError("langchain-openai not installed. Run: pip install langchain-openai")
        
        api_key = config.get_api_key()
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")
            
        self.config = config
        self.client = ChatOpenAI(
            api_key=api_key,
            model=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )
        
    def chat(self, messages: List[BaseMessage], **kwargs) -> LLMResponse:
        start_time = time.time()
        
        response = self.client.invoke(messages, **kwargs)
        content = response.content
        
        # Extract token usage
        usage = TokenUsage()
        if hasattr(response, 'usage_metadata'):
            meta = response.usage_metadata
            usage.prompt_tokens = meta.get('input_tokens', 0)
            usage.completion_tokens = meta.get('output_tokens', 0)
            usage.total_tokens = meta.get('total_tokens', 0)
        
        processing_time = (time.time() - start_time) * 1000
        
        return LLMResponse(
            content=content,
            provider="openai",
            model=self.config.model,
            token_usage=usage,
            processing_time_ms=processing_time,
        )
    
    def stream(self, messages: List[BaseMessage], **kwargs) -> Generator[str, None, None]:
        for chunk in self.client.stream(messages, **kwargs):
            yield chunk.content if hasattr(chunk, 'content') else str(chunk)
    
    def get_name(self) -> str:
        return "openai"


class GeminiProvider(LLMProvider):
    """Google Gemini provider implementation."""
    
    def __init__(self, config: ProviderConfig):
        if ChatGoogleGenerativeAI is None:
            raise ImportError("langchain-google-genai not installed. Run: pip install langchain-google-genai")
        
        api_key = config.get_api_key()
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set")
            
        self.config = config
        self.client = ChatGoogleGenerativeAI(
            api_key=api_key,
            model=config.model,
            temperature=config.temperature,
            max_output_tokens=config.max_tokens,
        )
        
    def chat(self, messages: List[BaseMessage], **kwargs) -> LLMResponse:
        start_time = time.time()
        
        response = self.client.invoke(messages, **kwargs)
        content = response.content
        
        # Extract token usage if available
        usage = TokenUsage()
        if hasattr(response, 'usage_metadata'):
            meta = response.usage_metadata
            usage.prompt_tokens = meta.get('prompt_token_count', 0)
            usage.completion_tokens = meta.get('candidates_token_count', 0)
            usage.total_tokens = meta.get('total_token_count', 0)
        
        processing_time = (time.time() - start_time) * 1000
        
        return LLMResponse(
            content=content,
            provider="gemini",
            model=self.config.model,
            token_usage=usage,
            processing_time_ms=processing_time,
        )
    
    def stream(self, messages: List[BaseMessage], **kwargs) -> Generator[str, None, None]:
        for chunk in self.client.stream(messages, **kwargs):
            yield chunk.content if hasattr(chunk, 'content') else str(chunk)
    
    def get_name(self) -> str:
        return "gemini"


class VLLMProvider(LLMProvider):
    """vLLM provider - uses OpenAI-compatible API."""

    def __init__(self, config: ProviderConfig):
        if ChatOpenAI is None:
            raise ImportError("langchain-openai not installed. Run: pip install langchain-openai")
        self.config = config
        self.client = ChatOpenAI(
            base_url=config.base_url or "http://localhost:8000/v1",
            api_key=config.get_api_key() or "not-needed",
            model=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )

    def chat(self, messages: List[BaseMessage], **kwargs) -> LLMResponse:
        start_time = time.time()

        response = self.client.invoke(messages, **kwargs)
        content = response.content

        usage = TokenUsage()
        if hasattr(response, 'usage_metadata'):
            meta = response.usage_metadata
            usage.prompt_tokens = meta.get('input_tokens', 0)
            usage.completion_tokens = meta.get('output_tokens', 0)
            usage.total_tokens = meta.get('total_tokens', usage.prompt_tokens + usage.completion_tokens)

        processing_time = (time.time() - start_time) * 1000

        return LLMResponse(
            content=content,
            provider="vllm",
            model=self.config.model,
            token_usage=usage,
            processing_time_ms=processing_time,
        )

    def stream(self, messages: List[BaseMessage], **kwargs) -> Generator[str, None, None]:
        for chunk in self.client.stream(messages, **kwargs):
            yield chunk.content if hasattr(chunk, 'content') else str(chunk)

    def get_name(self) -> str:
        return "vllm"


class UnifiedLLMClient:
    """Unified LLM client supporting multiple providers with runtime switching."""

    _providers: Dict[str, Callable[[ProviderConfig], LLMProvider]] = {
        "ollama": OllamaProvider,
        "claude": ClaudeProvider,
        "openai": OpenAIProvider,
        "gemini": GeminiProvider,
        "vllm": VLLMProvider,
    }
    
    def __init__(self, provider_name: Optional[str] = None, config_path: Optional[str] = None):
        """Initialize unified LLM client.
        
        Args:
            provider_name: Provider to use. If None, uses config default.
            config_path: Path to LLM config file.
        """
        self.config = get_config(config_path)
        self._active_provider: Optional[LLMProvider] = None
        self._provider_name: Optional[str] = None
        
        # Initialize with specified or default provider
        self.switch_provider(provider_name or self.config.default_provider)
    
    def switch_provider(self, provider_name: str) -> None:
        """Switch to a different LLM provider at runtime.
        
        Args:
            provider_name: Name of provider to switch to.
            
        Raises:
            ValueError: If provider not found or not enabled.
        """
        provider_config = self.config.get_provider_config(provider_name)
        
        if not provider_config:
            raise ValueError(f"Provider '{provider_name}' not found in config")
        
        if not provider_config.enabled:
            raise ValueError(f"Provider '{provider_name}' is not enabled")
        
        provider_class = self._providers.get(provider_name)
        if not provider_class:
            raise ValueError(f"Unknown provider: {provider_name}")
        
        try:
            self._active_provider = provider_class(provider_config)
            self._provider_name = provider_name
            logger.info(f"Switched to provider: {provider_name}")
        except (ImportError, ValueError) as e:
            logger.error(f"Failed to initialize provider '{provider_name}': {e}")
            raise
    
    def get_available_providers(self) -> List[str]:
        """Get list of available (enabled) providers."""
        return self.config.get_enabled_providers()
    
    def get_current_provider(self) -> str:
        """Get name of current provider."""
        return self._provider_name or "unknown"
    
    def chat(self, messages: List[BaseMessage], **kwargs) -> LLMResponse:
        """Send chat messages.
        
        Args:
            messages: List of LangChain messages.
            **kwargs: Additional arguments for the provider.
            
        Returns:
            LLMResponse with standardized format.
        """
        if not self._active_provider:
            raise RuntimeError("No provider selected. Call switch_provider() first.")
        
        return self._active_provider.chat(messages, **kwargs)
    
    def chat_text(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> LLMResponse:
        """Send text prompt (convenience method).
        
        Args:
            prompt: User prompt text.
            system_prompt: Optional system prompt.
            **kwargs: Additional arguments.
            
        Returns:
            LLMResponse.
        """
        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))
        
        return self.chat(messages, **kwargs)
    
    def stream(self, messages: List[BaseMessage], **kwargs) -> Generator[str, None, None]:
        """Stream response tokens.
        
        Args:
            messages: List of LangChain messages.
            **kwargs: Additional arguments.
            
        Yields:
            Response text chunks.
        """
        if not self._active_provider:
            raise RuntimeError("No provider selected. Call switch_provider() first.")
        
        yield from self._active_provider.stream(messages, **kwargs)
    
    def stream_text(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> Generator[str, None, None]:
        """Stream response from text prompt (convenience method).
        
        Args:
            prompt: User prompt text.
            system_prompt: Optional system prompt.
            **kwargs: Additional arguments.
            
        Yields:
            Response text chunks.
        """
        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))
        
        yield from self.stream(messages, **kwargs)


# Singleton instance
_client: Optional[UnifiedLLMClient] = None


def get_client(provider_name: Optional[str] = None, config_path: Optional[str] = None) -> UnifiedLLMClient:
    """Get singleton LLM client instance.
    
    Args:
        provider_name: Provider to use. If None, uses config default.
        config_path: Path to config file.
        
    Returns:
        UnifiedLLMClient instance.
    """
    global _client
    if _client is None:
        _client = UnifiedLLMClient(provider_name, config_path)
    return _client


def reset_client() -> None:
    """Reset singleton client (useful for testing)."""
    global _client
    _client = None
