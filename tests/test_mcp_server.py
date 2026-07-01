"""Test suite for MCP server tools (TDD Phase 1: RED)."""
import pytest
from unittest.mock import Mock, patch, MagicMock
import sqlite3
from pathlib import Path


@pytest.fixture(autouse=True)
def reset_mcp_state():
    """Reset MCP server state before each test to enable proper mocking."""
    from mcp_server.server import reset_state
    reset_state()
    yield


class TestSearchQdrant:
    """Test search_qdrant tool functionality."""
    
    @pytest.fixture
    def mock_qdrant_client(self):
        """Mock Qdrant client."""
        client = MagicMock()
        client.get_collection.return_value = MagicMock(points_count=100)
        client.search.return_value = [
            MagicMock(id="1", score=0.95, payload={"text": "test content", "file_path": "test.py"})
        ]
        return client
    
    @pytest.fixture
    def mock_config(self):
        """Mock shared_config."""
        config = MagicMock()
        config.qdrant.url = "http://localhost:6333"
        config.embeddings.base_url = "https://api.example.com/v1"
        config.embeddings.model_name = "text-embedding-v4"
        return config
    
    def test_search_qdrant_success(self, mock_qdrant_client, mock_config):
        """Verify successful semantic search returns results."""
        with patch('mcp_server.server._load_config', return_value=mock_config), \
             patch('mcp_server.server._create_qdrant_client', return_value=mock_qdrant_client), \
             patch('mcp_server.server._create_embedding_service'):
            from mcp_server.server import search_qdrant
            
            result = search_qdrant("test_collection", "search query", limit=5)
            
            assert result is not None
            assert len(result) > 0
            mock_qdrant_client.search.assert_called_once()
    
    def test_search_qdrant_invalid_collection(self, mock_qdrant_client, mock_config):
        """Verify error handling for non-existent collection."""
        mock_qdrant_client.get_collection.side_effect = Exception("Collection not found")
        
        with patch('mcp_server.server._load_config', return_value=mock_config), \
             patch('mcp_server.server._create_qdrant_client', return_value=mock_qdrant_client), \
             patch('mcp_server.server._create_embedding_service'):
            from mcp_server.server import search_qdrant
            
            with pytest.raises(Exception, match="Collection not found"):
                search_qdrant("invalid_collection", "query")
    
    def test_search_qdrant_read_only_uses_search_not_upsert(self, mock_qdrant_client, mock_config):
        """Verify read-only safety: uses search() not upsert()."""
        with patch('mcp_server.server._load_config', return_value=mock_config), \
             patch('mcp_server.server._create_qdrant_client', return_value=mock_qdrant_client), \
             patch('mcp_server.server._create_embedding_service'):
            from mcp_server.server import search_qdrant
            
            search_qdrant("test_collection", "query")
            
            # Should call search, not upsert
            mock_qdrant_client.search.assert_called()
            assert not mock_qdrant_client.upsert.called


class TestGetSearchContext:
    """Test get_search_context tool functionality."""
    
    @pytest.fixture
    def mock_ov_client(self):
        """Mock OpenViking client."""
        client = MagicMock()
        client.find_resources.return_value = [
            {
                "uri": "file:///test.py",
                "content": "test content",
                "metadata": {"tier": "L1"}
            }
        ]
        return client
    
    def test_get_search_context_l1_tier(self, mock_ov_client):
        """Verify L1 context retrieval."""
        with patch('mcp_server.server._create_ov_client', return_value=mock_ov_client):
            from mcp_server.server import get_search_context
            
            result = get_search_context("qdrant_id_123", tier="L1")
            
            assert result is not None
            mock_ov_client.find_resources.assert_called_once()
    
    def test_get_search_context_l0_tier(self, mock_ov_client):
        """Verify L0 context retrieval (original content)."""
        mock_ov_client.find_resources.return_value = [
            {
                "uri": "file:///test.py",
                "content": "original content",
                "metadata": {"tier": "L0"}
            }
        ]
        
        with patch('mcp_server.server._create_ov_client', return_value=mock_ov_client):
            from mcp_server.server import get_search_context
            
            result = get_search_context("qdrant_id_123", tier="L0")
            
            assert result is not None
            assert result[0]["metadata"]["tier"] == "L0"
    
    def test_get_search_context_invalid_tier(self, mock_ov_client):
        """Verify error handling for invalid tier."""
        with patch('mcp_server.server._create_ov_client', return_value=mock_ov_client):
            from mcp_server.server import get_search_context
            
            with pytest.raises(ValueError, match="Invalid tier"):
                get_search_context("qdrant_id_123", tier="INVALID")
    
    def test_get_search_context_read_only_uses_find_not_add(self, mock_ov_client):
        """Verify read-only safety: uses find_resources() not add_resource()."""
        with patch('mcp_server.server._create_ov_client', return_value=mock_ov_client):
            from mcp_server.server import get_search_context
            
            get_search_context("qdrant_id_123", tier="L1")
            
            # Should call find_resources, not add_resource
            mock_ov_client.find_resources.assert_called()
            assert not mock_ov_client.add_resource.called


