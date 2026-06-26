"""
Integration tests for OpenVikingManager in sentinel.py (TDD Phase 1: RED - Real failing tests).
These tests will FAIL because the integration code doesn't exist yet in sentinel.py.
"""
import pytest
import os
import sys
from pathlib import Path


class TestSentinelOpenVikingIntegration:
    """Test actual integration in sentinel.py - these will FAIL initially."""

    def test_sentinel_imports_process_manager(self):
        """Verify that sentinel.py imports process_manager module."""
        sentinel_path = Path(__file__).parent.parent / "sentinel.py"
        content = sentinel_path.read_text()
        
        # This should fail initially
        assert "import process_manager" in content or "from process_manager import" in content, \
            "sentinel.py should import process_manager module"

    def test_sentinel_checks_openviking_enabled_env(self):
        """Verify that sentinel.py checks OPEN_VIKING_ENABLED environment variable."""
        sentinel_path = Path(__file__).parent.parent / "sentinel.py"
        content = sentinel_path.read_text()
        
        # This should fail initially
        assert "OPEN_VIKING_ENABLED" in content, \
            "sentinel.py should check OPEN_VIKING_ENABLED environment variable"

    def test_sentinel_instantiates_openviking_manager(self):
        """Verify that sentinel.py instantiates OpenVikingManager."""
        sentinel_path = Path(__file__).parent.parent / "sentinel.py"
        content = sentinel_path.read_text()
        
        # This should fail initially
        assert "OpenVikingManager" in content, \
            "sentinel.py should instantiate OpenVikingManager class"

    def test_sentinel_has_try_finally_for_cleanup(self):
        """Verify that sentinel.py has try/finally block for manager cleanup."""
        sentinel_path = Path(__file__).parent.parent / "sentinel.py"
        content = sentinel_path.read_text()
        
        # This should fail initially
        assert "try:" in content and "finally:" in content, \
            "sentinel.py should have try/finally block for cleanup"

    def test_sentinel_calls_manager_stop_in_finally(self):
        """Verify that sentinel.py calls manager.stop() in finally block."""
        sentinel_path = Path(__file__).parent.parent / "sentinel.py"
        content = sentinel_path.read_text()
        
        # This should fail initially
        assert "manager.stop()" in content, \
            "sentinel.py should call manager.stop() in finally block"

    def test_sentinel_has_health_check_loop(self):
        """Verify that sentinel.py has health check loop for OpenViking server."""
        sentinel_path = Path(__file__).parent.parent / "sentinel.py"
        content = sentinel_path.read_text()
        
        # This should fail initially
        assert "is_alive" in content or "health" in content.lower(), \
            "sentinel.py should have health check for OpenViking server"

    def test_sentinel_uses_openviking_server_path_env(self):
        """Verify that sentinel.py uses OPEN_VIKING_SERVER_PATH environment variable."""
        sentinel_path = Path(__file__).parent.parent / "sentinel.py"
        content = sentinel_path.read_text()
        
        # This should fail initially
        assert "OPEN_VIKING_SERVER_PATH" in content, \
            "sentinel.py should use OPEN_VIKING_SERVER_PATH environment variable"

    def test_sentinel_has_async_main_or_wrapper(self):
        """Verify that sentinel.py has async main function or wrapper for async operations."""
        sentinel_path = Path(__file__).parent.parent / "sentinel.py"
        content = sentinel_path.read_text()
        
        # Check for async function definition
        has_async = "async def" in content
        has_await = "await" in content
        
        # This should fail initially
        assert has_async and has_await, \
            "sentinel.py should have async functions with await for OpenVikingManager"
