"""Abstract base class for embedding services."""

from abc import ABC, abstractmethod
from typing import List


class EmbeddingService(ABC):
    """Abstract base class defining the embedding service interface.
    
    All embedding providers must implement this interface to be compatible
    with the plugin system and factory pattern.
    
    LangChain-style alias methods are provided as concrete methods:
    - embed_query(text) → alias for embed(text)
    - embed_documents(texts) → alias for embed_batch(texts)
    """

    @property
    @abstractmethod
    def vector_size(self) -> int:
        """Return the dimension of vectors produced by this embedding service."""
        pass

    @abstractmethod
    def embed(self, text: str) -> List[float]:
        """Generate embedding vector for a single text string.
        
        Args:
            text: Input text to embed.
            
        Returns:
            List of floats representing the embedding vector.
        """
        pass

    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embedding vectors for multiple texts in batch.
        
        Args:
            texts: List of input texts to embed.
            
        Returns:
            List of embedding vectors, each being a list of floats.
        """
        pass

    def embed_query(self, text: str) -> List[float]:
        """Generate embedding for a single query text (LangChain-style alias).
        
        Delegates to embed(). Useful for query-side embedding in RAG pipelines.
        
        Args:
            text: Query text to embed.
            
        Returns:
            List of floats representing the embedding vector.
        """
        return self.embed(text)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple documents (LangChain-style alias).
        
        Delegates to embed_batch(). Useful for document-side embedding in RAG pipelines.
        
        Args:
            texts: List of document texts to embed.
            
        Returns:
            List of embedding vectors, each being a list of floats.
        """
        return self.embed_batch(texts)
