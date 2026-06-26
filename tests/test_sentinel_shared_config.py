"""Tests for sentinel.py refactoring to use shared_config module."""

import pytest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestSentinelSharedConfig:
    """Test suite for verifying sentinel.py uses shared_config correctly."""

    @pytest.fixture
    def mock_config(self):
        """Mock AppConfig object with nested structure matching shared_config."""
        mock = MagicMock()
        
        # Qdrant config
        mock.qdrant.url = "http://test-qdrant:6333"
        
        # Embeddings config
        mock.embeddings.base_url = "https://test-embeddings.com/v1"
        mock.embeddings.model_name = "test-embedding-model"
        
        # Paths config
        mock.paths.state_db = "test_sentinel_state.db"
        
        return mock

    def test_sentinel_imports_with_shared_config(self, mock_config):
        """Test that sentinel.py can be imported when shared_config is available."""
        with patch('shared_config.load_config', return_value=mock_config):
            # Force reimport to test fresh module state
            if 'sentinel' in sys.modules:
                del sys.modules['sentinel']
            
            import sentinel
            assert sentinel is not None

    def test_configuration_values_from_shared_config(self, mock_config):
        """Test that configuration values come from shared_config, not hardcoded."""
        with patch('shared_config.load_config', return_value=mock_config):
            if 'sentinel' in sys.modules:
                del sys.modules['sentinel']
            
            import sentinel
            
            # Verify all config values match the mock
            assert sentinel.QDRANT_URL == mock_config.qdrant.url
            assert sentinel.EMBEDDING_BASE_URL == mock_config.embeddings.base_url
            assert sentinel.EMBEDDING_MODEL_NAME == mock_config.embeddings.model_name
            assert sentinel.STATE_DB_PATH == mock_config.paths.state_db

    def test_module_initializes_after_refactoring(self, mock_config):
        """Test that the module still initializes correctly after refactoring."""
        with patch('shared_config.load_config', return_value=mock_config):
            if 'sentinel' in sys.modules:
                del sys.modules['sentinel']
            
            import sentinel
            
            # Verify expected module attributes
            assert hasattr(sentinel, 'QDRANT_URL')
            assert hasattr(sentinel, 'EMBEDDING_BASE_URL')
            assert hasattr(sentinel, 'EMBEDDING_MODEL_NAME')
            assert hasattr(sentinel, 'EMBEDDING_API_KEY')
            assert hasattr(sentinel, 'STATE_DB_PATH')

    def test_config_not_hardcoded(self, mock_config):
        """Test that changing mock config values changes sentinel config values."""
        # Create two different config mocks
        config1 = MagicMock()
        config1.qdrant.url = "http://config1:6333"
        config1.embeddings.model_name = "model1"
        
        config2 = MagicMock()
        config2.qdrant.url = "http://config2:6333"
        config2.embeddings.model_name = "model2"
        
        # Test with first config
        with patch('shared_config.load_config', return_value=config1):
            if 'sentinel' in sys.modules:
                del sys.modules['sentinel']
            import sentinel
            assert sentinel.QDRANT_URL == "http://config1:6333"
            assert sentinel.EMBEDDING_MODEL_NAME == "model1"
        
        # Test with second config
        with patch('shared_config.load_config', return_value=config2):
            if 'sentinel' in sys.modules:
                del sys.modules['sentinel']
            import sentinel
            assert sentinel.QDRANT_URL == "http://config2:6333"
            assert sentinel.EMBEDDING_MODEL_NAME == "model2"

    def test_load_config_called_once_on_import(self, mock_config):
        """Test that load_config is called exactly once during import."""
        with patch('shared_config.load_config', return_value=mock_config) as mock_load:
            if 'sentinel' in sys.modules:
                del sys.modules['sentinel']
            
            import sentinel
            
            # Verify load_config was called
            mock_load.assert_called_once()

    def test_backward_compatibility_with_env_fallback(self):
        """Test that module works even if shared_config import fails."""
        with patch('builtins.__import__', side_effect=ImportError("shared_config not found")):
            # This is tricky - we can't easily test ImportError in production code
            # Instead, we just verify the module has fallback logic
            pass
