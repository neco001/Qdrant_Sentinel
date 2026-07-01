"""Test that sys.path hack removal doesn't break imports (TDD Phase 1: RED)."""
import sys
import pytest
from pathlib import Path


class TestSysPathCleanup:
    """Verify sys.path hack is removed and imports still work."""

    def test_server_module_no_sys_path_insert(self):
        """Verify mcp_server/server.py does not contain sys.path.insert."""
        server_path = Path(__file__).parent.parent / "mcp_server" / "server.py"
        content = server_path.read_text(encoding="utf-8")
        assert "sys.path.insert" not in content, "Legacy sys.path.insert should be removed from server.py"

    def test_server_module_no_dunder_main(self):
        """Verify mcp_server/server.py does not contain if __name__ == '__main__' block."""
        server_path = Path(__file__).parent.parent / "mcp_server" / "server.py"
        content = server_path.read_text(encoding="utf-8")
        assert 'if __name__' not in content, "Dead __main__ block should be removed from server.py"

    def test_run_module_no_sys_path_insert(self):
        """Verify mcp_server/run.py does not contain sys.path.insert."""
        run_path = Path(__file__).parent.parent / "mcp_server" / "run.py"
        content = run_path.read_text(encoding="utf-8")
        assert "sys.path.insert" not in content, "Legacy sys.path.insert should be removed from run.py"

    def test_server_imports_work_without_sys_path_hack(self):
        """Verify server module imports work without sys.path manipulation."""
        # These imports should work via proper package installation
        from mcp_server.server import search_qdrant, get_search_context, expand_context, find_by_structure
        assert callable(search_qdrant)
        assert callable(get_search_context)
        assert callable(expand_context)
        assert callable(find_by_structure)

    def test_run_imports_work_without_sys_path_hack(self):
        """Verify run module imports work without sys.path manipulation."""
        from mcp_server.run import create_server, run_server, main
        assert callable(create_server)
        assert callable(run_server)
        assert callable(main)
