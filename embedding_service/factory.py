"""Embedding service factory for provider-agnostic embedding creation.

Factory pattern implementation that creates appropriate EmbeddingService
implementations based on provider configuration.
"""

from typing import Dict, Any, Optional

from embedding_service.base import EmbeddingService


class EmbeddingServiceFactory:
    """Factory for creating embedding service instances by provider name.
    
    Supported providers:
    - 'openai_compatible': OpenAI API, Alibaba DashScope, any OpenAI-compatible endpoint
    - 'byteplus_ark': BytePlus Volcengine Ark API (OpenAI-compatible)
    
    Example:
        service = EmbeddingServiceFactory.create(
            provider='openai_compatible',
            api_key='your-key',
            model_name='text-embedding-v4',
            base_url='https://dashscope.aliyuncs.com/compatible-mode/v1'
        )
    """
    
    # Map provider names to their default configurations
    PROVIDER_DEFAULTS: Dict[str, Dict[str, Any]] = {
        'openai_compatible': {
            'base_url': None,  # User must specify or use OpenAI default
            'vector_size': 1024,
        },
        'byteplus_ark': {
            'base_url': 'https://ark.ap-southeast.bytepluses.com/api/coding/v3',
            'vector_size': 1024,
        },
        # Aliases for convenience
        'alibaba': {
            'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
            'vector_size': 1024,
        },
        'dashscope': {
            'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
            'vector_size': 1024,
        },
        'byteplus': {
            'base_url': 'https://ark.ap-southeast.bytepluses.com/api/coding/v3',
            'vector_size': 1024,
        },
    }
    
    @classmethod
    def create(
        cls,
        provider: str,
        api_key: str,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None,
        vector_size: Optional[int] = None,
        model: Optional[str] = None,  # Deprecated alias
        **kwargs,
    ) -> EmbeddingService:
        """Create an embedding service instance for the specified provider.
        
        Args:
            provider: Name of the embedding provider.
                      Supported: 'openai_compatible', 'byteplus_ark', 'alibaba', 'byteplus'
            api_key: API key for authentication.
            model_name: Name/ID of the embedding model to use.
            base_url: Optional custom base URL for the API endpoint.
                      If not provided, uses provider-specific defaults.
            vector_size: Dimension of output vectors. Defaults to provider-specific default.
            model: Deprecated alias for model_name (backward compatibility).
            **kwargs: Additional provider-specific arguments.
            
        Returns:
            An EmbeddingService implementation instance.
            
        Raises:
            ValueError: If the provider is unknown or required parameters are missing.
            ImportError: If required dependencies for the provider are not installed.
        """
        provider_lower = provider.lower()
        
        # Check if provider is supported
        if provider_lower not in cls.PROVIDER_DEFAULTS:
            raise ValueError(
                f"Unknown embedding provider: '{provider}'. "
                f"Supported providers: {list(cls.PROVIDER_DEFAULTS.keys())}"
            )
        
        # Get provider defaults
        defaults = cls.PROVIDER_DEFAULTS[provider_lower]
        
        # Merge user-provided values with defaults
        effective_base_url = base_url or defaults.get('base_url')
        effective_vector_size = vector_size or defaults.get('vector_size', 1024)
        effective_model_name = model_name or model
        
        # Both OpenAICompatibleService and BytePlusArkService use the same underlying
        # OpenAI-compatible API. The difference is in default base_url.
        from embedding_service.openai_compatible import OpenAICompatibleService
        
        # BytePlusArkService is a wrapper with BytePlus defaults, but we can also
        # use OpenAICompatibleService directly with the right base_url
        if provider_lower in ('byteplus_ark', 'byteplus'):
            try:
                from embedding_service.byteplus_ark import BytePlusArkService
                return BytePlusArkService(
                    api_key=api_key,
                    model_name=effective_model_name,
                    base_url=effective_base_url,
                    vector_size=effective_vector_size,
                    model=model,  # Pass deprecated alias for internal handling
                    **kwargs,
                )
            except ImportError:
                # Fall back to OpenAICompatibleService with BytePlus defaults
                pass
        
        # Default: OpenAICompatibleService
        return OpenAICompatibleService(
            api_key=api_key,
            model_name=effective_model_name,
            base_url=effective_base_url,
            vector_size=effective_vector_size,
            model=model,  # Pass deprecated alias
            **kwargs,
        )
    
    @classmethod
    def get_supported_providers(cls) -> list:
        """Return a list of all supported provider names.
        
        Returns:
            List of provider name strings.
        """
        return list(cls.PROVIDER_DEFAULTS.keys())
    
    @classmethod
    def get_provider_defaults(cls, provider: str) -> Dict[str, Any]:
        """Get the default configuration for a specific provider.
        
        Args:
            provider: Name of the provider.
            
        Returns:
            Dictionary containing default configuration values.
            
        Raises:
            ValueError: If the provider is unknown.
        """
        provider_lower = provider.lower()
        if provider_lower not in cls.PROVIDER_DEFAULTS:
            raise ValueError(f"Unknown provider: '{provider}'")
        return cls.PROVIDER_DEFAULTS[provider_lower].copy()
