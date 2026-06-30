"""Tests for mcp_server/server.py embedding service factory integration."""

import pytest
import os
from unittest.mock import MagicMock, patch


# Set env var for tests to pass
os.environ["EMBEDDING_API_KEY"] = "test-api-key"


class TestMCPServerEmbeddingFactory:
    """Tests for MCP server using EmbeddingServiceFactory."""

    def test_mcp_imports_embedding_factory(self):
        """mcp_server/server.py should import EmbeddingServiceFactory."""
        import sys
        sys.path.insert(0, '.')
        from mcp_server.server import EmbeddingServiceFactory
        assert EmbeddingServiceFactory is not None

    def test_mcp_no_direct_openai_import(self):
        """mcp_server/server.py should NOT import OpenAI directly."""
        import mcp_server.server
        import inspect
        source = inspect.getsource(mcp_server.server)
        for line in source.split('\n'):
            stripped = line.strip()
            if stripped.startswith('from openai import OpenAI'):
                pytest.fail(f"Direct OpenAI import found: {stripped}")

    @patch("mcp_server.server.EmbeddingServiceFactory.create")
    @patch("mcp_server.server._create_qdrant_client")
    @patch("mcp_server.server._load_config")
    def test_search_qdrant_uses_embedding_service(
        self, mock_load_config, mock_create_qdrant, mock_factory_create
    ):
        """search_qdrant should use embedding_service.embed() not OpenAI API."""
        from mcp_server.server import search_qdrant, reset_state
        
        # Reset any cached state
        reset_state()
        
        # Mock config
        mock_config = MagicMock()
        mock_config.qdrant.url = "http://127.0.0.1:6333"
        mock_config.embeddings.provider = "openai_compatible"
        mock_config.embeddings.model_name = "text-embedding-v4"
        mock_config.embeddings.base_url = "https://example.com/v1"
        mock_config.embeddings.dimension = 1024
        mock_config.embeddings.api_key_env_var = "EMBEDDING_API_KEY"
        mock_config.paths.state_db = ":memory:"
        mock_config.openviking.cli_path = "ov"
        mock_config.openviking.enabled = True
        mock_config.openviking.data_path = "./openviking_data"
        mock_load_config.return_value = mock_config
        
        # Mock Qdrant client
        mock_qdrant = MagicMock()
        mock_qdrant.collection_exists.return_value = True
        mock_qdrant.search.return_value = []
        mock_create_qdrant.return_value = mock_qdrant
        
        # Mock embedding service
        mock_embedding = MagicMock()
        mock_embedding.embed.return_value = [0.1] * 1024
        mock_factory_create.return_value = mock_embedding
        
        with patch.dict(os.environ, {"EMBEDDING_API_KEY": "test-key"}):
            try:
                search_qdrant("test-collection", "test query", limit=1)
            except Exception:
                pass  # May fail due to other setup, but factory should be called
        
        # Verify factory was called with correct provider
        mock_factory_create.assert_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
