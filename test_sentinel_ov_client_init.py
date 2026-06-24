import pytest
from sentinel import QdrantSentinel


def test_ov_client_init():
    """Test that QdrantSentinel initializes OpenVikingClient instance."""
    sentinel = QdrantSentinel(watch_paths=[])
    
    # Assert OpenVikingClient instance exists
    assert sentinel.ov_client is not None
    
    # Assert required methods exist
    assert hasattr(sentinel.ov_client, 'add_resource')
    assert callable(sentinel.ov_client.add_resource)
    
    assert hasattr(sentinel.ov_client, 'find_resources')
    assert callable(sentinel.ov_client.find_resources)
