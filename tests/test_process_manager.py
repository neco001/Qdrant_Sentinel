import asyncio
import os
import signal
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

# TDD Phase 1: Tests for OpenVikingManager
# These tests expect the class to be created in process_manager.py

@pytest.mark.asyncio
class TestOpenVikingManagerInit:
    """Test initialization of OpenVikingManager."""
    
    async def test_init_with_path_and_args(self):
        """Test that initialization stores executable path and arguments."""
        from process_manager import OpenVikingManager
        
        executable = "/path/to/openviking-server"
        args = ["--port", "8080", "--verbose"]
        
        manager = OpenVikingManager(executable, args)
        
        assert manager.executable == executable
        assert manager.args == args
        assert manager.process is None

@pytest.mark.asyncio
class TestOpenVikingManagerStart:
    """Test process spawning and startup."""
    
    async def test_start_spawns_process(self):
        """Test that start() creates an asyncio subprocess."""
        from process_manager import OpenVikingManager
        
        manager = OpenVikingManager("openviking-server", ["--port", "8080"])
        
        mock_process = AsyncMock()
        mock_process.returncode = None
        mock_process.stdout = MagicMock()
        mock_process_manager = MagicMock()
        mock_process.pid = 12345
        
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process) as mock_subprocess:
            with patch("asyncio.create_task"):
                await manager.start()
                
                # Verify the subprocess was called with correct arguments
                call_args = mock_subprocess.call_args
                assert call_args[0] == ("openviking-server", "--port", "8080")
                assert call_args[1]['stdout'] == asyncio.subprocess.PIPE
                assert call_args[1]['stderr'] == asyncio.subprocess.PIPE
                assert 'env' in call_args[1]  # Environment augmentation for Windows
                assert manager.process == mock_process

    async def test_start_file_not_found_error(self):
        """Test that FileNotFoundError is raised if executable is not found."""
        from process_manager import OpenVikingManager
        
        manager = OpenVikingManager("nonexistent-binary", [])
        
        error = FileNotFoundError(2, "No such file or directory", "nonexistent-binary")
        
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, side_effect=error):
            with pytest.raises(FileNotFoundError):
                await manager.start()

    async def test_start_captures_logs_non_blocking(self):
        """Test that stdout/stderr are piped and log reading tasks are spawned."""
        from process_manager import OpenVikingManager
        
        manager = OpenVikingManager("openviking-server", [])
        
        mock_process = AsyncMock()
        mock_process.returncode = None
        mock_process.stdout = MagicMock()
        mock_process.stderr = MagicMock()
        
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process):
            with patch("asyncio.create_task") as mock_create_task:
                await manager.start()
                
                # Should create tasks for reading stdout and stderr
                assert mock_create_task.call_count == 2

@pytest.mark.asyncio
class TestOpenVikingManagerIsAlive:
    """Test process status checking."""
    
    async def test_is_alive_true_when_running(self):
        """Test is_alive returns True when process returncode is None."""
        from process_manager import OpenVikingManager
        
        manager = OpenVikingManager("openviking-server", [])
        
        mock_process = AsyncMock()
        mock_process.returncode = None
        manager.process = mock_process
        
        assert manager.is_alive() is True

    async def test_is_alive_false_when_stopped(self):
        """Test is alive returns False when process has exited."""
        from process_manager import OpenVikingManager
        
        manager = OpenVikingManager("openviking-server", [])
        
        mock_process = AsyncMock()
        mock_process.returncode = 0
        manager.process = mock_process
        
        assert manager.is_alive() is False

    async def test_is_alive_false_when_not_started(self):
        """Test is_alive returns False when process is None."""
        from process_manager import OpenVikingManager
        
        manager = OpenVikingManager("openviking-server", [])
        
        assert manager.is_alive() is False

@pytest.mark.asyncio
class TestOpenVikingManagerStop:
    """Test process termination and signal handling."""
    
    async def test_stop_sends_sigterm(self):
        """Test that SIGTERM is sent on stop()."""
        from process_manager import OpenVikingManager
        
        manager = OpenVikingManager("openviking-server", [])
        
        mock_process = AsyncMock()
        mock_process.returncode = None
        mock_process.wait = AsyncMock(return_value=None)
        manager.process = mock_process
        
        with patch("asyncio.wait_for", new_callable=AsyncMock, return_value=None) as mock_wait_for:
            await manager.stop()
            
            mock_process.terminate.assert_called_once()
            mock_wait_for.assert_called_once()
            # Check that wait_for was called with timeout=5.0
            call_args = mock_wait_for.call_args
            assert call_args[1]['timeout'] == 5.0

    async def test_stop_sigkill_if_hanging(self):
        """Test SIGKILL is sent if process doesn't terminate after 5s."""
        from process_manager import OpenVikingManager
        
        manager = OpenVikingManager("openviking-server", [])
        
        mock_process = AsyncMock()
        mock_process.returncode = None  # Still running after wait
        mock_process.wait = AsyncMock(side_effect=asyncio.TimeoutError)
        manager.process = mock_process
        
        await manager.stop()
        
        mock_process.terminate.assert_called_once()
        mock_process.kill.assert_called_once()

    async def test_stop_idempotent(self):
        """Test stop() is safe to call multiple times."""
        from process_manager import OpenVikingManager
        
        manager = OpenVikingManager("openviking-server", [])
        
        mock_process = AsyncMock()
        mock_process.returncode = None
        mock_process.wait = AsyncMock(return_value=None)
        manager.process = mock_process
        
        with patch("asyncio.wait_for", new_callable=AsyncMock, return_value=None):
            await manager.stop()
            # Simulate process termination after first stop
            mock_process.returncode = 0
            await manager.stop()
            
            # terminate should only be called once
            mock_process.terminate.assert_called_once()

@pytest.mark.asyncio
class TestOpenVikingManagerWait:
    """Test waiting for process termination."""
    
    async def test_wait_awaits_process(self):
        """Test wait() awaits the process.wait() coroutine."""
        from process_manager import OpenVikingManager
        
        manager = OpenVikingManager("openviking-server", [])
        
        mock_process = AsyncMock()
        mock_process.wait = AsyncMock(return_value=0)
        manager.process = mock_process
        
        return_code = await manager.wait()
        
        assert return_code == 0
        mock_process.wait.assert_called_once()

    async def test_wait_without_start_raises_error(self):
        """Test wait() raises RuntimeError if process not started."""
        from process_manager import OpenVikingManager
        
        manager = OpenVikingManager("openviking-server", [])
        
        with pytest.raises(RuntimeError):
            await manager.wait()

@pytest.mark.asyncio
class TestOpenVikingManagerLifecycle:
    """Test full process lifecycle integration."""
    
    async def test_lifecycle_start_alive_stop(self):
        """Test complete lifecycle: start -> is_alive -> stop."""
        from process_manager import OpenVikingManager
        
        manager = OpenVikingManager("openviking-server", [ "--test"])
        
        mock_process = AsyncMock()
        mock_process.returncode = None
        mock_process.stdout = MagicMock()
        mock_process.stderr = MagicMock()
        mock_process.wait = AsyncMock(return_value=None)
        
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process):
            with patch("asyncio.create_task"):
                with patch("asyncio.wait_for", new_callable=AsyncMock, return_value=None):
                    # Start
                    await manager.start()
                    assert manager.is_alive() is True
                    
                    # Stop
                    await manager.stop()
                    # After stop, the process should have a returncode set
                    mock_process.returncode = 0
                    assert manager.is_alive() is False
