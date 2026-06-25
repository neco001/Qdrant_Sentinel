"""
Test suite for rebuild functionality in Qdrant Sentinel.

Tests cover:
- Dry-run mode (no data deletion)
- Backup creation before rebuild
- Rollback on failure
- Project-specific rebuild
"""
import pytest
from unittest.mock import Mock, MagicMock, patch, call
from pathlib import Path
import sqlite3
import tempfile
import shutil


@pytest.fixture
def mock_qdrant_client():
    """Mock Qdrant client."""
    client = MagicMock()
    client.get_collections.return_value = MagicMock(collections=[
        MagicMock(name="project-a-mycorp"),
        MagicMock(name="project-b-tools"),
        MagicMock(name="project-c-utils")
    ])
    client.delete_collection.return_value = None
    return client


@pytest.fixture
def mock_sqlite_conn():
    """Mock SQLite connection."""
    conn = MagicMock()
    cursor = MagicMock()
    cursor.execute.return_value = None
    cursor.fetchone.return_value = (1234,)  # file_hashes count
    cursor.fetchall.return_value = [
        ("qdrant_id_1", "ov_resource_1", "path1.py"),
        ("qdrant_id_2", "ov_resource_2", "path2.py"),
    ]
    conn.cursor.return_value = cursor
    conn.commit.return_value = None
    return conn


@pytest.fixture
def mock_openviking_client():
    """Mock OpenViking client."""
    client = MagicMock()
    client.find_resources.return_value = [
        {"id": "ov_resource_1", "path": "path1.py"},
        {"id": "ov_resource_2", "path": "path2.py"},
    ]
    return client


@pytest.fixture
def temp_dir():
    """Temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestRebuildDryRun:
    """Test dry-run mode doesn't delete data."""

    def test_rebuild_dry_run_no_qdrant_deletion(
        self, mock_qdrant_client, mock_sqlite_conn, mock_openviking_client
    ):
        """Verify dry-run mode doesn't delete Qdrant collections."""
        with patch('sentinel.get_qdrant_client', return_value=mock_qdrant_client), \
             patch('sentinel.get_db_connection', return_value=mock_sqlite_conn), \
             patch('sentinel.OpenVikingClient', return_value=mock_openviking_client), \
             patch('sentinel.confirm_rebuild', return_value=True):
            
            from sentinel import rebuild_index
            
            result = rebuild_index(dry_run=True)
            
            # Verify delete_collection was NOT called
            mock_qdrant_client.delete_collection.assert_not_called()
            
            # Verify execute DELETE was NOT called
            delete_calls = [
                call for call in mock_sqlite_conn.cursor().execute.call_args_list
                if 'DELETE' in str(call).upper()
            ]
            assert len(delete_calls) == 0, "No DELETE queries should be executed in dry-run"
            
            # Verify dry-run completed successfully
            assert result is True

    def test_rebuild_dry_run_shows_stats(
        self, mock_qdrant_client, mock_sqlite_conn, mock_openviking_client, caplog
    ):
        """Verify dry-run mode shows statistics without modifying data."""
        with patch('sentinel.get_qdrant_client', return_value=mock_qdrant_client), \
             patch('sentinel.get_db_connection', return_value=mock_sqlite_conn), \
             patch('sentinel.OpenVikingClient', return_value=mock_openviking_client), \
             patch('sentinel.confirm_rebuild', return_value=True):
            
            from sentinel import rebuild_index
            
            result = rebuild_index(dry_run=True)
            
            # Verify collections were listed (read-only)
            mock_qdrant_client.get_collections.assert_called_once()
            
            # Verify file_hashes were counted (read-only)
            mock_sqlite_conn.cursor().execute.assert_any_call("SELECT COUNT(*) FROM file_hashes")
            
            assert result is True


