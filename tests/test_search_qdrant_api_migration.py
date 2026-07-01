"""TDD test for search_qdrant() qdrant-client v1.18.0 API migration.

This test verifies that search_qdrant() uses query_points() instead of the
deprecated .search() method, and correctly unwraps QueryResponse.points.
"""
import pytest
from unittest.mock import MagicMock, patch, call


@pytest.fixture(autouse=True)
def reset_mcp_state():
    """Reset MCP server state before each test."""
    from mcp_server.server import reset_state
    reset_state()
    yield


@pytest.fixture
def mock_config():
    """Mock shared config."""
    config = MagicMock()
    config.qdrant.url = "http://localhost:6333"
    config.embeddings.base_url = "https://api.example.com/v1"
    config.embeddings.api_key = "fake-key"
    config.embeddings.model_name = "text-embedding-v4kt"
    config.embeddings.provider = "dashscope"
    config.embeddings.vector_size = 1024
    config.openviking.data_path = None
    config.paths.state_db = "sentinel_state.db"
    return config


@pytest.fixture
def mock_embedding_service():
    """Mock embedding service."""
    service = MagicMock()
    service.embed.return_value = [0.1, 0.2, 0.3, 0.4, 0.5]
    return service


@pytest.fixture
def mock_qdrant_client_v118():
    """Mock qdrant-client v1.18.0 — has query_points, NOT search."""
    client = MagicMock(spec=['get_collection', 'query_points'])

    # query_points returns QueryResponse with .points
    scored_point = MagicMock()
    scored_point.id = "abc-123"
    scored_point.score = 0.95
    scored_point.payload = {"text": "test content", "file_path": "src/example.py"}

    query_response = MagicMock()
    query_response.points = [scored_point]

    client.get_collection.return_value = MagicMock()
    client.query_points.return_value = query_response

    # Ensure .search() does NOT exist (simulates real v1.18.0 client)
    del client.search

    return client


class TestSearchQdrantAPIv118:
    """Tests that verify qdrant-client v1.18.0 API compatibility."""

    def test_uses_query_points_not_search(self, mock_config, mock_embedding_service, mock_qdrant_client_v118):
        """search_qdrant must call query_points(), NOT search()."""
        with patch('mcp_server.server._load_config', return_value=mock_config), \
             patch('mcp_server.server._create_qdrant_client', return_value=mock_qdrant_client_v118), \
             patch('mcp_server.server._create_embedding_service', return_value=mock_embedding_service), \
             patch('mcp_server.server._create_ov_client'):

            from mcp_server.server import search_qdrant

            # This will raise AttributeError if code still uses .search()
            result = search_qdrant("test_collection", "search query", limit=5)

            # Must have called query_points
            mock_qdrant_client_v118.query_points.assert_called_once()
            # Must NOT have tried to call .search()
            assert not hasattr(mock_qdrant_client_v118, 'search') or not mock_qdrant_client_v118.search.called

    def test_query_points_receives_correct_params(self, mock_config, mock_embedding_service, mock_qdrant_client_v118):
        """query_points() must receive query= (not query_vector=) and collection_name, limit."""
        with patch('mcp_server.server._load_config', return_value=mock_config), \
             patch('mcp_server.server._create_qdrant_client', return_value=mock_qdrant_client_v118), \
             patch('mcp_server.server._create_embedding_service', return_value=mock_embedding_service), \
             patch('mcp_server.server._create_ov_client'):

            from mcp_server.server import search_qdrant

            search_qdrant("my_collection", "hello world", limit=10)

            call_kwargs = mock_qdrant_client_v118.query_points.call_args
            assert call_kwargs[1]['collection_name'] == "my_collection"
            assert 'query' in call_kwargs[1], "Expected 'query' param, not 'query_vector'"
            assert call_kwargs[1]['query'] == [0.1, 0.2, 0.3, 0.4, 0.5]
            assert call_kwargs[1]['limit'] == 10

    def test_returns_formatted_results_from_query_response_points(self, mock_config, mock_embedding_service, mock_qdrant_client_v118):
        """Results must be formatted from response.points with id, score, payload."""
        with patch('mcp_server.server._load_config', return_value=mock_config), \
             patch('mcp_server.server._create_qdrant_client', return_value=mock_qdrant_client_v118), \
             patch('mcp_server.server._create_embedding_service', return_value=mock_embedding_service), \
             patch('mcp_server.server._create_ov_client'):

            from mcp_server.server import search_qdrant

            result = search_qdrant("test_collection", "query")

            assert len(result) == 1
            assert result[0]['id'] == "abc-123"
            assert result[0]['score'] == 0.95
            assert result[0]['payload'] == {"text": "test content", "file_path": "src/example.py"}

    def test_empty_results_when_no_points(self, mock_config, mock_embedding_service, mock_qdrant_client_v118):
        """Must return empty list when query_points returns no points."""
        mock_qdrant_client_v118.query_points.return_value = MagicMock(points=[])

        with patch('mcp_server.server._load_config', return_value=mock_config), \
             patch('mcp_server.server._create_qdrant_client', return_value=mock_qdrant_client_v118), \
             patch('mcp_server.server._create_embedding_service', return_value=mock_embedding_service), \
             patch('mcp_server.server._create_ov_client'):

            from mcp_server.server import search_qdrant

            result = search_qdrant("test_collection", "query")
            assert result == []
