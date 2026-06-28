"""
ACTUALLY FAILING RED tests for Task 61 - Security Audit.

These tests WILL FAIL with the current implementation because:
1. Path traversal attacks currently flow directly to SyncOpenViking
2. Empty/whitespace queries are not short-circuited
3. No early rejection of null-byte paths

TDD Shackle Protocol: RED → GREEN → REFACTOR
"""

import pytest
import os
from unittest.mock import patch, MagicMock, call
from openviking_client import OpenVikingClient


class TestActualPathTraversalVulnerability:
    """
    THESE TESTS SHOULD FAIL NOW (RED PHASE):
    - Currently, traversal paths like "../../etc/passwd" flow directly to SyncOpenViking
    - After fix (GREEN), SyncOpenViking.add_resource should NOT be called for these
    """

    @patch('openviking_client.SyncOpenViking')
    def test_traversal_paths_should_NOT_reach_syncopenviking(self, mock_sync_openviking: MagicMock):
        """
        RED TEST: This FAILS until fix applied.
        
        Vulnerability: add_resource("../../../etc/shadow") currently calls
        SyncOpenViking.add_resource with that exact dangerous path.
        
        After fix: Should return None and NEVER call underlying client for traversal attempts.
        """
        mock_instance = MagicMock()
        mock_sync_openviking.return_value = mock_instance
        mock_instance.add_resource.return_value = {"id": "should-never-get-here"}
        
        client = OpenVikingClient()
        
        traversal_paths = [
            "../../../../etc/shadow",
            "safe/../../../etc/passwd",
            ".\\..\\..\\..\\Windows\\System32",
            "/tmp/../../etc/passwd",
        ]
        
        # For RED phase: we ASSERT these should NOT reach the mock
        # This test WILL FAIL initially because current code passes them through
        for traversal_path in traversal_paths:
            mock_instance.reset_mock()
            result = client.add_resource(traversal_path)
            
            # After fix:
            # 1. add_resource should return None for dangerous paths
            # 2. SyncOpenViking.add_resource should NOT be called
            
            # RED assertion: If this FAILS, it means the vulnerability EXISTS
            # (which is what we want for RED phase - proving code needs fixing)
            assert result is None, f"Traversal path '{traversal_path}' should be blocked and return None"
            
            # CRITICAL RED assertion: Mock should NOT be called
            # This WILL fail before fixes because paths flow directly through
            mock_instance.add_resource.assert_not_called()


class TestInputShortCircuit:
    """
    THESE TESTS SHOULD FAIL NOW:
    - Empty/whitespace queries should be short-circuited without hitting SyncOpenViking
    """

    @patch('openviking_client.SyncOpenViking')
    def test_empty_query_should_short_circuit(self, mock_sync_openviking: MagicMock):
        """
        RED TEST: Empty string queries should NOT call SyncOpenViking.find()
        
        Current code passes "" directly to client.find()
        After fix: Return [] without calling underlying client
        """
        mock_instance = MagicMock()
        mock_sync_openviking.return_value = mock_instance
        mock_instance.find.return_value = []
        
        client = OpenVikingClient()
        
        result = client.find_resources("")
        
        # Should return empty list (this may already pass)
        assert result == []
        
        # CRITICAL RED assertion: Should NOT have called SyncOpenViking
        # This WILL fail before fixes
        mock_instance.find.assert_not_called()
    
    @patch('openviking_client.SyncOpenViking')
    def test_null_byte_paths_should_be_blocked(self, mock_sync_openviking: MagicMock):
        """
        RED TEST: Paths containing null bytes like "/etc/passwd\x00.jpg"
        are common attack vectors to bypass extension checks.
        
        Should be BLOCKED early.
        """
        mock_instance = MagicMock()
        mock_sync_openviking.return_value = mock_instance
        mock_instance.add_resource.return_value = {"id": "exploit-succeeded"}
        
        client = OpenVikingClient()
        
        null_paths = [
            "/etc/passwd\x00.jpg",
            "script.py\x00.txt",
        ]
        
        for nb_path in null_paths:
            mock_instance.reset_mock()
            result = client.add_resource(nb_path)
            
            # After fix: Blocked
            assert result is None, f"Null-byte path '{nb_path!r}' should be blocked"
            mock_instance.add_resource.assert_not_called()


class TestSafePathsStillWork:
    """
    These should pass even now - ensure we don't break legitimate paths when fixing.
    """
    
    @patch('openviking_client.SyncOpenViking')
    def test_legitimate_paths_work(self, mock_sync_openviking: MagicMock):
        """Control test: Safe paths SHOULD be allowed to reach SyncOpenViking."""
        mock_instance = MagicMock()
        mock_sync_openviking.return_value = mock_instance
        mock_instance.add_resource.return_value = {"id": "legitimate-id"}
        
        client = OpenVikingClient()
        
        safe_paths = [
            "./local_file.txt",
            "subdir/document.md",
            # Note: absolute paths may be valid user file paths, should be allowed
            # The traversal detection is about "../" patterns, not absolute vs relative
        ]
        
        for safe_path in safe_paths:
            mock_instance.reset_mock()
            result = client.add_resource(safe_path)
            
            # Legitimate paths: Should call underlying API
            mock_instance.add_resource.assert_called_once()
            # And return the ID
            assert result == "legitimate-id"