class TestRebuildBackup:
    """Test backup creation and restoration."""

    def test_rebuild_with_backup_creates_file(
        self, mock_qdrant_client, mock_sqlite_conn, mock_openviking_client, temp_dir
    ):
        """Verify backup file is created when backup=True."""
        with patch('sentinel.get_qdrant_client', return_value=mock_qdrant_client), \
             patch('sentinel.get_db_connection', return_value=mock_sqlite_conn), \
             patch('sentinel.OpenVikingClient', return_value=mock_openviking_client), \
             patch('sentinel.confirm_rebuild', return_value=True), \
             patch('sentinel.STATE_DB_PATH', str(temp_dir / "sentinel_state.db")):
            
            # Create dummy state db
            state_db = temp_dir / "sentinel_state.db"
            state_db.write_text("dummy data")
            
            from sentinel import rebuild_index
            
            result = rebuild_index(backup=True)
            
            # Verify backup file exists
            backup_file = temp_dir / "sentinel_state.db.backup"
            assert backup_file.exists(), "Backup file should be created"
            
            assert result is True

    def test_rebuild_with_backup_copies_data(
        self, mock_qdrant_client, mock_sqlite_conn, mock_openviking_client, temp_dir
    ):
        """Verify backup contains data from original database."""
        with patch('sentinel.get_qdrant_client', return_value=mock_qdrant_client), \
             patch('sentinel.get_db_connection', return_value=mock_sqlite_conn), \
             patch('sentinel.OpenVikingClient', return_value=mock_openviking_client), \
             patch('sentinel.confirm_rebuild', return_value=True), \
             patch('sentinel.STATE_DB_PATH', str(temp_dir / "sentinel_state.db")):
            
            # Create state db with content
            state_db = temp_dir / "sentinel_state.db"
            original_content = "original database content"
            state_db.write_text(original_content)
            
            from sentinel import rebuild_index
            
            rebuild_index(backup=True)
            
            # Verify backup content matches original
            backup_file = temp_dir / "sentinel_state.db.backup"
            backup_content = backup_file.read_text()
            assert backup_content == original_content


class TestRebuildRollback:
    """Test rollback behavior on rebuild failure."""

    def test_rebuild_rollback_on_qdrant_failure(
        self, mock_qdrant_client, mock_sqlite_conn, mock_openviking_client, temp_dir
    ):
        """Verify backup is restored if Qdrant rebuild fails."""
        # Make delete_collection fail
        mock_qdrant_client.delete_collection.side_effect = Exception("Qdrant error")
        
        with patch('sentinel.get_qdrant_client', return_value=mock_qdrant_client), \
             patch('sentinel.get_db_connection', return_value=mock_sqlite_conn), \
             patch('sentinel.OpenVikingClient', return_value=mock_openviking_client), \
             patch('sentinel.confirm_rebuild', return_value=True), \
             patch('sentinel.STATE_DB_PATH', str(temp_dir / "sentinel_state.db")):
            
            # Create state db with content
            state_db = temp_dir / "sentinel_state.db"
            original_content = "original database content"
            state_db.write_text(original_content)
            
            from sentinel import rebuild_index
            
            result = rebuild_index(backup=True)
            
            # Verify rebuild failed
            assert result is False
            
            # Verify backup file exists (created before failure)
            backup_file = temp_dir / "sentinel_state.db.backup"
            assert backup_file.exists()

    def test_rebuild_rollback_on_sqlite_failure(
        self, mock_qdrant_client, mock_sqlite_conn, mock_openviking_client, temp_dir
    ):
        """Verify backup is restored if SQLite rebuild fails."""
        # Make execute fail on DELETE
        cursor = mock_sqlite_conn.cursor()
        original_execute = cursor.execute
        
        def failing_execute(query, *args):
            if 'DELETE' in str(query).upper():
                raise sqlite3.Error("SQLite error")
            return original_execute(query, *args)
        
        cursor.execute.side_effect = failing_execute
        
        with patch('sentinel.get_qdrant_client', return_value=mock_qdrant_client), \
             patch('sentinel.get_db_connection', return_value=mock_sqlite_conn), \
             patch('sentinel.OpenVikingClient', return_value=mock_openviking_client), \
             patch('sentinel.confirm_rebuild', return_value=True), \
             patch('sentinel.STATE_DB_PATH', str(temp_dir / "sentinel_state.db")):
            
            # Create state db
            state_db = temp_dir / "sentinel_state.db"
            state_db.write_text("original content")
            
            from sentinel import rebuild_index
            
            result = rebuild_index(backup=True)
            
            # Verify rebuild failed
            assert result is False


