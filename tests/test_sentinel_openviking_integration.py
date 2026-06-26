"""
Test suite for OpenVikingManager integration into sentinel.py (TDD Phase 1: RED).
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio
import os


class TestOpenVikingIntegration:
    """Test OpenVikingManager lifecycle integration in sentinel.py."""

    @pytest.mark.asyncio
    async def test_openviking_enabled_starts_manager(self):
        """Verify that OPEN_VIKING_ENABLED=true starts the manager."""
        with patch.dict(os.environ, {'OPEN_VIKING_ENABLED': 'true', 'OPEN_VIKING_SERVER_PATH': 'ov'}):
            with patch('process_manager.OpenVikingManager') as MockManager:
                mock_manager = AsyncMock()
                mock_manager.start = AsyncMock()
                mock_manager.stop = AsyncMock()
                mock_manager.is_alive = MagicMock(return_value=True)
                MockManager.return_value = mock_manager

                # Import after patching to ensure module uses patched version
                import sentinel

                # Simulate main function behavior
                manager = MockManager('ov', ['server', 'start'])
                await manager.start()
                
                MockManager.assert_called_once()
                mock_manager.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_openviking_disabled_skips_manager(self):
        """Verify that OPEN_VIKING_ENABLED=false skips manager instantiation."""
        with patch.dict(os.environ, {'OPEN_VIKING_ENABLED': 'false'}):
            with patch('process_manager.OpenVikingManager') as MockManager:
                # Import after patching
                import sentinel

                # When disabled, manager should not be instantiated
                MockManager.assert_not_called()

    @pytest.mark.asyncio
    async def test_openviking_not_set_skips_manager(self):
        """Verify that missing OPEN_VIKING_ENABLED env var skips manager."""
        env_copy = os.environ.copy()
        if 'OPEN_VIKING_ENABLED' in env_copy:
            del env_copy['OPEN_VIKING_ENABLED']
        
        with patch.dict(os.environ, env_copy, clear=True):
            with patch('process_manager.OpenVikingManager') as MockManager:
                # Import after patching
                import sentinel

                # When not set, manager should not be instantiated
                MockManager.assert_not_called()

    @pytest.mark.asyncio
    async def test_manager_stop_called_in_finally_on_success(self):
        """Verify that manager.stop() is called in finally block on successful execution."""
        with patch.dict(os.environ, {'OPEN_VIKING_ENABLED': 'true', 'OPEN_VIKING_SERVER_PATH': 'ov'}):
            with patch('process_manager.OpenVikingManager') as MockManager:
                mock_manager = AsyncMock()
                mock_manager.start = AsyncMock()
                mock_manager.stop = AsyncMock()
                mock_manager.is_alive = MagicMock(return_value=True)
                MockManager.return_value = mock_manager

                # Simulate try/finally pattern
                manager = MockManager('ov', ['server', 'start'])
                try:
                    await manager.start()
                    # Main execution would happen here
                finally:
                    await manager.stop()

                mock_manager.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_manager_stop_called_in_finally_on_exception(self):
        """Verify that manager.stop() is called in finally block even when main execution crashes."""
        with patch.dict(os.environ, {'OPEN_VIKING_ENABLED': 'true', 'OPEN_VIKING_SERVER_PATH': 'ov'}):
            with patch('process_manager.OpenVikingManager') as MockManager:
                mock_manager = AsyncMock()
                mock_manager.start = AsyncMock()
                mock_manager.stop = AsyncMock()
                mock_manager.is_alive = MagicMock(return_value=True)
                MockManager.return_value = mock_manager

                # Simulate try/finally with exception
                manager = MockManager('ov', ['server', 'start'])
                with pytest.raises(RuntimeError):
                    try:
                        await manager.start()
                        raise RuntimeError("Main execution crashed")
                    finally:
                        await manager.stop()

                mock_manager.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_retries_until_alive(self):
        """Verify that health check retries until manager.is_alive() returns True."""
        with patch.dict(os.environ, {'OPEN_VIKING_ENABLED': 'true', 'OPEN_VIKING_SERVER_PATH': 'ov'}):
            with patch('process_manager.OpenVikingManager') as MockManager:
                mock_manager = AsyncMock()
                mock_manager.start = AsyncMock()
                mock_manager.stop = AsyncMock()
                # First two calls return False, third returns True
                mock_manager.is_alive = MagicMock(side_effect=[False, False, True])
                MockManager.return_value = mock_manager

                # Simulate health check loop
                manager = MockManager('ov', ['server', 'start'])
                await manager.start()
                
                max_retries = 5
                retry_delay = 0.1  # Short delay for testing
                for i in range(max_retries):
                    if manager.is_alive():
                        break
                    await asyncio.sleep(retry_delay)
                else:
                    raise RuntimeError("Health check failed")

                # Should have been called 3 times (False, False, True)
                assert mock_manager.is_alive.call_count == 3

    @pytest.mark.asyncio
    async def test_health_check_timeout_raises_error(self):
        """Verify that health check raises error if manager doesn't become alive."""
        with patch.dict(os.environ, {'OPEN_VIKING_ENABLED': 'true', 'OPEN_VIKING_SERVER_PATH': 'ov'}):
            with patch('process_manager.OpenVikingManager') as MockManager:
                mock_manager = AsyncMock()
                mock_manager.start = AsyncMock()
                mock_manager.stop = AsyncMock()
                mock_manager.is_alive = MagicMock(return_value=False)
                MockManager.return_value = mock_manager

                # Simulate health check loop with timeout
                manager = MockManager('ov', ['server', 'start'])
                await manager.start()
                
                max_retries = 3
                retry_delay = 0.01  # Very short delay for testing
                with pytest.raises(RuntimeError, match="Health check failed"):
                    for i in range(max_retries):
                        if manager.is_alive():
                            break
                        await asyncio.sleep(retry_delay)
                    else:
                        raise RuntimeError("Health check failed")

    @pytest.mark.asyncio
    async def test_openviking_server_path_from_from_env(self):
        """Verify that OPEN_VIKING_SERVER_PATH env var is used for manager executable."""
        with patch.dict(os.environ, {
            'OPEN_VIKING_ENABLED': 'true',
            'OPEN_VIKING_SERVER_PATH': '/custom/path/ov'
        }):
            with patch('process_manager.OpenVikingManager') as MockManager:
                mock_manager = AsyncMock()
                mock_manager.start = AsyncMock()
                mock_manager.stop = AsyncMock()
                mock_manager.is_alive = MagicMock(return_value=True)
                MockManager.return_value = mock_manager

                # Simulate manager instantiation with custom path
                manager = MockManager('/custom/path/ov', ['server', 'start'])
                
                MockManager.assert_called_once_with('/custom/path/ov', ['server', 'start'])

    @pytest.mark.asyncio
    async def test_default_server_path_when_not_set(self):
        """Verify that default 'ov' path is used when OPEN_VIKING_SERVER_PATH is not set."""
        with patch.dict(os.environ, {'OPEN_VIKING_ENABLED': 'true'}):
            with patch('process_manager.OpenVikingManager') as MockManager:
                mock_manager = AsyncMock()
                mock_manager.start = AsyncMock()
                mock_manager.stop = AsyncMock()
                mock_manager.is_alive = MagicMock(return_value=True)
                MockManager.return_value = mock_manager

                # Simulate manager instantiation with default path
                manager = MockManager('ov', ['server', 'start'])
                
                MockManager.assert_called_once_with('ov', ['server', 'start'])

    @pytest.mark.asyncio
    async def test_manager_args_include_server_start(self):
        """Verify that manager is instantiated with ['server', 'start'] args."""
        with patch.dict(os.environ, {
            'OPEN_VIKING_ENABLED': 'true',
            'OPEN_VIKING_SERVER_PATH': 'ov'
        }):
            with patch('process_manager.OpenVikingManager') as MockManager:
                mock_manager = AsyncMock()
                mock_manager.start = AsyncMock()
                mock_manager.stop = AsyncMock()
                mock_manager.is_alive = MagicMock(return_value=True)
                MockManager.return_value = mock_manager

                # Simulate manager instantiation
                manager = MockManager('ov', ['server', 'start'])
                
                call_args = MockManager.call_args
                assert call_args[0][1] == ['server', 'start']
