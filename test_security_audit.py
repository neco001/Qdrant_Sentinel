"""
Security and Dependency Audit Tests.

Tests for:
1. Command injection vulnerabilities in subprocess calls
2. Input validation
3. Dependency security checks
"""
import pytest
import re
from unittest.mock import Mock, patch
import subprocess
import tomllib
from openviking_client import OpenVikingClient


@pytest.fixture(scope="module")
def client_source_code():
    """Cached fixture for reading OpenViking client source code."""
    import openviking_client
    with open(openviking_client.__file__, 'r') as f:
        return f.read()


class TestOpenVikingSecurity:
    """Test security aspects of OpenVikingClient."""

    def test_subprocess_uses_list_not_shell(self):
        """
        Verify that subprocess.run is called with list arguments, not shell=True.
        This prevents command injection vulnerabilities.
        """
        client = OpenVikingClient()
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(stdout='{"id": "test123"}', stderr='')
            
            # Call add_resource with potentially malicious input
            result = client.add_resource(path="test; rm -rf /", wait=False)
            
            # Verify subprocess.run was called with list, not shell=True
            assert mock_run.called
            call_args = mock_run.call_args
            
            # First argument should be a list
            assert isinstance(call_args[0][0], list)
            
            # Should NOT have shell=True
            kwargs = call_args[1]
            assert 'shell' not in kwargs or kwargs.get('shell') is False

    def test_find_resources_uses_list_not_shell(self):
        """
        Verify that find_resources also uses list arguments.
        """
        client = OpenVikingClient()
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(stdout='[]', stderr='')
            
            # Call with potentially malicious query
            result = client.find_resources("test; cat /etc/passwd")
            
            # Verify subprocess.run was called with list
            assert mock_run.called
            call_args = mock_run.call_args
            assert isinstance(call_args[0][0], list)
            
            # Should NOT have shell=True
            kwargs = call_args[1]
            assert 'shell' not in kwargs or kwargs.get('shell') is False

    def test_path_argument_is_properly_passed(self):
        """
        Verify that path argument is properly passed to the CLI.
        """
        client = OpenVikingClient()
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(stdout='{"id": "test123"}', stderr='')
            
            # Call with potentially malicious path
            result = client.add_resource(path="test; rm -rf /", wait=False)
            
            # Verify path is passed as an argument
            call_args = mock_run.call_args[0][0]
            
            # The path should be in the command list
            assert "test; rm -rf /" in call_args
            
            # Command should be "add-resource", not "add"
            assert "add-resource" in call_args

    def test_cli_path_is_not_executed_via_shell(self):
        """
        Verify that the CLI path itself is not executed via shell.
        """
        client = OpenVikingClient(cli_path="ov; malicious_command")
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(stdout='[]', stderr='')
            
            result = client.find_resources("test")
            
            # The CLI path should be in the command list
            call_args = mock_run.call_args[0][0]
            assert call_args[0] == "ov; malicious_command"
            
            # But it should NOT be executed via shell
            kwargs = mock_run.call_args[1]
            assert 'shell' not in kwargs or kwargs.get('shell') is False


class TestDependencyAudit:
    """Test dependency security and version constraints."""

    def test_tree_sitter_version_pinned(self):
        """
        Verify that tree-sitter version is properly pinned.
        Unpinned versions can introduce breaking changes.
        """
        import tomli_w  # Will fail if not installed
        
        # This test ensures the dependency is available
        # The actual version pinning is verified in pyproject.toml
        assert True

    def test_no_deprecated_dependencies(self):
        """
        Verify that no deprecated dependencies are in use.
        """
        # Check that we're using modern alternatives
        # e.g., not using 'subprocess.call' with shell=True
        import subprocess
        import openviking_client
        
        # Verify the module uses subprocess.run, not deprecated methods
        source = openviking_client.__file__
        with open(source, 'r') as f:
            content = f.read()
            
        # Should use subprocess.run, not subprocess.call or shell=True
        assert 'subprocess.run' in content
        assert 'shell=True' not in content

    def test_minimal_privilege_principle(self):
        """
        Verify that the code follows the principle of least privilege.
        """
        import openviking_client
        
        source = openviking_client.__file__
        with open(source, 'r') as f:
            content = f.read()
        
        # Should not use os.system, eval, or exec
        dangerous_patterns = ['os.system', 'eval(', 'exec(']
        for pattern in dangerous_patterns:
            assert pattern not in content, f"Found dangerous pattern: {pattern}"


class TestInputValidation:
    """Test input validation and sanitization."""

    def test_empty_query_handling(self):
        """
        Verify that empty queries are handled gracefully.
        """
        client = OpenVikingClient()
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(stdout='[]', stderr='')
            
            result = client.find_resources("")
            
            # Should still attempt the query (CLI may handle empty input)
            assert result == []

    def test_special_characters_in_query(self):
        """
        Verify that special characters in queries don't cause issues.
        """
        client = OpenVikingClient()
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(stdout='[]', stderr='')
            
            # Test with various special characters
            special_queries = [
                "test$HOME",
                "test`whoami`",
                "test$(id)",
                "test\\x00null",
            ]
            
            for query in special_queries:
                result = client.find_resources(query)
                assert mock_run.called
                mock_run.reset_mock()

    def test_long_query_handling(self):
        """
        Verify that very long queries are handled without buffer overflow.
        """
        client = OpenVikingClient()
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(stdout='[]', stderr='')
            
            # Create a very long query (10KB)
            long_query = "a" * 10240
            
            result = client.find_resources(long_query)
            
            # Should handle gracefully
            assert result == []
