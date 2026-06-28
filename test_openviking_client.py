# test_openviking_client.py - Updated for native SyncOpenViking API
# Backward compatible test suite migrated from subprocess CLI to native embedded mode

import pytest
import warnings
from unittest.mock import patch, MagicMock
from openviking_client import OpenVikingClient


class TestOpenVikingClient:
    """Test suite for OpenVikingClient wrapper functionality (native SyncOpenViking mode)."""

    @patch('openviking_client.SyncOpenViking')
    def test_instantiation(self, mock_sync_openviking: MagicMock):
        """Test that OpenVikingClient can be instantiated with default config."""
        mock_instance = MagicMock()
        mock_sync_openviking.return_value = mock_instance

        client = OpenVikingClient()
        assert client is not None
        assert client.cli_path == "ov"  # Backward compat: default cli_path property
        mock_sync_openviking.assert_called_once_with(path="./openviking_data")

    @patch('openviking_client.SyncOpenViking')
    def test_instantiation_with_custom_path(self, mock_sync_openviking: MagicMock):
        """Test instantiation with deprecated cli_path parameter (backward compatibility)."""
        mock_instance = MagicMock()
        mock_sync_openviking.return_value = mock_instance

        # cli_path is deprecated but should still be stored for property inspection
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            client = OpenVikingClient(cli_path="/custom/path/to/ov")

            # Verify deprecation warning was issued
            assert len(w) == 1
            assert issubclass(w[-1].category, DeprecationWarning)
            assert "cli_path" in str(w[-1].message).lower()

        # Backward compat: cli_path property returns the provided deprecated path
        assert client.cli_path == "/custom/path/to/ov"
        # But SyncOpenViking was initialized with default data_path
        mock_sync_openviking.assert_called_once_with(path="./openviking_data")

    @patch('openviking_client.SyncOpenViking')
    def test_add_resource_success(self, mock_sync_openviking: MagicMock):
        """Test add_resource() returns a resource_id on success using native API."""
        mock_instance = MagicMock()
        mock_sync_openviking.return_value = mock_instance
        mock_instance.add_resource.return_value = {"id": "resource-12345"}

        client = OpenVikingClient()
        resource_id = client.add_resource(
            path="test-resource",
            wait=False
        )

        assert resource_id == "resource-12345"
        mock_instance.add_resource.assert_called_once_with("test-resource")

    @patch('openviking_client.SyncOpenViking')
    def test_find_resources_success(self, mock_sync_openviking: MagicMock):
        """Test find_resources() returns parsed results on success using native API."""
        mock_instance = MagicMock()
        mock_sync_openviking.return_value = mock_instance

        # Mock find() returning an iterable of dict-like objects
        mock_find_result_1 = MagicMock()
        mock_find_result_1.__dict__ = {"id": "res-1", "name": "service-a"}
        mock_instance.find.return_value = [mock_find_result_1]

        client = OpenVikingClient()
        results = client.find_resources(query="service-a")

        assert len(results) == 1
        assert results[0]["id"] == "res-1"
        assert results[0]["name"] == "service-a"
        mock_instance.find.assert_called_once_with("service-a")

    @patch('openviking_client.SyncOpenViking')
    def test_graceful_degradation_syncopenviking_fails_to_init(self, mock_sync_openviking: MagicMock):
        """Test graceful degradation when SyncOpenViking fails to initialize (replaces CLI not found test)."""
        # Simulate SyncOpenViking raising an exception during init
        mock_sync_openviking.side_effect = RuntimeError("Failed to initialize OpenViking native engine")

        client = OpenVikingClient()

        # Should not crash, client._client should be None (degraded mode)
        resource_id = client.add_resource(path="test", wait=False)
        assert resource_id is None

        results = client.find_resources(query="test")
        assert results == []

    @patch('openviking_client.SyncOpenViking')
    def test_error_handling_add_resource_raises_exception(self, mock_sync_openviking: MagicMock):
        """Test that native API exceptions are caught and handled gracefully."""
        mock_instance = MagicMock()
        mock_sync_openviking.return_value = mock_instance
        mock_instance.add_resource.side_effect = RuntimeError("Native add_resource failed: invalid path")

        client = OpenVikingClient()

        # Should not crash, return None
        resource_id = client.add_resource(path="test", wait=False)
        assert resource_id is None

    @patch('openviking_client.SyncOpenViking')
    def test_error_handling_find_resources_raises_exception(self, mock_sync_openviking: MagicMock):
        """Test handling of exceptions in native find_resources (replaces malformed JSON test)."""
        mock_instance = MagicMock()
        mock_sync_openviking.return_value = mock_instance
        mock_instance.find.side_effect = RuntimeError("Native find failed: query syntax error")

        client = OpenVikingClient()
        results = client.find_resources(query="test")

        # Should return empty list on error
        assert results == []
