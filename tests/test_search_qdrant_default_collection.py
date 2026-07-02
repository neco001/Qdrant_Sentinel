"""TDD RED test for default collection resolution in search_qdrant().

This test should FAIL with current code because:
1. Current search_qdrant signature: collection_name: str (required)
2. Current search_qdrant signature: NOT Optional[str] = None
3. No logic to resolve default from config.qdrant.collections
"""
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def reset_mcp_state():
    """Reset MCP server state before each test."""
    from mcp_server.server import reset_state
    reset_state()
    yield


@pytest.fixture
def mock_embedding_service():
    """Mock embedding service following test_search_qdrant_api_migration.py pattern."""
    service = MagicMock()
    service.embed.return_value = [0.1, 0.2, 0.3, 0.4, 0.5]
    return service


@pytest.fixture
def mock_qdrant_client_v118():
    """Mock qdrant-client v1.18.0 — has query_points, NOT search.
    
    From test_search_qdrant_api_migration.py.
    """
    client = MagicMock(spec=['get_collection', 'query_points'])

    scored_point = MagicMock()
    scored_point.id = "abc-123"
    scored_point.score = 0.95
    scored_point.payload = {"text": "test content", "file_path": "src/example.py"}

    query_response = MagicMock()
    query_response.points = [scored_point]

    client.get_collection.return_value = MagicMock()
    client.query_points.return_value = query_response

    del client.search

    return client


class TestDefaultCollectionResolution:
    """Test collection_name: Optional[str] = None behavior.
    
    RED phase - tests WILL fail until implementation is done.
    """

    def test_uses_default_collection_from_config_when_none_passed(
        self, mock_embedding_service, mock_qdrant_client_v118
    ):
        """Test 1: When collection_name=None, use config.qdrant.collections[0].
        
        CURRENTLY FAILS: search_qdrant(collection_name: str) does not accept None.
        """
        # Mock config WITH collections populated (following test_mcp_server.py pattern)
        mock_config = MagicMock()
        mock_config.qdrant.url = "http://localhost:6333"
        mock_config.qdrant.collections = ["default-collection-from-toml"]
        mock_config.embeddings.base_url = "https://api.example.com/v1"
        mock_config.embeddings.api_key = "fake-key"
        mock_config.embeddings.model_name = "text-embedding-v4kt"
        mock_config.embeddings.provider = "dashscope"
        mock_config.embeddings.vector_size = 1024
        mock_config.openviking.data_path = None
        mock_config.paths.state_db = "sentinel_state.db"

        with patch('mcp_server.server._load_config', return_value=mock_config), \
             patch('mcp_server.server._create_qdrant_client', return_value=mock_qdrant_client_v118), \
             patch('mcp_server.server._create_embedding_service', return_value=mock_embedding_service), \
             patch('mcp_server.server._create_ov_client'):

            from mcp_server.server import search_qdrant

            # This call SHOULD FAIL NOW with TypeError because collection_name is required
            result = search_qdrant(
                collection_name=None,  # Currently fails: expected str, got NoneType
                query_text="test query"
            )

            # After implementation, should verify:
            mock_qdrant_client_v118.get_collection.assert_called_once_with("default-collection-from-toml")
            call_kwargs = mock_qdrant_client_v118.query_points.call_args
            assert call_kwargs[1]['collection_name'] == "default-collection-from-toml"

    def test_raises_value_error_when_collections_empty_and_none_passed(
        self, mock_embedding_service, mock_qdrant_client_v118
    ):
        """Test 2: When collection_name=None AND collections=[], raise ValueError.
        
        CURRENTLY FAILS: search_qdrant doesn't accept None AND has no such validation.
        """
        # Mock config WITH EMPTY collections (backward compatible default)
        mock_config = MagicMock()
        mock_config.qdrant.url = "http://localhost:6333"
        mock_config.qdrant.collections = []  # Empty = not configured in TOML
        mock_config.embeddings.base_url = "https://api.example.com/v1"
        mock_config.embeddings.api_key = "fake-key"
        mock_config.embeddings.model_name = "text-embedding-v4kt"
        mock_config.embeddings.provider = "dashscope"
        mock_config.embeddings.vector_size = 1024
        mock_config.openviking.data_path = None
        mock_config.paths.state_db = "sentinel_state.db"

        with patch('mcp_server.server._load_config', return_value=mock_config), \
             patch('mcp_server.server._create_qdrant_client', return_value=mock_qdrant_client_v118), \
             patch('mcp_server.server._create_embedding_service', return_value=mock_embedding_service), \
             patch('mcp_server.server._create_ov_client'):

            from mcp_server.server import search_qdrant

            # This SHOULD raise ValueError AFTER implementation
            # Currently it raises TypeError (None not allowed)
            with pytest.raises(ValueError) as exc_info:
                search_qdrant(
                    collection_name=None,
                    query_text="test query"
                )
            
            assert "No collections configured" in str(exc_info.value)

    def test_explicit_collection_name_still_works(
        self, mock_embedding_service, mock_qdrant_client_v118
    ):
        """Test 3: Explicit collection_name takes precedence over default.
        
        This test SHOULD PASS with current code (backward compatibility).
        If it fails now - something is fundamentally broken.
        """
        # Mock config with default collection
        mock_config = MagicMock()
        mock_config.qdrant.url = "http://localhost:6333"
        mock_config.qdrant.collections = ["should-be-ignored"]
        mock_config.embeddings.base_url = "https://api.example.com/v1"
        mock_config.embeddings.api_key = "fake-key"
        mock_config.embeddings.model_name = "text-embedding-v4kt"
        mock_config.embeddings.provider = "dashscope"
        mock_config.embeddings.vector_size = 1024
        mock_config.openviking.data_path = None
        mock_config.paths.state_db = "sentinel_state.db"

        with patch('mcp_server.server._load_config', return_value=mock_config), \
             patch('mcp_server.server._create_qdrant_client', return_value=mock_qdrant_client_v118), \
             patch('mcp_server.server._create_embedding_service', return_value=mock_embedding_service), \
             patch('mcp_server.server._create_ov_client'):

            from mcp_server.server import search_qdrant

            # Pass explicit collection name - existing behavior
            result = search_qdrant(
                collection_name="explicit-collection",
                query_text="test query",
                limit=5
            )

            # Should use explicit collection, NOT the default from config
            mock_qdrant_client_v118.get_collection.assert_called_once_with("explicit-collection")
            call_kwargs = mock_qdrant_client_v118.query_points.call_args
            assert call_kwargs[1]['collection_name'] == "explicit-collection"
