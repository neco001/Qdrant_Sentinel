"""Embedding Service plugin system.

Provider-agnostic embedding interfaces with multiple implementations:
- OpenAICompatibleService: Alibaba DashScope, OpenAI API, etc.
- BytePlusArkService: BytePlus Volcengine Ark API
"""

from embedding_service.base import EmbeddingService
from embedding_service.openai_compatible import OpenAICompatibleService
from embedding_service.byteplus_ark import BytePlusArkService
from embedding_service.factory import EmbeddingServiceFactory

__all__ = [
    "EmbeddingService",
    "OpenAICompatibleService",
    "BytePlusArkService",
    "EmbeddingServiceFactory",
]