class TestExpandContext:
    """Test expand_context tool functionality."""
    
    @pytest.fixture
    def mock_config(self):
        """Mock shared_config."""
        config = MagicMock()
        config.paths.state_db = "sentinel_state.db"
        return config
    
    @pytest.fixture
    def mock_sqlite_conn(self):
        """Mock SQLite connection."""
        conn = MagicMock()
        cursor = MagicMock()
        
        # Mock parent query result
        cursor.fetchone.return_value = ("parent_qdrant_id",)
        cursor.fetchall.return_value = [
            ("child_qdrant_id_1",),
            ("child_qdrant_id_2",)
        ]
        
        conn.cursor.return_value = cursor
        return conn
    
    def test_expand_context_both_directions(self, mock_sqlite_conn, mock_config):
        """Verify context expansion in both directions."""
        with patch('mcp_server.server._load_config', return_value=mock_config), \
             patch('mcp_server.server.sqlite3.connect', return_value=mock_sqlite_conn):
            from mcp_server.server import expand_context
            
            result = expand_context("file:///test.py", direction="both")
            
            assert result is not None
            assert "parents" in result or "children" in result
    
    def test_expand_context_parent_only(self, mock_sqlite_conn, mock_config):
        """Verify parent-only context expansion."""
        with patch('mcp_server.server._load_config', return_value=mock_config), \
             patch('mcp_server.server.sqlite3.connect', return_value=mock_sqlite_conn):
            from mcp_server.server import expand_context
            
            result = expand_context("file:///test.py", direction="parent")
            
            assert result is not None
    
    def test_expand_context_child_only(self, mock_sqlite_conn, mock_config):
        """Verify child-only context expansion."""
        with patch('mcp_server.server._load_config', return_value=mock_config), \
             patch('mcp_server.server.sqlite3.connect', return_value=mock_sqlite_conn):
            from mcp_server.server import expand_context
            
            result = expand_context("file:///test.py", direction="child")
            
            assert result is not None
    
    def test_expand_context_read_only_uses_select_not_insert(self, mock_sqlite_conn, mock_config):
        """Verify read-only safety: uses SELECT not INSERT/UPDATE."""
        with patch('mcp_server.server._load_config', return_value=mock_config), \
             patch('mcp_server.server.sqlite3.connect', return_value=mock_sqlite_conn):
            from mcp_server.server import expand_context
            
            expand_context("file:///test.py")
            
            cursor = mock_sqlite_conn.cursor.return_value
            # Should execute SELECT queries
            assert cursor.execute.called
            
            # Check that no write operations were attempted
            for call in cursor.execute.call_args_list:
                query = call[0][0].strip().upper() if call[0] else ""
                assert query.startswith("SELECT") or query.startswith("WITH")


