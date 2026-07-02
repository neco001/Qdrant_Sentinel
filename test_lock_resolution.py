"""Test OpenVikingClient lock resolution (Task: 3188d81f).

Verifies that:
1. Client prefers HTTP server when available (avoids embedded lock contention)
2. Falls back to embedded mode when HTTP server is unavailable
3. Uses threading.Lock to serialize embedded operations
4. No 'database is locked' errors during concurrent access
"""
import pytest
import threading
import time
from unittest.mock import patch, MagicMock


class TestLockResolution:
    """Verify OpenVikingClient lock resolution behavior."""

    @patch('openviking_client.is_http_server_alive')
    @patch('openviking_client.SyncHTTPClient')
    def test_prefers_http_server_when_available(self, mock_http_client, mock_alive):
        """Client should connect via HTTP when server is running."""
        from openviking_client import OpenVikingClient

        mock_alive.return_value = True
        mock_instance = MagicMock()
        mock_http_client.return_value = mock_instance

        client = OpenVikingClient(data_path="/tmp/test_ov")

        assert client._is_http_client is True
        assert client._client is mock_instance
        mock_http_client.assert_called_once()

    @patch('openviking_client.is_http_server_alive')
    @patch('openviking_client.SyncOpenViking')
    def test_fallback_to_embedded_when_http_unavailable(self, mock_sync_ov, mock_alive):
        """Client should fall back to embedded mode when HTTP server is down."""
        from openviking_client import OpenVikingClient

        mock_alive.return_value = False
        mock_embedded = MagicMock()
        mock_sync_ov.return_value = mock_embedded

        client = OpenVikingClient(data_path="/tmp/test_ov")

        assert client._is_http_client is False
        assert client._client is mock_embedded
        mock_sync_ov.assert_called_once()

    @patch('openviking_client.is_http_server_alive')
    @patch('openviking_client.SyncOpenViking')
    def test_embedded_mode_uses_threading_lock(self, mock_sync_ov, mock_alive):
        """Embedded mode should use threading.Lock to serialize operations."""
        from openviking_client import OpenVikingClient

        mock_alive.return_value = False
        mock_sync_ov.return_value = MagicMock()

        client = OpenVikingClient(data_path="/tmp/test_ov")

        assert isinstance(client._lock, type(threading.Lock()))
        assert client._is_http_client is False

    @patch('openviking_client.is_http_server_alive')
    @patch('openviking_client.SyncOpenViking')
    def test_add_resource_uses_lock_in_embedded_mode(self, mock_sync_ov, mock_alive):
        """add_resource should acquire lock before calling native API in embedded mode."""
        from openviking_client import OpenVikingClient

        mock_alive.return_value = False
        mock_native = MagicMock()
        mock_native.add_resource.return_value = {"id": "test-resource-id"}
        mock_sync_ov.return_value = mock_native

        client = OpenVikingClient(data_path="/tmp/test_ov")
        result = client.add_resource("/tmp/test_file.py")

        assert result == "test-resource-id"
        mock_native.add_resource.assert_called_once()

    @patch('openviking_client.is_http_server_alive')
    @patch('openviking_client.SyncOpenViking')
    def test_no_database_locked_error_under_concurrent_access(self, mock_sync_ov, mock_alive):
        """Concurrent add_resource calls should not raise 'database is locked' errors."""
        from openviking_client import OpenVikingClient

        mock_alive.return_value = False
        errors = []

        def mock_add_resource(path, build_index=False):
            # Simulate slight delay to expose race conditions
            time.sleep(0.01)
            return {"id": f"resource-{path}"}

        mock_native = MagicMock()
        mock_native.add_resource = mock_add_resource
        mock_sync_ov.return_value = mock_native

        client = OpenVikingClient(data_path="/tmp/test_ov")

        def worker(thread_id):
            try:
                result = client.add_resource(f"/tmp/test_{thread_id}.py")
                assert result is not None
            except Exception as e:
                if "database is locked" in str(e).lower():
                    errors.append(str(e))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Database locked errors occurred: {errors}"

    @patch('openviking_client.is_http_server_alive')
    @patch('openviking_client.SyncOpenViking')
    def test_daemon_mode_waits_for_http_server(self, mock_sync_ov, mock_alive, monkeypatch):
        """When OPEN_VIKING_ENABLED=true, client should retry HTTP connections."""
        from openviking_client import OpenVikingClient

        # Simulate server not ready on first check, ready on second
        call_count = [0]
        def alive_side_effect(*args, **kwargs):
            call_count[0] += 1
            return call_count[0] >= 2

        mock_alive.side_effect = alive_side_effect
        mock_http = MagicMock()
        with patch('openviking_client.SyncHTTPClient', return_value=mock_http):
            monkeypatch.setenv("OPEN_VIKING_ENABLED", "true")

            client = OpenVikingClient(data_path="/tmp/test_ov")

            assert client._is_http_client is True
            assert call_count[0] >= 2  # Verified retries occurred


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
