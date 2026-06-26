import pytest
import os
import tempfile
from pathlib import Path
from shared_config import load_config, ConfigurationError

class TestSharedConfig:
    """Test suite for shared_config module."""

    def test_load_config_success(self):
        """Verify successful config loading with valid TOML."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create valid config file
            config_path = Path(tmpdir) / "qdrant_index.toml"
            config_path.write_text("""
[qdrant]
url = "http://localhost:6333"

[embeddings]
base_url = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
model_name = "text-embedding-v4"
dimension = 1024

[openviking]
cli_path = "ov"
enabled = true

[paths]
data_root = "."
state_db = "sentinel_state.db"
""")
            
            config = load_config(tmpdir)
            
            # Verify Qdrant config
            assert config.qdrant.url == "http://localhost:6333"
            
            # Verify Embeddings config (CRITICAL for vector compatibility)
            assert config.embeddings.base_url == "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
            assert config.embeddings.model_name == "text-embedding-v4"
            assert config.embeddings.dimension == 1024
            
            # Verify OpenViking config
            assert config.openviking.cli_path == "ov"
            assert config.openviking.enabled is True
            
            # Verify Paths config
            assert config.paths.data_root == "."
            assert config.paths.state_db == "sentinel_state.db"

    def test_load_config_missing_file(self):
        """Verify ConfigurationError raised when config file missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Don't create config file
            with pytest.raises(ConfigurationError) as exc_info:
                load_config(tmpdir)
            
            assert "Configuration file not found" in str(exc_info.value)

    def test_load_config_missing_qdrant_section(self):
        """Verify ConfigurationError raised when [qdrant] section missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "qdrant_index.toml"
            config_path.write_text("""
[embeddings]
base_url = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
model_name = "text-embedding-v4"
dimension = 1024

[paths]
data_root = "."
state_db = "sentinel_state.db"
""")
            
            with pytest.raises(ConfigurationError) as exc_info:
                load_config(tmpdir)
            
            assert "Missing required key in [qdrant] section" in str(exc_info.value)

    def test_load_config_missing_embeddings_section(self):
        """Verify ConfigurationError raised when [embeddings] section missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "qdrant_index.toml"
            config_path.write_text("""
[qdrant]
url = "http://localhost:6333"

[paths]
data_root = "."
state_db = "sentinel_state.db"
""")
            
            with pytest.raises(ConfigurationError) as exc_info:
                load_config(tmpdir)
            
            assert "Missing required key in [embeddings] section" in str(exc_info.value)

    def test_load_config_openviking_defaults(self):
        """Verify OpenViking config uses defaults when section missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "qdrant_index.toml"
            config_path.write_text("""
[qdrant]
url = "http://localhost:6333"

[embeddings]
base_url = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
model_name = "text-embedding-v4"
dimension = 1024

[paths]
data_root = "."
state_db = "sentinel_state.db"
""")
            
            config = load_config(tmpdir)
            
            # Verify defaults
            assert config.openviking.cli_path == "ov"
            assert config.openviking.enabled is True

    def test_load_config_paths_defaults(self):
        """Verify Paths config uses defaults when values missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "qdrant_index.toml"
            config_path.write_text("""
[qdrant]
url = "http://localhost:6333"

[embeddings]
base_url = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
model_name = "text-embedding-v4"
dimension = 1024

[paths]
data_root = "."
""")
            
            config = load_config(tmpdir)
            
            # Verify default for state_db
            assert config.paths.state_db == "sentinel_state.db"

    def test_load_config_invalid_toml(self):
        """Verify ConfigurationError raised for invalid TOML syntax."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "qdrant_index.toml"
            config_path.write_text("""
[qdrant
url = "http://localhost:6333"
""")
            
            with pytest.raises(ConfigurationError) as exc_info:
                load_config(tmpdir)
            
            assert "Failed to parse" in str(exc_info.value)
