from .base import LLMBase
from .models import TokenUsage
from .openai import OpenAILLM
from app.logger import get_logger
from typing import List


logger = get_logger(__name__)


class LLMFactory:
    """Factory for creating LLM provider instances."""
    
    LLM_MAP = {
        "openai": OpenAILLM,
        # "anthropic": AnthropicLLM,
        # "gemini": GeminiLLM,
    }

    @classmethod
    def get_llm(cls, provider: str, model: str, **kwargs) -> LLMBase:
        """Get LLM instance for a provider.
        
        Args:
            provider: Provider name ('openai', 'anthropic', 'gemini')
            model: Model name
            **kwargs: Additional arguments (timeout, max_retries, etc.)
            
        Returns:
            LLMBase instance
            
        Raises:
            ValueError: If provider is not supported
        """
        provider_lower = provider.lower()
        llm_cls = cls.LLM_MAP.get(provider_lower)
        
        if not llm_cls:
            supported = ", ".join(cls.LLM_MAP.keys())
            logger.error(f"Unsupported LLM provider '{provider}'. Supported: {supported}")
            raise ValueError(f"Unsupported LLM provider: {provider}. Supported providers: {supported}")
        
        logger.info(f"Creating {provider} LLM instance with model {model}")
        return llm_cls(model=model, provider=provider_lower, **kwargs)

    @classmethod
    def get_supported_providers(cls) -> List[str]:
        """Get list of supported providers."""
        return list(cls.LLM_MAP.keys())


# Global factory instance
llm_factory = LLMFactory()
logger.info(f"LLM Factory initialized with providers: {llm_factory.get_supported_providers()}")