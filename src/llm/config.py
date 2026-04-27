"""LLM Configuration Module.

Handles loading and validation of LLM provider configuration from YAML.
Supports environment variable substitution.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class ProviderConfig:
    """Configuration for a single LLM provider."""
    
    name: str
    enabled: bool = False
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: str = "gpt-3.5-turbo"
    max_tokens: int = 4096
    temperature: float = 0.1
    extra_body: Optional[Dict[str, Any]] = None
    
    def get_api_key(self) -> Optional[str]:
        """Get API key, resolving environment variables if needed."""
        if not self.api_key:
            return None
        if self.api_key.startswith("${") and self.api_key.endswith("}"):
            env_var = self.api_key[2:-1]
            return os.getenv(env_var)
        return self.api_key


@dataclass
class ExtractionConfig:
    """Configuration for entity/relation extraction."""
    
    chunk_size: int = 1000
    chunk_overlap: int = 200
    max_chunks_per_document: int = 50
    entity_types: List[str] = field(default_factory=list)
    relation_types: List[str] = field(default_factory=list)


@dataclass
class LLMConfig:
    """Complete LLM configuration container."""
    
    providers: Dict[str, ProviderConfig] = field(default_factory=dict)
    default_provider: str = "ollama"
    extraction: ExtractionConfig = field(default_factory=ExtractionConfig)
    
    @classmethod
    def from_yaml(cls, config_path: Optional[Union[str, Path]] = None) -> "LLMConfig":
        """Load configuration from YAML file.
        
        Args:
            config_path: Path to config file. If None, uses default path.
            
        Returns:
            LLMConfig instance with loaded settings.
        """
        if config_path is None:
            # Try to find config in project root
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "config" / "llm.yaml"
        else:
            config_path = Path(config_path) if isinstance(config_path, str) else config_path
            
        if not config_path.exists():
            logger.warning(f"Config file not found: {config_path}")
            return cls._default_config()
            
        with open(config_path, 'r') as f:
            raw_config = yaml.safe_load(f)
            
        return cls._from_dict(raw_config)
    
    @classmethod
    def _from_dict(cls, raw_config: Dict[str, Any]) -> "LLMConfig":
        """Parse raw config dict into LLMConfig."""
        providers = {}
        for name, settings in raw_config.get("providers", {}).items():
            providers[name] = ProviderConfig(
                name=name,
                enabled=settings.get("enabled", False),
                api_key=settings.get("api_key"),
                base_url=settings.get("base_url"),
                model=settings.get("model", "gpt-3.5-turbo"),
                max_tokens=settings.get("max_tokens", 4096),
                temperature=settings.get("temperature", 0.1),
                extra_body=settings.get("extra_body"),
            )
            
        extraction_dict = raw_config.get("extraction", {})
        extraction_config = ExtractionConfig(
            chunk_size=extraction_dict.get("chunk_size", 1000),
            chunk_overlap=extraction_dict.get("chunk_overlap", 200),
            max_chunks_per_document=extraction_dict.get("max_chunks_per_document", 50),
            entity_types=raw_config.get("entity_types", []),
            relation_types=raw_config.get("relation_types", []),
        )
        
        return cls(
            providers=providers,
            default_provider=raw_config.get("default_provider", "ollama"),
            extraction=extraction_config,
        )
    
    @classmethod
    def _default_config(cls) -> "LLMConfig":
        """Return default configuration when file is missing."""
        return cls(
            providers={
                "ollama": ProviderConfig(
                    name="ollama",
                    enabled=True,
                    base_url="http://localhost:11434",
                    model="llama3.2:3b",
                ),
            },
            default_provider="ollama",
        )
    
    def get_enabled_providers(self) -> List[str]:
        """Get list of enabled provider names."""
        return [name for name, config in self.providers.items() if config.enabled]
    
    def get_provider_config(self, provider_name: Optional[str] = None) -> Optional[ProviderConfig]:
        """Get configuration for a specific provider.
        
        Args:
            provider_name: Provider name. If None, uses default_provider.
            
        Returns:
            ProviderConfig or None if not found.
        """
        if provider_name is None:
            provider_name = self.default_provider
        return self.providers.get(provider_name)


# Global config instance
_config: Optional[LLMConfig] = None


def get_config(config_path: Optional[Union[str, Path]] = None) -> LLMConfig:
    """Get singleton config instance.
    
    Args:
        config_path: Optional path to config file. Only used on first call.
        
    Returns:
        LLMConfig instance.
    """
    global _config
    if _config is None or config_path is not None:
        _config = LLMConfig.from_yaml(config_path)
    return _config


def reload_config(config_path: Optional[Union[str, Path]] = None) -> LLMConfig:
    """Force reload configuration from file.
    
    Args:
        config_path: Optional path to config file.
        
    Returns:
        Reloaded LLMConfig instance.
    """
    global _config
    _config = LLMConfig.from_yaml(config_path)
    return _config