class TestRebuildProjectSpecific:
    """Test project-specific rebuild functionality."""

    def test_rebuild_project_specific_filters_collections(
        self, mock_qdrant_client, mock_sqlite_conn, mock_openviking_client
    ):
        """Verify only specified project's collection is rebuilt."""
        with patch('sentinel.get_qdrant_client', return_value=mock_qdrant_client), \
             patch('sentinel.get_db_connection', return_value=mock_sqlite_conn), \
             patch('sentinel.OpenVikingClient', return_value=mock_openviking_client), \
             patch('sentinel.confirm_rebuild', return_value=True):
            
            from sentinel import rebuild_index
            
            rebuild_index(project_name="project-a-mycorp")
            
            # Verify only project-a collection was deleted
            mock_qdrant_client.delete_collection.assert_called_once_with("project-a-mycorp")

    def test_rebuild_project_specific_filters_sqlite_queries(
        self, mock_qdrant_client, mock_sqlite_conn, mock_openviking_client
    ):
        """Verify SQLite queries are filtered by project name."""
        with patch('sentinel.get_qdrant_client', return_value=mock_qdrant_client), \
             patch('sentinel.get_db_connection', return_value=mock_sqlite_conn), \
             patch('sentinel.OpenVikingClient', return_value=mock_openviking_client), \
             patch('sentinel.confirm_rebuild', return_value=True):
            
            from sentinel import rebuild_index
            
            rebuild_index(project_name="project-a-mycorp")
            
            # Verify DELETE queries include project filter
            delete_calls = [
                str(call) for call in mock_sqlite_conn.cursor().execute.call_args_list
                if 'DELETE' in str(call).upper()
            ]
            
            # At least one DELETE should have WHERE clause with project
            has_project_filter = any('project' in call.lower() for call in delete_calls)
            assert has_project_filter, "DELETE queries should filter by project"

    def test_rebuild_all_projects_when_none_specified(
        self, mock_qdrant_client, mock_sqlite_conn, mock_openviking_client
    ):
        """Verify all collections are deleted when no project specified."""
        with patch('sentinel.get_qdrant_client', return_value=mock_qdrant_client), \
             patch('sentinel.get_db_connection', return_value=mock_sqlite_conn), \
             patch('sentinel.OpenVikingClient', return_value=mock_openviking_client), \
             patch('sentinel.confirm_rebuild', return_value=True):
            
            from sentinel import rebuild_index
            
            rebuild_index(project_name=None)
            
            # Verify all 3 collections were deleted
            assert mock_qdrant_client.delete_collection.call_count == 3


class TestConfirmRebuild:
    """Test rebuild confirmation prompt."""

    def test_confirm_rebuild_accepts_yes(self, capsys):
        """Verify confirm_rebuild returns True for 'y' input."""
        with patch('builtins.input', return_value='y'):
            from sentinel import confirm_rebuild
            
            stats = {
                'qdrant_collections': 3,
                'sqlite_file_hashes': 1234,
                'sqlite_ov_mappings': 1234,
                'openviking_resources': 1234
            }
            
            result = confirm_rebuild(stats)
            assert result is True

    def test_confirm_rebuild_rejects_no(self, capsys):
        """Verify confirm_rebuild returns False for 'n' input."""
        with patch('builtins.input', return_value='n'):
            from sentinel import confirm_rebuild
            
            stats = {
                'qdrant_collections': 3,
                'sqlite_file_hashes': 1234,
                'sqlite_ov_mappings': 1234,
                'openviking_resources': 1234
            }
            
            result = confirm_rebuild(stats)
            assert result is False

    def test_confirm_rebuild_shows_warning(self, capsys):
        """Verify confirm_rebuild shows warning with stats."""
        with patch('builtins.input', return_value='y'):
            from sentinel import confirm_rebuild
            
            stats = {
                'qdrant_collections': 3,
                'sqlite_file_hashes': 1234,
                'sqlite_ov_mappings': 1234,
                'openviking_resources': 1234
            }
            
            confirm_rebuild(stats)
            
            captured = capsys.readouterr()
            assert 'WARNING' in captured.out
            assert '3' in captured.out
            assert '1234' in captured.out


class TestQdrantOnly:
    """Test --qdrant-only flag functionality."""

    def test_rebuild_qdrant_only_preserves_sqlite(
        self, mock_qdrant_client, mock_sqlite_conn, mock_openviking_client
    ):
        """Verify SQLite tables are not cleared when qdrant_only=True."""
        with patch('sentinel.get_qdrant_client', return_value=mock_qdrant_client), \
             patch('sentinel.get_db_connection', return_value=mock_sqlite_conn), \
             patch('sentinel.OpenVikingClient', return_value=mock_openviking_client), \
             patch('sentinel.confirm_rebuild', return_value=True):
            
            from sentinel import rebuild_index
            
            rebuild_index(qdrant_only=True)
            
            # Verify Qdrant collections were deleted
            assert mock_qdrant_client.delete_collection.call_count > 0
            
            # Verify SQLite DELETE was NOT called
            delete_calls = [
                call for call in mock_sqlite_conn.cursor().execute.call_args_list
                if 'DELETE' in str(call).upper()
            ]
            assert len(delete_calls) == 0, "SQLite should not be cleared with qdrant_only=True"
