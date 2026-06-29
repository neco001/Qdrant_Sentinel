# test_task_build_index_param.py

import pytest
from unittest.mock import patch, MagicMock
from openviking_client import OpenVikingClient

def test_add_resource_passes_build_index_false():
    """
    Test that OpenVikingClient.add_resource() passes build_index=False to SyncOpenViking.add_resource()
    """
    # Create a mock SyncOpenViking instance
    mock_sync_openviking = MagicMock()
    mock_sync_openviking.add_resource.return_value = {"id": "test-resource-id"}
    
    # Patch SyncOpenViking to return our mock
    with patch('openviking_client.SyncOpenViking', return_value=mock_sync_openviking):
        # Initialize OpenVikingClient
        client = OpenVikingClient()
        
        # Call add_resource
        test_path = '/test/path'
        result = client.add_resource(test_path)
        
        # Verify method was called with build_index=False
        mock_sync_openviking.add_resource.assert_called_once_with(
            test_path,
            build_index=False
        )
        assert result == "test-resource-id"
