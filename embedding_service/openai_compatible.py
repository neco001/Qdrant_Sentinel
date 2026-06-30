"""OpenAI-compatible embedding service implementation.

Works with Alibaba DashScope, OpenAI API, and any OpenAI-compatible endpoint.
"""

from typing import List, Optional

from embedding_service.base import EmbeddingService

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False
    OpenAI = None


class OpenAICompatibleService(EmbeddingService):
    """Embedding service using OpenAI-compatible API.
    
    Compatible with:
    - OpenAI API
    - Alibaba DashScope
    - Any OpenAI-compatible endpoint
    """

    def __init__(
        self,
        api_key: str,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None,
        vector_size: int = 1024,
        model: Optional[str] = None,  # Backward compatibility alias
    ):
        """Initialize OpenAI-compatible embedding service.
        
        Args:
            api_key: API key for the service.
            model_name: Model name/ID to use (e.g., 'text-embedding-v4' for DashScope).
            base_url: Optional base URL for the API endpoint. For Alibaba DashScope,
                      use 'https://dashscope.aliyuncs.com/compatible-mode/v1'.
            vector_size: Dimension of output vectors. Defaults to 1024.
            model: Deprecated alias for model_name (backward compatibility).
        """
        if not HAS_OPENAI or OpenAI is None:
            raise ImportError(
                "OpenAI SDK not installed. Install with: pip install openai"
            )
        
        # Support both model_name (preferred) and model (backward compat)
        self._model = model_name or model
        if self._model is None:
            raise ValueError("model_name is required")
        
        self._vector_size = vector_size
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    @property
    def vector_size(self) -> int:
        return self._vector_size

    def embed(self, text: str) -> List[float]:
        """Generate embedding for a single text.
        
        Args:
            text: Input text string.
            
        Returns:
            Embedding vector as list of floats.
        """
        response = self._client.embeddings.create(
            input=[text],  # Pass as list for API consistency
            model=self._model,
        )
        return response.data[0].embedding

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts in batch.
        
        Args:
            texts: List of input text strings.
            
        Returns:
            List of embedding vectors.
        """
        response = self._client.embeddings.create(
            input=texts,
            model=self._model,
        )
        # Sort by index to ensure correct order
        sorted_data = sorted(response.data, key=lambda x: x.index)
        return [item.embedding for item in sorted_data]
