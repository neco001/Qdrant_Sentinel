import tempfile
import os
import pytest
from pathlib import Path
from shared_config import load_config

def test_qdrant_config_with_collections():
    """Test that QdrantConfig correctly parses collections list from TOML."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create test TOML file - must be named qdrant_index.toml
        toml_content = """
[qdrant]
url = "http://localhost:6333"
collections = ["my-collection"]

[embeddings]
provider = "openai_compatible"

[openviking]
cli_path = "ov"
enabled = true

[paths]
data_root = "."
state_db = "sentinel_state.db"
        """.strip()
        
        config_path = os.path.join(temp_dir, "qdrant_index.toml")
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(toml_content)
        
        # Load config from temporary directory (load_config takes project_root, not file path)
        config = load_config(temp_dir)
        
        # Verify collections field exists and has correct value
        assert hasattr(config.qdrant, "collections"), "QdrantConfig must have 'collections' field"
        assert isinstance(config.qdrant.collections, list), "QdrantConfig.collections must be a list"
        assert all(isinstance(item, str) for item in config.qdrant.collections), "QdrantConfig.collections must contain only strings"
        assert config.qdrant.collections == ["my-collection"], "QdrantConfig.collections must match the configured value"

def test_qdrant_config_without_collections():
    """Test that QdrantConfig defaults to empty list when collections not specified (backward compatibility)."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create test TOML file without collections field
        toml_content = """
[qdrant]
url = "http://localhost:6333"

[embeddings]
provider = "openai_compatible"

[openviking]
cli_path = "ov"
enabled = true

[paths]
data_root = "."
state_db = "sentinel_state.db"
        """.strip()
        
        config_path = os.path.join(temp_dir, "qdrant_index.toml")
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(toml_content)
        
        # Load config from temporary directory
        config = load_config(temp_dir)
        
        # Verify collections field exists and defaults to empty list
        assert hasattr(config.qdrant, "collections"), "QdrantConfig must have 'collections' field"
        assert isinstance(config.qdrant.collections, list), "QdrantConfig.collections must be a list"
        assert config.qdrant.collections == [], "QdrantConfig.collections must default to empty list if not specified"
