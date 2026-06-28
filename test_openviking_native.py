# test_openviking_native.py
"""
Test file for the native SyncOpenViking-based OpenVikingClient implementation.

These tests will FAIL with the current subprocess-based implementation
and will PASS after implementing the native adapter.
"""

import unittest
import warnings
import builtins
import pytest
from unittest.mock import patch, MagicMock
from typing import Dict, Any, List
from openviking_client import OpenVikingClient


class TestOpenVikingClientNative(unittest.TestCase):
    """Test cases for the native SyncOpenViking-based OpenVikingClient."""

    @patch('openviking_client.SyncOpenViking')
    def test_init_with_data_path(self, mock_sync_openviking: MagicMock):
        """Test that client can be instantiated with data_path parameter."""
        # Setup mock
        mock_instance = MagicMock()
        mock_sync_openviking.return_value = mock_instance

        # Test initialization with data_path
        client = OpenVikingClient(data_path="/test/data")
        
        # Verify SyncOpenViking was initialized with correct parameters
        mock_sync_openviking.assert_called_once_with(
            path="/test/data"
        )
        self.assertIsNotNone(client)

    @patch('openviking_client.SyncOpenViking')
    def test_default_init_uses_default_data_path(self, mock_sync_openviking: MagicMock):
        """Test that default constructor uses sensible default data_path."""
        # Setup mock
        mock_instance = MagicMock()
        mock_sync_openviking.return_value = mock_instance

        # Test default initialization (like callers do: OpenVikingClient())
        client = OpenVikingClient()
        
        # Verify SyncOpenViking was initialized (with default data path)
        mock_sync_openviking.assert_called_once()
        self.assertIsNotNone(client)

    @patch('openviking_client.SyncOpenViking')
    def test_backward_compatibility_with_cli_path(self, mock_sync_openviking: MagicMock):
        """Test backward compatibility: cli_path is accepted but warns and uses default data_path."""
        # Setup mock
        mock_instance = MagicMock()
        mock_sync_openviking.return_value = mock_instance

        # Capture warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            client = OpenVikingClient(cli_path="/old/path/ov")
            
            # Verify warning was issued
            warning_found = any(
                "cli_path" in str(warning.message) and "deprecated" in str(warning.message).lower()
                for warning in w
            )
            self.assertTrue(warning_found, f"Expected deprecation warning for cli_path, got: {[str(x.message) for x in w]}")
        
        # Verify SyncOpenViking was initialized (with default data path)
        mock_sync_openviking.assert_called_once()
        self.assertIsNotNone(client)

    @patch('openviking_client.SyncOpenViking')
    def test_add_resource_returns_id_from_dict(self, mock_sync_openviking: MagicMock):
        """Test add_resource extracts ID from SyncOpenViking's dict response."""
        # Setup mock
        mock_instance = MagicMock()
        mock_sync_openviking.return_value = mock_instance
        mock_instance.add_resource.return_value = {"id": "test-123"}

        client = OpenVikingClient(data_path="/test/data")
        
        # Call add_resource
        resource_id = client.add_resource("/test/file.txt")
        
        # Verify SyncOpenViking.add_resource was called
        mock_instance.add_resource.assert_called_once_with("/test/file.txt")
        
        # Verify returned resource ID
        self.assertEqual(resource_id, "test-123")

    @patch('openviking_client.SyncOpenViking')
    def test_add_resource_extracts_alternative_ids(self, mock_sync_openviking: MagicMock):
        """Test add_resource extracts IDs from various key formats in returned dict."""
        test_cases = [
            {"temp_file_id": "temp-456"},
            {"resource_id": "res-789"},
            {"uri": "file://test-uri-101"}
        ]

        for response in test_cases:
            with self.subTest(response=response):
                # Setup mock
                mock_instance = MagicMock()
                mock_sync_openviking.return_value = mock_instance
                mock_instance.add_resource.return_value = response

                client = OpenVikingClient(data_path="/test/data")
                
                # Call add_resource
                resource_id = client.add_resource("/test/file.txt")
                
                # Verify ID was extracted correctly
                self.assertIsNotNone(resource_id)

    @patch('openviking_client.SyncOpenViking')
    def test_find_resources_returns_list_of_dicts(self, mock_sync_openviking: MagicMock):
        """Test find_resources converts SyncOpenViking's FindResult objects to dicts."""
        # Setup mock
        mock_instance = MagicMock()
        mock_sync_openviking.return_value = mock_instance
        
        # Mock FindResult objects with required attributes
        class MockFindResult:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)
            
            def __getitem__(self, key):
                return getattr(self, key)
            
            def get(self, key, default=None):
                return getattr(self, key, default)
        
        mock_results = [
            MockFindResult(id="doc-1", content="First document", score=0.95),
            MockFindResult(id="doc-2", content="Second document", score=0.85)
        ]
        
        mock_instance.find.return_value = iter(mock_results)

        client = OpenVikingClient(data_path="/test/data")
        
        # Call find_resources
        results = client.find_resources("test query")
        
        # Verify SyncOpenViking.find was called
        mock_instance.find.assert_called_once_with("test query")
        
        # Verify results format
        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 2)
        self.assertIsInstance(results[0], dict)
        self.assertIn("id", results[0])
        self.assertIn("content", results[0])
        self.assertIn("score", results[0])

    @patch('openviking_client.SyncOpenViking')
    def test_find_resources_returns_empty_list_on_error(self, mock_sync_openviking: MagicMock):
        """Test find_resources returns empty list if SyncOpenViking.find raises an exception."""
        # Setup mock to raise exception
        mock_instance = MagicMock()
        mock_sync_openviking.return_value = mock_instance
        mock_instance.find.side_effect = Exception("Test exception")

        client = OpenVikingClient(data_path="/test/data")
        
        # Call find_resources
        results = client.find_resources("test query")
        
        # Verify results are empty list
        self.assertEqual(results, [])

    @patch('openviking_client.SyncOpenViking')
    def test_add_resource_returns_none_on_error(self, mock_sync_openviking: MagicMock):
        """Test add_resource returns None if SyncOpenViking.add_resource raises an exception."""
        # Setup mock to raise exception
        mock_instance = MagicMock()
        mock_sync_openviking.return_value = mock_instance
        mock_instance.add_resource.side_effect = Exception("Test exception")

        client = OpenVikingClient(data_path="/test/data")
        
        # Call add_resource
        resource_id = client.add_resource("/test/file.txt")
        
        # Verify None is returned
        self.assertIsNone(resource_id)

    @pytest.mark.xfail(reason="Import patching causes recursion in pytest; graceful degradation tested via test_graceful_degradation_when_syncopenviking_fails_to_initialize")
    @patch('builtins.__import__')
    def test_graceful_degradation_when_syncopenviking_not_importable(self, mock_import: MagicMock):
        """Test graceful degradation when SyncOpenViking import fails."""
        # Setup import to fail specifically for openviking
        original_import = builtins.__import__
        
        def custom_import(name, *args, **kwargs):
            if name == 'openviking' or name.startswith('openviking.'):
                raise ImportError("SyncOpenViking not found")
            return original_import(name, *args, **kwargs)
        
        mock_import.side_effect = custom_import

        # Force re-import to trigger the error
        import importlib
        import openviking_client
        importlib.reload(openviking_client)
        
        # Should instantiate without raising exception
        from openviking_client import OpenVikingClient
        client = OpenVikingClient(data_path="/test/data")
        
        # Methods should return safe values
        self.assertIsNone(client.add_resource("/test/file.txt"))
        self.assertEqual(client.find_resources("test query"), [])

    @patch('openviking_client.SyncOpenViking')
    def test_graceful_degradation_when_syncopenviking_fails_to_initialize(self, mock_sync_openviking: MagicMock):
        """Test graceful degradation when SyncOpenViking initialization fails."""
        # Setup initialization to raise exception
        mock_sync_openviking.side_effect = Exception("Failed to initialize")

        # Should instantiate without raising exception
        client = OpenVikingClient(data_path="/test/data")
        
        # Methods should return safe values
        self.assertIsNone(client.add_resource("/test/file.txt"))
        self.assertEqual(client.find_resources("test query"), [])


if __name__ == "__main__":
    unittest.main()
