import pytest
from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path
import sqlite3
from sentinel import QdrantSentinel


@pytest.fixture
def mock_clients():
    """Mock QdrantClient, OpenVikingClient, and SQLite connections."""
    with patch('sentinel.QdrantClient') as mock_qdrant, \
         patch('sentinel.OpenVikingClient') as mock_ov, \
         patch('sentinel.sqlite3.connect') as mock_sqlite:
        
        # Setup Qdrant mock
        mock_qdrant_instance = MagicMock()
        mock_qdrant_instance.collection_exists.return_value = False
        mock_qdrant.return_value = mock_qdrant_instance
        
        # Setup OpenViking mock
        mock_ov_instance = MagicMock()
        mock_ov_instance.add_resource.return_value = {'id': 'ov_123'}
        mock_ov.return_value = mock_ov_instance
        
        # Setup SQLite mock
        mock_sqlite_instance = MagicMock()
        mock_sqlite.return_value = mock_sqlite_instance
        
        yield {
            'qdrant': mock_qdrant_instance,
            'ov': mock_ov_instance,
            'sqlite': mock_sqlite_instance
        }


@pytest.fixture
def mock_file_content():
    """Mock file reading and AST parsing."""
    dummy_content = "def foo():\n    pass\n"
    
    with patch('builtins.open', mock_open(read_data=dummy_content)), \
         patch('sentinel.parse_file') as mock_parse, \
         patch('sentinel.extract_structural_nodes') as mock_extract, \
         patch('sentinel.build_chunks') as mock_chunks, \
         patch('sentinel.get_db_connection') as mock_db:
        
        # Mock parse_file to return None (fallback to simple chunking)
        mock_parse.return_value = None
        
        # Mock get_db_connection
        mock_db_conn = MagicMock()
        mock_db.return_value = mock_db_conn
        
        yield {
            'content': dummy_content,
            'parse': mock_parse,
            'extract': mock_extract,
            'chunks': mock_chunks,
            'db': mock_db_conn
        }


def test_index_file_calls_dual_write_successfully(mock_clients, mock_file_content):
    """Test that index_file calls index_point_dual_write for each chunk."""
    # Create a temporary test file
    test_file = Path("test_dummy.py")
    test_file.write_text("def foo():\n    pass\n")
    
    try:
        # Create QdrantSentinel instance
        sentinel = QdrantSentinel(watch_paths=[])
        
        # Mock index_point_dual_write to track calls
        with patch('sentinel.index_point_dual_write') as mock_dual_write:
            mock_dual_write.return_value = True  # Success
            
            # Call index_file
            sentinel.index_file(test_file, Path.cwd())
            
            # Verify dual_write was called
            assert mock_dual_write.call_count > 0, "index_point_dual_write should be called"
            
            # Verify each call had correct parameters
            for call in mock_dual_write.call_args_list:
                args, kwargs = call
                point = args[0]
                assert 'id' in point
                assert 'vector' in point
                assert 'payload' in point
    finally:
        # Cleanup
        if test_file.exists():
            test_file.unlink()


def test_index_file_graceful_degradation_on_openviking_failure(mock_clients, mock_file_content):
    """Test graceful degradation when OpenViking fails but continues with Qdrant."""
    # Create a temporary test file
    test_file = Path("test_dummy.py")
    test_file.write_text("def foo():\n    pass\n")
    
    try:
        # Create QdrantSentinel instance
        sentinel = QdrantSentinel(watch_paths=[])
        
        # Mock index_point_dual_write to simulate OpenViking failure
        with patch('sentinel.index_point_dual_write') as mock_dual_write:
            mock_dual_write.return_value = False  # OpenViking failed, but Qdrant succeeded
            
            # Call index_file - should not raise exception
            sentinel.index_file(test_file, Path.cwd())
            
            # Verify dual_write was still called
            assert mock_dual_write.call_count > 0
            
            # Verify operation completed without raising exception
            # (If it raised, test would have failed here)
    finally:
        # Cleanup
        if test_file.exists():
            test_file.unlink()
