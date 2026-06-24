import pytest
from unittest.mock import Mock, MagicMock, patch
import sqlite3

# Assuming the function exists in a module, we'll import it or define it for testing
# For this test, we'll assume it's imported from the appropriate module
# from sentinel import get_status_report


@pytest.fixture
def mock_qdrant_client():
    """Fixture for mocked Qdrant client."""
    client = Mock()
    
    # Mock the count response object
    count_response = Mock()
    count_response.count = 100
    client.count.return_value = count_response
    
    return client


@pytest.fixture
def mock_sqlite_conn():
    """Fixture for mocked SQLite connection."""
    conn = Mock(spec=sqlite3.Connection)
    cursor = Mock(spec=sqlite3.Cursor)
    
    # Setup cursor to return single tuple with both values from optimized query
    # SELECT COUNT(*) as total, COUNT(qdrant_id) as mapped FROM ov_mappings
    # Returns (total=80, mapped=75)
    cursor.fetchone.return_value = (80, 75)
    conn.cursor.return_value = cursor
    
    return conn


def test_get_status_report_success(mock_qdrant_client, mock_sqlite_conn):
    """
    Test get_status_report returns correct status dictionary.
    
    Expected:
    - Total Qdrant Points: 100 (from mock)
    - Total OpenViking Resources: 80 (from mock)
    - Mapped Count: 75 (from mock)
    - Unmapped Qdrant Count: 100 - 75 = 25
    """
    from sentinel import get_status_report
    
    result = get_status_report(mock_qdrant_client, mock_sqlite_conn)  # conn param name in test, sqlite_conn in function
    
    # Verify the structure
    assert isinstance(result, dict)
    assert set(result.keys()) == {
        "total_qdrant_points",
        "total_ov_resources",
        "mapped_count",
        "unmapped_qdrant_count"
    }
    
    # Verify the values
    assert result["total_qdrant_points"] == 100
    assert result["total_ov_resources"] == 80
    assert result["mapped_count"] == 75
    assert result["unmapped_qdrant_count"] == 25
    
    # Verify Qdrant client was called once
    mock_qdrant_client.count.assert_called_once()
    
    # Verify SQLite cursor was called once (optimized single query)
    mock_cursor = mock_sqlite_conn.cursor.return_value
    assert mock_cursor.execute.call_count == 1


def test_get_status_report_empty_mappings(mock_qdrant_client, mock_sqlite_conn):
    """
    Test get_status_report with no mappings in database.
    """
    from sentinel import get_status_report
    
    # Override cursor return_value for empty results
    mock_cursor = mock_sqlite_conn.cursor.return_value
    mock_cursor.fetchone.return_value = (0, 0)
    
    result = get_status_report(mock_qdrant_client, mock_sqlite_conn)
    
    assert result["total_qdrant_points"] == 100
    assert result["total_ov_resources"] == 0
    assert result["mapped_count"] == 0
    assert result["unmapped_qdrant_count"] == 100


def test_get_status_report_perfect_mapping(mock_qdrant_client, mock_sqlite_conn):
    """
    Test get_status_report where all Qdrant points are mapped.
    """
    from sentinel import get_status_report
    
    # Override cursor return_value for perfect mapping
    mock_cursor = mock_sqlite_conn.cursor.return_value
    mock_cursor.fetchone.return_value = (100, 100)
    
    result = get_status_report(mock_qdrant_client, mock_sqlite_conn)
    
    assert result["total_qdrant_points"] == 100
    assert result["total_ov_resources"] == 100
    assert result["mapped_count"] == 100
    assert result["unmapped_qdrant_count"] == 0
