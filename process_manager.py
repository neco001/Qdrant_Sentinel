"""
Process manager for OpenViking server.

Manages the lifecycle of the openviking-server subprocess as a child process
of Qdrant Sentinel, ensuring proper cleanup on shutdown.
"""

import asyncio
import logging
import os
import shutil
import subprocess
import socket
from typing import List, Optional, Tuple
from typing import List, Optional

logger = logging.getLogger(__name__)


class OpenVikingManager:
    """
    Manages the openviking-server subprocess lifecycle.
    
    Provides async methods to start, stop, and monitor the OpenViking server process.
    Handles graceful shutdown with SIGTERM followed by SIGKILL if necessary.
    """
    
    def __init__(self, executable: str, args: List[str]):
        """
        Initialize the process manager.
        
        Args:
            executable: Path to the openviking-server executable
            args: Command-line arguments to pass to the executable
        """
        self.executable = executable
        self.args = args
        self.process: Optional[asyncio.subprocess.Process] = None
        self._log_tasks: List[asyncio.Task] = []
        self.exit_code: Optional[int] = None
        self._monitor_task: Optional[asyncio.Task] = None
    
    async def _read_stream(self, stream: asyncio.StreamReader, prefix: str) -> None:
        """
        Non-blocking reader for process stdout/stderr.
        
        Prevents deadlock by continuously draining the pipe buffer.
        
        Args:
            stream: The stream to read from
            prefix: Log prefix (e.g., "STDOUT" or "STDERR")
        """
        try:
            while True:
                line = await stream.readline()
                if not line:
                    break
                logger.debug(f"[{prefix}] {line.decode().strip()}")
        except Exception as e:
            logger.error(f"Error reading {prefix}: {e}")
    
    async def start(self) -> None:
        """
        Start the openviking-server process.
        
        Spawns the subprocess with piped stdout/stderr and creates
        background tasks to drain the pipes to prevent deadlock.
        
        On Windows, automatically adds npm global directory to PATH
        to fix subprocess resolution issue for npm-installed packages.
        
        Raises:
            FileNotFoundError: If the executable is not found
        """
        if self.process is not None:
            logger.warning("Process already started")
            return
        
        try:
            # Prepare environment with augmented PATH for Windows npm global packages
            env = os.environ.copy()
            if os.name == 'nt':
                npm_global = os.path.join(os.environ.get('APPDATA', ''), 'npm')
                if os.path.exists(npm_global) and npm_global not in env.get('PATH', ''):
                    env['PATH'] = f"{npm_global};{env.get('PATH', '')}"
                    logger.debug(f"Augmented PATH with npm global directory: {npm_global}")
            
            # Resolve executable path on Windows (handle .cmd/.bat files)
            executable = self.executable
            if os.name == 'nt':
                resolved = shutil.which(self.executable)
                if resolved:
                    executable = resolved
                    logger.debug(f"Resolved executable: {executable}")
                else:
                    logger.warning(f"Could not resolve executable: {self.executable}")
            
            self.process = await asyncio.create_subprocess_exec(
                executable,
                *self.args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            logger.info(f"Started openviking-server (PID: {self.process.pid})")
            
            # Spawn non-blocking log readers to prevent pipe buffer deadlock
            if self.process.stdout:
                self._log_tasks.append(
                    asyncio.create_task(self._read_stream(self.process.stdout, "STDOUT"))
                )
            if self.process.stderr:
                self._log_tasks.append(
                    asyncio.create_task(self._read_stream(self.process.stderr, "STDERR"))
                )
                
        except FileNotFoundError as e:
            logger.error(f"Executable not found: {self.executable}")
            raise
        except Exception as e:
            logger.error(f"Failed to start openviking-server: {e}")
            raise
    
    def is_alive(self) -> bool:
        """
        Check if the process is currently running.
        
        Returns:
            True if process is running (returncode is None), False otherwise
        """
        if self.process is None:
            return False
        return self.process.returncode is None
    
    async def health_check(self) -> bool:
        """
        Perform actual health check by attempting TCP connection to OpenViking port.
        
        Checks if server is actually listening on port 5478, not just process liveness.
        
        Returns:
            True if server is healthy and responding, False otherwise
        """
        if not self.is_alive():
            return False
            
        # Try TCP connection to OpenViking default port
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection('127.0.0.1', 5478),
                timeout=2.0
            )
            writer.close()
            await writer.wait_closed()
            return True
        except (ConnectionRefusedError, asyncio.TimeoutError, socket.error):
            return False
            
    async def _monitor_process(self) -> None:
        """
        Background monitor task that waits for process exit and captures exit code.
        """
        if self.process is None:
            return
            
        self.exit_code = await self.process.wait()
        logger.warning(f"openviking-server exited with code: {self.exit_code}")
        
        # Cancel log readers
        for task in self._log_tasks:
            if not task.done():
                task.cancel()
        self._log_tasks.clear()
    
    async def stop(self) -> None:
        """
        Stop the openviking-server process gracefully.
        
        Sends SIGTERM and waits up to 5 seconds. If the process doesn't
        terminate, sends SIGKILL. This method is idempotent.
        """
        if self.process is None:
            return
        
        if self.process.returncode is not None:
            logger.info("Process already stopped")
            return
        
        try:
            # Send SIGTERM for graceful shutdown
            self.process.terminate()
            logger.info(f"Sent SIGTERM to openviking-server (PID: {self.process.pid})")
            
            # Wait up to 5 seconds for graceful shutdown
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
                logger.info("openviking-server terminated gracefully")
            except asyncio.TimeoutError:
                # Process didn't respond to SIGTERM, force kill
                logger.warning("openviking-server did not terminate gracefully, sending SIGKILL")
                self.process.kill()
                await self.process.wait()
                logger.info("openviking-server killed")
                
        except Exception as e:
            logger.error(f"Error stopping openviking-server: {e}")
        finally:
                    # Cancel monitor task
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            
        # Cancel log reading tasks
            for task in self._log_tasks:
                if not task.done():
                    task.cancel()
            self._log_tasks.clear()
            self.process = None
    
    async def wait(self) -> int:
        """
        Wait for the process to terminate.
        
        Returns:
            The process exit code
            
        Raises:
            RuntimeError: If the process was not started
        """
        if self.process is None:
            raise RuntimeError("Process not started")
        
        return await self.process.wait()
