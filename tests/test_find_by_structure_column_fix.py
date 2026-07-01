"""TDD test for find_by_structure SQLite column mismatch fix."""
import pytest
from unittest.mock import patch, MagicMock
import sqlite3
from pathlib import Path
import tempfile


@pytest.fixture(autouse=True)
def reset_mcp_state():
    """Reset MCP server state before each test."""
    from mcp_server.server import reset_state
    reset_state()
    yield


@pytest.fixture
def mock_config_with_db():
    """Mock config with real temp SQLite DB."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = tmp.name
    tmp.close()

    # Create the ov_mappings table with the actual schema (created_at, NOT indexed_at)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ov_mappings (
                qdrant_id TEXT PRIMARY KEY,
                ov_resource_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ov_resource ON ov_mappings(ov_resource_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ov_file ON ov_mappings(file_path)")
        conn.execute("""
            INSERT INTO ov_mappings (qdrant_id, ov_resource_id, file_path, created_at)
            VALUES ('abc-123', 'file:///test.py', 'test.py', '2025-01-01 00:00:00')
        """)
        conn.execute("""
            INSERT INTO ov_mappings (qdrant_id, ov_resource_id, file_path, created_at)
            VALUES ('def-456', 'file:///src/main.py', 'src/main.py', '2025-01-02 00:00:00')
        """)
        conn.commit()
    finally:
        conn.close()

    config = MagicMock()
    config.paths.state_db = db_path
    return config


class TestFindByStructureColumnMismatch:
    """Tests that verify find_by_structure uses correct column name."""

    def test_find_by_structure_uses_created_at_not_indexed_at(self, mock_config_with_db):
        """find_by_structure must query 'created_at' column, not non-existent 'indexed_at'."""
        with patch('mcp_server.server._load_config', return_value=mock_config_with_db), \
             patch('mcp_server.server._get_config', return_value=mock_config_with_db):

            from mcp_server.server import find_by_structure

            # This will raise sqlite3.OperationalError if code queries 'indexed_at'
            result = find_by_structure("test.py")

            assert len(result) == 1
            assert result[0]['qdrant_id'] == 'abc-123'
            assert result[0]['uri'] == 'file:///test.py'
            assert 'created_at' in result[0], "Result must have 'created_at' key"
            assert result[0]['created_at'] == '2025-01-01 00:00:00'

    def test_find_by_structure_wildcard_pattern(self, mock_config_with_db):
        """find_by_structure must handle wildcard patterns correctly."""
        with patch('mcp_server.server._load_config', return_value=mock_config_with_db), \
             patch('mcp_server.server._get_config', return_value=mock_config_with_db):

            from mcp_server.server import find_by_structure

            result = find_by_structure("src/*.py")

            assert len(result) == 1
            assert result[0]['qdrant_id'] == 'def-456'
            assert 'created_at' in result[0]

    def test_find_by_structure_no_matches(self, mock_config_with_db):
        """find_by_structure must return empty list when no matches."""
        with patch('mcp_server.server._load_config', return_value=mock_config_with_db), \
             patch('mcp_server.server._get_config', return_value=mock_config_with_db):

            from mcp_server.server import find_by_structure

            result = find_by_structure("nonexistent/*.js")
            assert result == []
