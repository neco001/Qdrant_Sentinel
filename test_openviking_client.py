# tests/test_openvovking_client.py

import pytest
import subprocess
from unittest.mock import patch, MagicMock
from openviking_client import OpenVikingClient


class TestOpenVikingClient:
    """Test suite for OpenVikingClient wrapper functionality."""

    def test_instantiation(self):
        """Test that OpenVikingClient can be instantiated with default config."""
        client = OpenVikingClient()
        assert client is not None
        assert client.cli_path == "ov"

    def test_instantiation_with_custom_path(self):
        """Test instantiation with custom CLI path."""
        client = OpenVikingClient(cli_path="/custom/path/to/ov")
        assert client.cli_path == "/custom/path/to/ov"

    @patch('subprocess.run')
    def test_add_resource_success(self, mock_run):
        """Test add_resource() returns a resource_id on success."""
        # Mock successful subprocess response
        mock_result = MagicMock()
        mock_result.stdout = "resource-12345\n"
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        client = OpenVikingClient()
        resource_id = client.add_resource(
            name="test-resource",
            resource_type="service",
            tags=["test", "pytest"]
        )

        assert resource_id == "resource-12345"
        mock_run.assert_called_once()

    @patch('subprocess.run')
    def test_find_resources_success(self, mock_run):
        """Test find_resources() returns parsed results on success."""
        # Mock successful subprocess response with JSON output
        mock_result = MagicMock()
        mock_result.stdout = '[{"id": "res-1", "name": "service-a"}]\n'
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        client = OpenVikingClient()
        results = client.find_resources(query="service-a")

        assert len(results) == 1
        assert results[0]["id"] == "res-1"
        assert results[0]["name"] == "service-a"

    @patch('subprocess.run', side_effect=FileNotFoundError("ov not found"))
    def test_graceful_degradation_cli_not_found(self, mock_run):
        """Test graceful degradation when ov CLI is not found."""
        client = OpenVikingClient()

        # Should not crash, return None or empty result
        resource_id = client.add_resource(name="test", resource_type="service")
        assert resource_id is None

        results = client.find_resources(query="test")
        assert results == []

    @patch('subprocess.run')
    def test_error_handling_subprocess_failure(self, mock_run):
        """Test that subprocess failures are caught and ahandled gracefully."""
        # Mock subprocess failure by raising CalledProcessError
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=["ov", "add", "test", "--type", "invalid"],
            stderr="Error: Invalid arguments\n"
        )

        client = OpenVikingClient()

        # Should not crash, return None
        resource_id = client.add_resource(name="test", resource_type="invalid")
        assert resource_id is None

    @patch('subprocess.run')
    def test_error_handling_malformed_json_response(self, mock_run):
        """Test handling of malformed JSON in find_resources response."""
        # Mock subprocess returning invalid JSON
        mock_result = MagicMock()
        mock_result.stdout = "not valid json\n"
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        client = OpenVikingClient()
        results = client.find_resources(query="test")

        # Should return empty list on parse error
        assert results == []
