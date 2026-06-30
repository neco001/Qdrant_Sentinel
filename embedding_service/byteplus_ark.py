"""BytePlus Ark embedding service implementation.

BytePlus Volcengine Ark API uses OpenAI-compatible interface.
This module provides a specialized wrapper with BytePlus-specific defaults.

See: test_embedding_rate_limit.py for actual production usage pattern:
    OpenAI(base_url="https://ark.ap-southeast.bytepluses.com/api/coding/v3")
"""

from typing import List, Optional

from embedding_service.base import EmbeddingService
from embedding_service.openai_compatible import OpenAICompatibleService


class BytePlusArkService(EmbeddingService):
    """Embedding service using BytePlus Volcengine Ark API.
    
    BytePlus Ark API is OpenAI-compatible, so this is a thin wrapper
    around OpenAICompatibleService with BytePlus-specific default base_url.
    
    Default endpoint: https://ark.ap-southeast.bytepluses.com/api/coding/v3
    
    Example:
        service = BytePlusArkService(
            api_key='your-byteplus-key',
            model_name='your-endpoint-id'
        )
        embedding = service.embed('Hello world')
    """
    
    # BytePlus Ark default configuration
    DEFAULT_BASE_URL = 'https://ark.ap-southeast.bytepluses.com/api/coding/v3'
    DEFAULT_VECTOR_SIZE = 1024
    
    def __init__(
        self,
        api_key: str,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None,
        vector_size: int = DEFAULT_VECTOR_SIZE,
        model: Optional[str] = None,  # Backward compatibility alias
    ):
        """Initialize BytePlus Ark embedding service.
        
        Args:
            api_key: BytePlus API key for authentication.
            model_name: Model/endpoint ID to use (from BytePlus console).
            base_url: Optional custom base URL. Defaults to BytePlus Ark endpoint.
            vector_size: Dimension of output vectors. Defaults to 1024.
            model: Deprecated alias for model_name (backward compatibility).
        """
        # Use OpenAICompatibleService internally since BytePlus API is OpenAI-compatible
        effective_base_url = base_url or self.DEFAULT_BASE_URL
        effective_model_name = model_name or model
        
        self._impl = OpenAICompatibleService(
            api_key=api_key,
            model_name=effective_model_name,
            base_url=effective_base_url,
            vector_size=vector_size,
        )
    
    @property
    def vector_size(self) -> int:
        """Return the dimension of vectors produced by this embedding service."""
        return self._impl.vector_size
    
    def embed(self, text: str) -> List[float]:
        """Generate embedding for a single text.
        
        Args:
            text: Input text string.
            
        Returns:
            Embedding vector as list of floats.
        """
        return self._impl.embed(text)
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts in batch.
        
        Args:
            texts: List of input text strings.
            
        Returns:
            List of embedding vectors.
        """
        return self._impl.embed_batch(texts)
    
    @property
    def client(self):
        """Access the underlying OpenAI client (for advanced usage)."""
        return self._impl._client
