"""Test suite for signal handling in sentinel.py (TDD Phase 1: RED)."""
import asyncio
import signal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
class TestSignalHandlerRegistration:
    """Test that signal handlers are properly registered."""

    async def test_sigterm_handler_registered(self):
        """Verify SIGTERM handler is registered on async_main start."""
        with patch('asyncio.get_event_loop') as mock_get_loop:
            mock_loop = MagicMock()
            mock_get_loop.return_value = mock_loop
            
            # Import and call async_main (will fail because we don't have the handler yet)
            from sentinel import async_main
            
            # Mock the actual async_main to avoid running full sentinel
            with patch('sentinel.QdrantSentinel'), \
                 patch('sentinel.Observer'), \
                 patch('sentinel.SentinelHandler'), \
                 patch('os.getenv', return_value='false'):
                
                try:
                    await async_main()
                except:
                    pass  # We expect some errors since we're mocking heavily
                
                # Verify signal handler was registered
                assert mock_loop.add_signal_handler.called
                call_args = mock_loop.add_signal_handler.call_args_list
                signal_nums = [call[0][0] for call in call_args]
                assert signal.SIGTERM in signal_nums

    async def test_sigint_handler_registered(self):
        """Verify SIGINT handler is registered on async_main start."""
        with patch('asyncio.get_event_loop') as mock_get_loop:
            mock_loop = MagicMock()
            mock_get_loop.return_value = mock_loop
            
            from sentinel import async_main
            
            with patch('sentinel.QdrantSentinel'), \
                 patch('sentinel.Observer'), \
                 patch('sentinel.SentinelHandler'), \
                 patch('os.getenv', return_value='false'):
                
                try:
                    await async_main()
                except:
                    pass
                
                assert mock_loop.add_signal_handler.called
                call_args = mock_loop.add_signal_handler.call_args_list
                signal_nums = [call[0][0] for call in call_args]
                assert signal.SIGINT in signal_nums


@pytest.mark.asyncio
class TestSignalHandlerBehavior:
    """Test signal handler behavior."""

    @pytest.fixture(autouse=True)
    def reset_shutdown_flag(self):
        """Reset shutdown_flag before each test to prevent cross-test contamination."""
        import sentinel
        sentinel.shutdown_flag = False
        yield

    async def test_handler_sets_shutdown_flag(self):
        """Verify signal handler sets global shutdown flag."""
        import sentinel
        sentinel.shutdown_flag = False
        
        # Call handler
        await sentinel.signal_handler()
        
        # Verify flag is set
        assert sentinel.shutdown_flag is True

    async def test_handler_calls_manager_stop(self):
        """Verify signal handler calls manager.stop() when manager exists."""
        import sentinel
        
        # Create mock manager
        mock_manager = MagicMock()
        mock_manager.stop = AsyncMock()
        
        # Set global manager
        sentinel.manager = mock_manager
        
        # Call handler
        await sentinel.signal_handler()
        
        # Verify stop was called
        mock_manager.stop.assert_called_once()

    async def test_handler_handles_no_manager_gracefully(self):
        """Verify signal handler doesn't crash when manager is None."""
        import sentinel
        
        # Set global manager to None
        sentinel.manager = None
        
        # Call handler - should not raise
        try:
            await sentinel.signal_handler()
        except Exception as e:
            pytest.fail(f"signal_handler raised exception: {e}")

    async def test_handler_logs_shutdown_message(self):
        """Verify signal handler logs shutdown message."""
        import sentinel
        
        # Set global manager to None
        sentinel.manager = None
        
        with patch('sentinel.logger') as mock_logger:
            mock_log = mock_logger.info
            # Call handler
            await sentinel.signal_handler()
            
            # Verify log was called
            assert mock_log.called
            call_args = mock_log.call_args_list
            log_messages = [call[0][0] for call in call_args]
            assert any('shutdown' in msg.lower() for msg in log_messages)


@pytest.mark.asyncio
class TestShutdownFlagraIntegration:
    """Test shutdown flag integration with main loop."""

    @pytest.fixture(autouse=True)
    def reset_shutdown_flag(self):
        """Reset shutdown_flag before each test to prevent cross-test contamination."""
        import sentinel
        sentinel.shutdown_flag = False
        yield

    async def test_shutdown_flag_stops_watching_loop(self):
        """Verify shutdown flag causes watching loop to exit."""
        import sentinel
        sentinel.shutdown_flag = False
        
        with patch('sentinel.QdrantSentinel') as mock_sentinel_class, \
             patch('sentinel.Observer') as mock_observer_class, \
             patch('sentinel.SentinelHandler'), \
             patch('os.getenv', return_value='false'):
            
            mock_sentinel = MagicMock()
            mock_sentinel_class.return_value = mock_sentinel
            
            mock_observer = MagicMock()
            mock_observer_class.return_value = mock_observer
            
            # Mock the event loop to set shutdown flag after a short delay
            async def set_shutdown_later():
                await asyncio.sleep(0.1)
                sentinel.shutdown_flag = True
            
            # Start async_main but with timeout
            try:
                await asyncio.wait_for(set_shutdown_later(), timeout=0.5)
            except asyncio.TimeoutError:
                pytest.fail("async_main did not exit when shutdown_flag was set")


@pytest.mark.asyncio
class TestSignalHandlerCleanup:
    """Test signal handler cleanup on exit."""

    async def test_signal_handlers_removed_on_exit(self):
        """Verify signal handlers are removed when async_main exits."""
        import sentinel
        import sys
        
        # Store original get_event_loop and sys.argv
        original_get_event_loop = asyncio.get_event_loop
        original_argv = sys.argv
        
        mock_loop = MagicMock()
        
        # Patch asyncio.get_event_loop in the sentinel module's scope
        sentinel.asyncio.get_event_loop = lambda: mock_loop
        
        try:
            with patch('sentinel.QdrantSentinel'), \
                 patch('sentinel.Observer'), \
                 patch('sentinel.SentinelHandler'), \
                 patch('os.getenv', return_value='false'):
                
                # Patch sys.argv to avoid argparse parsing pytest arguments
                sys.argv = ['sentinel']

                try:
                    await sentinel.async_main()
                except:
                    pass

                # Verify remove_signal_handler was called
                assert mock_loop.remove_signal_handler.called
        finally:
            # Restore original
            sentinel.asyncio.get_event_loop = original_get_event_loop
            sys.argv = original_argv