class TestFindByStructure:
    """Test find_by_structure tool functionality."""
    
    @pytest.fixture
    def mock_config(self):
        """Mock configuration."""
        from shared_config import AppConfig, QdrantConfig, EmbeddingsConfig, OpenVikingConfig, PathsConfig
        
        return AppConfig(
            qdrant=QdrantConfig(url="http://localhost:6333"),
            embeddings=EmbeddingsConfig(
                base_url="https://test.com",
                model_name="test_model",
                dimension=1024
            ),
            openviking=OpenVikingConfig(data_path="./test_data", cli_path="ov", enabled=False),
            paths=PathsConfig(data_root=".", state_db=":memory:")
        )
    
    @pytest.fixture
    def mock_sqlite_conn(self):
        """Mock SQLite connection."""
        conn = MagicMock()
        cursor = MagicMock()
        
        cursor.fetchall.return_value = [
            ("qdrant_id_1", "file:///src/module.py", "2024-01-01"),
            ("qdrant_id_2", "file:///src/utils.py", "2024-01-02")
        ]
        
        conn.cursor.return_value = cursor
        return conn
    
    def test_find_by_structure_pattern_wildcard(self, mock_sqlite_conn, mock_config):
        """Verify pattern matching with wildcards."""
        with patch('mcp_server.server._load_config', return_value=mock_config), \
             patch('mcp_server.server.sqlite3.connect', return_value=mock_sqlite_conn):
            from mcp_server.server import find_by_structure
            
            result = find_by_structure("src/*.py")
            
            assert result is not None
            assert len(result) > 0
    
    def test_find_by_structure_exact_path(self, mock_sqlite_conn, mock_config):
        """Verify exact path matching."""
        with patch('mcp_server.server._load_config', return_value=mock_config), \
             patch('mcp_server.server.sqlite3.connect', return_value=mock_sqlite_conn):
            from mcp_server.server import find_by_structure
            
            result = find_by_structure("src/module.py")
            
            assert result is not None
    
    def test_find_by_structure_no_results(self, mock_sqlite_conn, mock_config):
        """Verify empty result handling."""
        mock_sqlite_conn.cursor.return_value.fetchall.return_value = []
        
        with patch('mcp_server.server._load_config', return_value=mock_config), \
             patch('mcp_server.server.sqlite3.connect', return_value=mock_sqlite_conn):
            from mcp_server.server import find_by_structure
            
            result = find_by_structure("nonexistent/*.py")
            
            assert result == []
    
    def test_find_by_structure_read_only_uses_select_only(self, mock_sqlite_conn, mock_config):
        """Verify read-only safety: only SELECT queries."""
        with patch('mcp_server.server._load_config', return_value=mock_config), \
             patch('mcp_server.server.sqlite3.connect', return_value=mock_sqlite_conn):
            from mcp_server.server import find_by_structure
            
            find_by_structure("src/*.py")
            
            cursor = mock_sqlite_conn.cursor.return_value
            assert cursor.execute.called
            
            # Verify no write operations
            for call in cursor.execute.call_args_list:
                query = call[0][0].strip().upper() if call[0] else ""
                assert query.startswith("SELECT")


class TestConfigurationValidation:
    """Test configuration validation across tools."""
    
    def test_missing_qdrant_config_raises_error(self):
        """Verify error when Qdrant config is missing."""
        config = MagicMock()
        delattr(config, 'qdrant')
        
        with patch('mcp_server.server._load_config', return_value=config):
            from mcp_server.server import search_qdrant
            
            with pytest.raises(AttributeError, match="Qdrant configuration missing"):
                search_qdrant("test_collection", "query")
    
    def test_missing_embeddings_config_raises_error(self):
        """Verify error when embeddings config is missing."""
        config = MagicMock()
        config.qdrant.url = "http://localhost:6333"
        delattr(config, 'embeddings')
        
        with patch('mcp_server.server._load_config', return_value=config):
            from mcp_server.server import search_qdrant
            
            with pytest.raises(AttributeError, match="Embeddings configuration missing"):
                search_qdrant("test_collection", "query")


class TestConnectionErrorHandling:
    """Test graceful connection error handling."""
    
    @pytest.fixture
    def mock_config(self):
        """Mock configuration."""
        from shared_config import AppConfig, QdrantConfig, EmbeddingsConfig, OpenVikingConfig, PathsConfig

        return AppConfig(
            qdrant=QdrantConfig(url="http://localhost:6333"),
            embeddings=EmbeddingsConfig(
                base_url="https://test.com",
                model_name="test_model",
                dimension=1024
            ),
            openviking=OpenVikingConfig(data_path=".", cli_path="ov", enabled=False),
            paths=PathsConfig(data_root=".", state_db=":memory:")
        )
    
    def test_qdrant_connection_failure(self):
        """Verify graceful handling of Qdrant connection failure."""
        with patch('mcp_server.server._load_config', side_effect=ConnectionError("Cannot connect")):
            from mcp_server.server import search_qdrant
            
            with pytest.raises(ConnectionError):
                search_qdrant("test_collection", "query")
    
    def test_sqlite_connection_failure(self, mock_config):
        """Verify graceful handling of SQLite connection failure."""
        with patch('mcp_server.server._load_config', return_value=mock_config), \
             patch('mcp_server.server.sqlite3.connect', side_effect=sqlite3.Error("Database locked")):
            from mcp_server.server import expand_context
            
            with pytest.raises(sqlite3.Error):
                expand_context("file:///test.py")
    
    def test_openviking_cli_not_found(self):
        """Verify graceful handling when OpenViking CLI is not found."""
        with patch('mcp_server.server._create_ov_client', side_effect=FileNotFoundError("ov not found")):
            from mcp_server.server import get_search_context
            
            with pytest.raises(FileNotFoundError):
                get_search_context("qdrant_id_123")
