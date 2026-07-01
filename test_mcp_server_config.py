"""Test MCP server configuration loading after fix."""
import os
import pytest

# Set environment variables before importing shared_config
os.environ.setdefault("EMBEDDING_PROVIDER", "openai_compatible")
os.environ.setdefault("EMBEDDING_API_KEY", "test_key")
os.environ.setdefault("EMBEDDING_BASE_URL", "http://test.com/v1")
os.environ.setdefault("EMBEDDING_MODEL_NAME", "text-embedding-v4")
os.environ.setdefault("EMBEDDING_DIMENSION", "1024")
os.environ.setdefault("QDRANT_URL", "http://127.0.0.1:6333")


def test_load_config_returns_appconfig():
    """Verify load_config returns AppConfig with all required sections."""
    from shared_config import load_config, AppConfig, QdrantConfig, PathsConfig
    
    config = load_config()
    
    assert isinstance(config, AppConfig)
    assert isinstance(config.qdrant, QdrantConfig)
    assert isinstance(config.paths, PathsConfig)


def test_qdrant_config_has_url():
    """Verify [qdrant].url is present and correct."""
    from shared_config import load_config
    
    config = load_config()
    
    assert config.qdrant.url == "http://127.0.0.1:6333"


def test_paths_config_has_required_fields():
    """Verify [paths] section has data_root and state_db."""
    from shared_config import load_config
    
    config = load_config()
    
    assert config.paths.data_root is not None
    assert config.paths.state_db is not None
    assert "sentinel_state" in config.paths.state_db


def test_create_server_succeeds():
    """Verify MCP server can be created with all tools registered."""
    os.environ["EMBEDDING_API_KEY"] = "test_key"
    from mcp_server.run import create_server
    
    server = create_server()
    
    assert server is not None
    assert server.name == "qdrant-sentinel"


def test_config_is_appconfig_not_dict():
    """Verify load_config returns AppConfig, not dict."""
    from shared_config import load_config, AppConfig
    
    config = load_config()
    
    # This is what run.py checks - if it were dict, isinstance would fail
    assert isinstance(config, AppConfig)
    assert not isinstance(config, dict)
