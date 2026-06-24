import pytest
import sqlite3
import tempfile
from pathlib import Path

@pytest.fixture
def temp_db_path():
    """Create a temporary database file path."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield Path(f.name)
    # Cleanup handled by tempfile

def test_ov_mappings_table_created_in_init_db(temp_db_path):
    """Test that init_db creates the ov_mappings table."""
    # Monkey-patch the STATE_DB_PATH to use temp database
    import sentinel
    original_db_path = sentinel.STATE_DB_PATH
    sentinel.STATE_DB_PATH = str(temp_db_path)
    
    try:
        # Create QdrantSentinel instance which calls init_db
        qs = sentinel.QdrantSentinel([])
        
        # Verify ov_mappings table exists
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='ov_mappings'
        """)
        result = cursor.fetchone()
        assert result is not None, "ov_mappings table should exist"
        
        # Verify schema
        cursor.execute("PRAGMA table_info(ov_mappings)")
        columns = {row[1]: row for row in cursor.fetchall()}
        
        assert 'qdrant_id' in columns
        assert columns['qdrant_id'][2] == 'TEXT'  # type
        assert columns['qdrant_id'][5] == 1      # pk (1 = primary key)
        
        assert 'ov_resource_id' in columns
        assert columns['ov_resource_id'][2] == 'TEXT'
        assert columns['ov_resource_id'][3] == 1  # notnull
        
        assert 'file_path' in columns
        assert columns['file_path'][2] == 'TEXT'
        assert columns['file_path'][3] == 1      # notnull
        
        assert 'created_at' in columns
        assert columns['created_at'][2] == 'TIMESTAMP'
        
        conn.close()
    finally:
        # Restore original DB path
        sentinel.STATE_DB_PATH = original_db_path

def test_ov_mappings_idempotency(temp_db_path):
    """Test that creating QdrantSentinel twice doesn't fail (idempotency)."""
    import sentinel
    original_db_path = sentinel.STATE_DB_PATH
    sentinel.STATE_DB_PATH = str(temp_db_path)
    
    try:
        # First creation
        qs1 = sentinel.QdrantSentinel([])
        
        # Second creation should not raise an error
        qs2 = sentinel.QdrantSentinel([])
        
        # Verify table still exists and is intact
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM ov_mappings")
        assert cursor.fetchone()[0] == 0  # Empty but exists
        conn.close()
    finally:
        sentinel.STATE_DB_PATH = original_db_path

def test_existing_file_states_untouched(temp_db_path):
    """Test that creating ov_mappings doesn't affect existing file_states table."""
    import sentinel
    original_db_path = sentinel.STATE_DB_PATH
    sentinel.STATE_DB_PATH = str(temp_db_path)
    
    try:
        # First, create file_states table manually
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS file_states (
                file_path TEXT PRIMARY KEY,
                hash TEXT,
                last_indexed REAL,
                collection_name TEXT
            )
        """)
        
        # Insert data into file_states before creating QdrantSentinel
        cursor.execute("""
            INSERT INTO file_states (file_path, last_indexed)
            VALUES ('test.py', 123456.0)
        """)
        conn.commit()
        conn.close()
        
        # Create QdrantSentinel which should add ov_mappings
        qs = sentinel.QdrantSentinel([])
        
        # Verify file_states still exists and has data
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM file_states")
        assert cursor.fetchone()[0] == 1
        
        cursor.execute("SELECT file_path FROM file_states WHERE file_path = 'test.py'")
        assert cursor.fetchone()[0] == 'test.py'
        conn.close()
    finally:
        sentinel.STATE_DB_PATH = original_db_path
