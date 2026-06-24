import pytest
from unittest.mock import patch, MagicMock, mock_open, call
from pathlib import Path
import sqlite3
from sentinel import QdrantSentinel, index_point_dual_write


def test_index_point_dual_write_success():
    """Test that index_point_dual_write calls both Qdrant and OpenViking."""
    # Setup mocks
    mock_qdrant = MagicMock()
    mock_ov = MagicMock()
    mock_ov.add_resource.return_value = {'id': 'ov_123'}
    mock_conn = MagicMock()
    
    # Create a test point
    point = {
        'id': 'test123',
        'vector': [0.1, 0.2, 0.3],
        'payload': {'text': 'test content', 'file_path': 'test.py'}
    }
    
    # Call dual-write function
    result = index_point_dual_write(point, mock_qdrant, mock_ov, mock_conn)
    
    # Verify both were called
    assert mock_qdrant.upsert.call_count == 1, "Qdrant upsert should be called once"
    assert mock_ov.add_resource.call_count == 1, "OpenViking add_resource should be called once"
    assert result is True, "Dual-write should return True on success"
    
    # Verify Qdrant was called with correct parameters
    upsert_call = mock_qdrant.upsert.call_args
    assert upsert_call is not None, "Qdrant upsert should have been called"


def test_index_point_dual_write_openviking_fails_gracefully():
    """Test that Qdrant succeeds even if OpenViking fails."""
    # Setup mocks
    mock_qdrant = MagicMock()
    mock_ov = MagicMock()
    mock_ov.add_resource.side_effect = Exception("OpenViking unavailable")
    mock_conn = MagicMock()
    
    # Create a test point
    point = {
        'id': 'test123',
        'vector': [0.1, 0.2, 0.3],
        'payload': {'text': 'test content', 'file_path': 'test.py'}
    }
    
    # Call dual-write function - should not raise exception
    result = index_point_dual_write(point, mock_qdrant, mock_ov, mock_conn)
    
    # Verify Qdrant was still called (graceful degradation)
    assert mock_qdrant.upsert.call_count == 1, "Qdrant upsert should still be called"
    assert mock_ov.add_resource.call_count == 1, "OpenViking add_resource should be attempted"
    # Result should still be True because Qdrant succeeded
    assert result is True, "Dual-write should return True if Qdrant succeeds"


def test_index_point_dual_write_qdrant_fails_rolls_back():
    """Test that if Qdrant fails, nothing is written to SQLite."""
    # Setup mocks
    mock_qdrant = MagicMock()
    mock_qdrant.upsert.side_effect = Exception("Qdrant unavailable")
    mock_ov = MagicMock()
    mock_conn = MagicMock()
    
    # Create a test point
    point = {
        'id': 'test123',
        'vector': [0.1, 0.2, 0.3],
        'payload': {'text': 'test content', 'file_path': 'test.py'}
    }
    
    # Call dual-write function
    result = index_point_dual_write(point, mock_qdrant, mock_ov, mock_conn)
    
    # Verify Qdrant was attempted
    assert mock_qdrant.upsert.call_count == 1, "Qdrant upsert should be attempted"
    
    # Verify OpenViking was NOT called (because Qdrant failed first)
    assert mock_ov.add_resource.call_count == 0, "OpenViking should not be called if Qdrant fails"
    
    # Verify SQLite insert was NOT called (atomicity)
    assert mock_conn.execute.call_count == 0, "SQLite insert should not be called if Qdrant fails"
    
    # Result should be False
    assert result is False, "Dual-write should return False if Qdrant fails"


def test_index_point_dual_write_stores_mapping():
    """Test that successful dual-write stores mapping in SQLite."""
    # Setup mocks
    mock_qdrant = MagicMock()
    mock_ov = MagicMock()
    mock_ov.add_resource.return_value = {'id': 'ov_123'}
    mock_conn = MagicMock()
    
    # Create a test point
    point = {
        'id': 'qdrant_id_123',
        'vector': [0.1, 0.2, 0.3],
        'payload': {'text': 'test content', 'file_path': 'test.py'}
    }
    
    # Call dual-write function
    result = index_point_dual_write(point, mock_qdrant, mock_ov, mock_conn)
    
    # Verify SQLite insert was called to store mapping
    assert mock_conn.execute.call_count > 0, "SQLite execute should be called"
    
    # Check that the insert was for the mapping table
    insert_calls = [str(call) for call in mock_conn.execute.call_args_list]
    assert any('INSERT INTO ov_mappings' in str(call) for call in insert_calls), \
        "Should insert into ov_mappings table"
    
    assert result is True, "Dual-write should return True on success"
