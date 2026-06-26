"""Test suite for audit fixes (TDD Phase 1: RED)."""
import pytest
from unittest.mock import patch, MagicMock
import sqlite3
from pathlib import Path


class TestSQLWildcardEscaping:
    """Test SQL wildcard escaping in find_by_structure."""
    
    @pytest.fixture
    def mock_config(self):
        """Mock configuration."""
        from shared_config import AppConfig, QdrantConfig, EmbeddingsConfig, PathsConfig, OpenVikingConfig
        
        return AppConfig(
            qdrant=QdrantConfig(url="http://localhost:6333"),
            embeddings=EmbeddingsConfig(
                base_url="http://localhost:11434",
                model_name="nomic-embed-text-v1.5",
                dimension=768
            ),
            openviking=OpenVikingConfig(cli_path="ov", enabled=True),
            paths=PathsConfig(data_root=".", state_db=":memory:")
        )
    
    @pytest.fixture
    def mock_sqlite_conn(self):
        """Mock SQLite connection."""
        conn = sqlite3.connect(":memory:")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ov_mappings (
                qdrant_id TEXT PRIMARY KEY,
                ov_resource_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("INSERT INTO ov_mappings VALUES ('id1', 'src/main.py', 'src/main.py', datetime('now'), datetime('now'))")
        conn.execute("INSERT INTO ov_mappings VALUES ('id2', 'src/utils.py', 'src/utils.py', datetime('now'), datetime('now'))")
        conn.execute("INSERT INTO ov_mappings VALUES ('id3', 'test_main.py', 'test_main.py', datetime('now'), datetime('now'))")
        conn.commit()
        return conn
    
    def test_wildcard_asterisk_works(self, mock_sqlite_conn, mock_config):
        """Verify asterisk wildcard works as expected."""
        with patch('mcp_server.server._get_config', return_value=mock_config), \
             patch('mcp_server.server._get_state_db_path', return_value=':memory:'), \
             patch('sqlite3.connect', return_value=mock_sqlite_conn):
            
            from mcp_server.server import find_by_structure
            
            # Asterisk should match any characters
            results = find_by_structure("src/*.py")
            assert len(results) == 2
            uris = [r['uri'] for r in results]
            assert 'src/main.py' in uris
            assert 'src/utils.py' in uris
    
    def test_percent_literal_is_escaped(self, mock_sqlite_conn, mock_config):
        """Verify percent sign in path is treated as literal, not wildcard."""
        # Add a file with percent in name
        mock_sqlite_conn.execute("INSERT INTO ov_mappings VALUES ('id4', 'data/test%file.py', 'data/test%file.py', datetime('now'), datetime('now'))")
        mock_sqlite_conn.commit()
        
        with patch('mcp_server.server._get_config', return_value=mock_config), \
             patch('mcp_server.server._get_state_db_path', return_value=':memory:'), \
             patch('sqlite3.connect', return_value=mock_sqlite_conn):
            
            from mcp_server.server import find_by_structure
            
            # Should match exact file with percent sign
            results = find_by_structure("data/test%file.py")
            assert len(results) == 1
            assert results[0]['uri'] == 'data/test%file.py'
    
    def test_underscore_literal_is_escaped(self, mock_sqlite_conn, mock_config):
        """Verify underscore in path is treated as literal, not wildcard."""
        with patch('mcp_server.server._get_config', return_value=mock_config), \
             patch('mcp_server.server._get_state_db_path', return_value=':memory:'), \
             patch('sqlite3.connect', return_value=mock_sqlite_conn):
            
            from mcp_server.server import find_by_structure
            
            # Should match exact file with underscore
            results = find_by_structure("src/main.py")
            assert len(results) == 1
            assert results[0]['uri'] == 'src/main.py'
    
    def test_sql_injection_attempt_is_safe(self, mock_sqlite_conn, mock_config):
        """Verify SQL injection attempts are neutralized."""
        with patch('mcp_server.server._get_config', return_value=mock_config), \
             patch('mcp_server.server._get_state_db_path', return_value=':memory:'), \
             patch('sqlite3.connect', return_value=mock_sqlite_conn):
            
            from mcp_server.server import find_by_structure
            
            # Attempt SQL injection - should be treated as literal string
            malicious = "src/' OR '1'='1"
            results = find_by_structure(malicious)
            # Should return empty, not all rows
            assert len(results) == 0


class TestOpenVikingErrorHandling:
    """Test graceful error handling for OpenViking failures."""
    
    @pytest.fixture
    def mock_config(self):
        """Mock configuration."""
        from shared_config import AppConfig, QdrantConfig, EmbeddingsConfig, PathsConfig, OpenVikingConfig
        
        return AppConfig(
            qdrant=QdrantConfig(url="http://localhost:6333"),
            embeddings=EmbeddingsConfig(
                base_url="http://localhost:11434",
                model_name="nomic-embed-text-v1.5",
                dimension=768
            ),
            openviking=OpenVikingConfig(cli_path="ov", enabled=True),
            paths=PathsConfig(data_root=".", state_db=":memory:")
        )
    
    def test_openviking_cli_not_found_returns_empty(self, mock_config):
        """Verify FileNotFoundError returns empty list instead of crashing."""
        with patch('mcp_server.server._get_config', return_value=mock_config), \
             patch('mcp_server.server._get_ov_client') as mock_get_ov:
            
            from mcp_server.server import get_search_context
            
            # Mock client that raises FileNotFoundError
            mock_client = MagicMock()
            mock_client.find_resources.side_effect = FileNotFoundError("ov not found")
            mock_get_ov.return_value = mock_client
            
            # Should return empty list, not raise exception
            result = get_search_context("test-id", tier="L1")
            assert result == []
    
    def test_openviking_generic_error_returns_empty(self, mock_config):
        """Verify generic exceptions return empty list instead of crashing."""
        with patch('mcp_server.server._get_config', return_value=mock_config), \
             patch('mcp_server.server._get_ov_client') as mock_get_ov:
            
            from mcp_server.server import get_search_context
            
            # Mock client that raises generic exception
            mock_client = MagicMock()
            mock_client.find_resources.side_effect = RuntimeError("OpenViking crashed")
            mock_get_ov.return_value = mock_client
            
            # Should return empty list, not raise exception
            result = get_search_context("test-id", tier="L1")
            assert result == []
    
    def test_openviking_success_returns_resources(self, mock_config):
        """Verify successful OpenViking calls return resources."""
        with patch('mcp_server.server._get_config', return_value=mock_config), \
             patch('mcp_server.server._get_ov_client') as mock_get_ov:
            
            from mcp_server.server import get_search_context
            
            # Mock client that returns resources
            mock_client = MagicMock()
            mock_client.find_resources.return_value = [
                {"id": "res1", "content": "test content"}
            ]
            mock_get_ov.return_value = mock_client
            
            result = get_search_context("test-id", tier="L1")
            assert len(result) == 1
            assert result[0]["id"] == "res1"


class TestReadOnlySafety:
    """Verify read-only safety is enforced."""
    
    def test_expand_context_uses_read_only_connection(self):
        """Verify expand_context uses read-only SQLite connection."""
        with patch('mcp_server.server._get_state_db_path', return_value=':memory:'), \
             patch('sqlite3.connect') as mock_connect:
            
            from mcp_server.server import expand_context
            
            # Mock successful connection
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn
            
            expand_context("test-uri", direction="parent")
            
            # Verify connection was made with read-only mode
            assert mock_connect.called
            call_args = mock_connect.call_args[0][0]
            assert "mode=ro" in call_args
    
    def test_find_by_structure_uses_read_only_connection(self):
        """Verify find_by_structure uses read-only SQLite connection."""
        with patch('mcp_server.server._get_state_db_path', return_value=':memory:'), \
             patch('sqlite3.connect') as mock_connect:
            
            from mcp_server.server import find_by_structure
            
            # Mock successful connection
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn
            
            find_by_structure("*.py")
            
            # Verify connection was made with read-only mode
            assert mock_connect.called
            call_args = mock_connect.call_args[0][0]
            assert "mode=ro" in call_args


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
