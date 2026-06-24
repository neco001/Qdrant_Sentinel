# test_dual_write_pipeline.py

import pytest
import sys
from unittest.mock import MagicMock, patch, call
from pathlib import Path
import sqlite3

# Mock the modules before importing sentinel
mock_qdrant = MagicMock()
mock_qdrant_http = MagicMock()
mock_qdrant_http.models = MagicMock()
sys.modules['qdrant_client'] = mock_qdrant
sys.modules['qdrant_client.http'] = mock_qdrant_http
sys.modules['qdrant_client.models'] = mock_qdrant_http.models
sys.modules['openai'] = MagicMock()

import sentinel
from openviking_client import OpenVikingClient as OVClient


@pytest.fixture
def mock_qdrant_client():
    """Mock Qdrant client with upsert method."""
    client = MagicMock()
    client.upsert.return_value = None
    return client


@pytest.fixture
def mock_openviking_client():
    """Mock OpenVikingClient with add_resource method."""
    client = MagicMock(spec=OVClient)
    client.add_resource.return_value = "ov_resource_123"
    return client


@pytest.fixture
def mock_sqlite_conn():
    """Mock SQLite connection for ov_mappings table."""
    conn = MagicMock(spec=sqlite3.Connection)
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    cursor.execute.return_value = None
    cursor.fetchone.return_value = None
    return conn


@pytest.fixture
def sample_point():
    """Sample Qdrant point structure."""
    return {
        "id": "qdrant_id_456",
        "vector": [0.1] * 1024,
        "payload": {
            "file_path": "test.py",
            "content": "def test(): pass",
            "language": "python"
        }
    }


class TestDualWritePipeline:
    """Test suite for dual-write indexing pipeline (Qdrant + OpenViking)."""

    def test_successful_dual_write_stores_mapping(
        self, mock_qdrant_client, mock_openviking_client, mock_sqlite_conn, sample_point
    ):
        """Verify successful write to both Qdrant and OpenViking stores mapping in SQLite."""
        qdrant_id = sample_point["id"]
        ov_resource_id = "ov_res_abc"
        
        mock_openviking_client.add_resource.return_value = ov_resource_id
        
        # Simulate the dual-write operation
        with patch('sentinel.get_db_connection', return_value=mock_sqlite_conn):
            result = sentinel.index_point_dual_write(
                point=sample_point,
                qdrant_client=mock_qdrant_client,
                ov_client=mock_openviking_client,
                conn=mock_sqlite_conn
            )
        
        # Verify Qdrant upsert was called
        mock_qdrant_client.upsert.assert_called_once()
        
        # Verify OpenViking add_resource was called
        mock_openviking_client.add_resource.assert_called_once()
        
        # Verify SQLite mapping was inserted
        insert_calls = [
            c for c in mock_sqlite_conn.execute.call_args_list
            if "INSERT INTO ov_mappings" in str(c)
        ]
        assert len(insert_calls) > 0
        mock_sqlite_conn.commit.assert_called_once()

    def test_openviking_failure_qdrant_succeeds(
        self, mock_qdrant_client, mock_openviking_client, mock_sqlite_conn, sample_point
    ):
        """Verify graceful degradation: Qdrant succeeds even if OpenViking fails."""
        # Simulate OpenViking failure
        mock_openviking_client.add_resource.side_effect = Exception("OpenViking unavailable")
        
        with patch('sentinel.get_db_connection', return_value=mock_sqlite_conn):
            result = sentinel.index_point_dual_write(
                point=sample_point,
                qdrant_client=mock_qdrant_client,
                ov_client=mock_openviking_client,
                conn=mock_sqlite_conn
            )
        
        # Verify Qdrant still succeeded
        mock_qdrant_client.upsert.assert_called_once()
        
        # Verify no mapping was stored (atomicity)
        insert_calls = [
            c for c in mock_sqlite_conn.execute.call_args_list
            if "INSERT INTO ov_mappings" in str(c)
        ]
        assert len(insert_calls) == 0

    def test_sqlite_mapping_atomicity_on_failure(
        self, mock_qdrant_client, mock_openviking_client, mock_sqlite_conn, sample_point
    ):
        """Verify SQLite mapping is atomic: if insert fails, Qdrant write is rolled back."""
        qdrant_id = sample_point["id"]
        ov_resource_id = "ov_res_xyz"
        
        mock_openviking_client.add_resource.return_value = ov_resource_id
        
        # Simulate SQLite insert failure
        mock_sqlite_conn.execute.side_effect = sqlite3.IntegrityError("Constraint failed")
        
        with patch('sentinel.get_db_connection', return_value=mock_sqlite_conn):
            with pytest.raises(sqlite3.IntegrityError):
                sentinel.index_point_dual_write(
                    point=sample_point,
                    qdrant_client=mock_qdrant_client,
                    ov_client=mock_openviking_client,
                    conn=mock_sqlite_conn
                )
        
        # Verify OpenViking was called (before SQLite failure)
        mock_openviking_client.add_resource.assert_called_once()
        
        # Verify Qdrant delete was called for rollback
        mock_qdrant_client.delete.assert_called_once()

    def test_retrieve_mapping_by_qdrant_id(
        self, mock_sqlite_conn
    ):
        """Verify retrieving OpenViking resource ID by Qdrant ID."""
        qdrant_id = "qdrant_123"
        ov_resource_id = "ov_456"
        
        cursor = mock_sqlite_conn.cursor.return_value
        cursor.fetchone.return_value = (ov_resource_id,)
        
        with patch('sentinel.get_db_connection', return_value=mock_sqlite_conn):
            result = sentinel.get_ov_mapping(qdrant_id, mock_sqlite_conn)
        
        assert result == ov_resource_id
        cursor.execute.assert_called_once_with(
            "SELECT ov_resource_id FROM ov_mappings WHERE qdrant_id = ?",
            (qdrant_id,)
        )

    def test_retrieve_mapping_by_ov_resource_id(
        self, mock_sqlite_conn
    ):
        """Verify retrieving Qdrant ID by OpenViking resource ID."""
        qdrant_id = "qdrant_789"
        ov_resource_id = "ov_101"
        
        cursor = mock_sqlite_conn.cursor.return_value
        cursor.fetchone.return_value = (qdrant_id,)
        
        with patch('sentinel.get_db_connection', return_value=mock_sqlite_conn):
            result = sentinel.get_qdrant_mapping(ov_resource_id, mock_sqlite_conn)
        
        assert result == qdrant_id
        cursor.execute.assert_called_once_with(
            "SELECT qdrant_id FROM ov_mappings WHERE ov_resource_id = ?",
            (ov_resource_id,)
        )
