"""Tests for sentinel.py embedding service factory integration.

Tests verify that QdrantSentinel uses EmbeddingServiceFactory
instead of direct OpenAI client initialization.
"""

import pytest
import sys
from unittest.mock import MagicMock, patch


class TestSentinelEmbeddingFactoryIntegration:
    """Verify EmbeddingServiceFactory is imported in sentinel.py."""

    def test_sentinel_imports_embedding_factory(self):
        """sentinel.py should import EmbeddingServiceFactory."""
        from sentinel import EmbeddingServiceFactory
        assert EmbeddingServiceFactory is not None

    def test_sentinel_no_direct_openai_import(self):
        """sentinel.py should NOT import OpenAI directly at module level."""
        import sentinel
        import inspect
        source = inspect.getsource(sentinel)
        # Check that there's no 'from openai import OpenAI' at module level
        for line in source.split('\n'):
            stripped = line.strip()
            if stripped.startswith('from openai import OpenAI'):
                pytest.fail(f"Direct OpenAI import found at module level: {stripped}")

    def test_qdrant_sentinel_has_embedding_service_attribute(self):
        """QdrantSentinel.__init__ should create self.embedding_service."""
        with patch("sentinel.QdrantClient") as mock_qdrant:
            with patch("sentinel.OpenVikingClient") as mock_ov:
                with patch("sentinel.EmbeddingServiceFactory.create") as mock_factory:
                    mock_qdrant.return_value = MagicMock()
                    mock_ov.return_value = MagicMock()
                    mock_factory.return_value = MagicMock(vector_size=1024)

                    from sentinel import QdrantSentinel
                    sentinel = QdrantSentinel(["."])
                    
                    # Verify factory was called during __init__
                    mock_factory.assert_called_once()
                    assert hasattr(sentinel, 'embedding_service')
                    assert sentinel.embedding_service is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
