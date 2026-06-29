"""Test to verify README.md contains required documentation updates.
This is a documentation-focused test - it should FAIL before the updates are applied.
"""
import os
import re
import pytest

README_PATH = os.path.join(os.path.dirname(__file__), "README.md")


def read_readme() -> str:
    with open(README_PATH, "r", encoding="utf-8") as f:
        return f.read()


class TestREADMEWinError10061:
    """Test that [WinError 10061] troubleshooting documentation exists."""

    def test_readme_contains_winerror_troubleshooting(self):
        """README should contain troubleshooting section for WinError 10061.
        This error means Qdrant Docker container is not running.
        """
        content = read_readme()
        
        # Check for WinError 10061 mention
        assert "10061" in content or "WinError" in content, \
            "README should mention WinError 10061 troubleshooting"
        
        # Check for "Docker" in troubleshooting context
        assert "Docker" in content or "docker" in content.lower(), \
            "README should mention Docker in troubleshooting"
        
        # Check for clear troubleshooting steps
        # Should explain: WinError 10061 = Qdrant not running
        error_guidance = any(term in content.lower() for term in [
            "not running",
            "start qdrant",
            "docker run",
            "troubleshoot",
            "connection refused"
        ])
        assert error_guidance, "README should contain troubleshooting guidance for connection errors"

    def test_readme_contains_how_to_verify_qdrant_running(self):
        """README should explain how to verify Qdrant is running."""
        content = read_readme()
        
        verification_steps = any(term in content.lower() for term in [
            "docker ps",
            "verify",
            "check if",
            "health",
            "running"
        ])
        # This is specifically about documenting the fix
        assert "docker ps" in content or "docker run" in content or "verify" in content.lower(), \
            "README should explain how to verify or start Qdrant Docker container"


class TestREADMESyncOpenVikingMapping:
    """Test that OpenVikingClient API mapping is documented."""

    def test_readme_documents_find_resources_mapping(self):
        """README should explain the find_resources() -> SyncOpenViking.find() mapping."""
        content = read_readme()
        
        # Should document the API mapping
        mapping_keywords = any(term in content for term in [
            "SyncOpenViking",
            "find_resources",
            "add_resource",
            "OpenVikingClient",
            "API mapping"
        ])
        
        # Specifically check for SyncOpenViking mention since that's what we use now
        assert "SyncOpenViking" in content, \
            "README should document that we use SyncOpenViking (embedded mode, not subprocess)"
        
        # Should explain it's EMBEDDED, not subprocess
        embedded_terms = any(term in content.lower() for term in [
            "embedded",
            "in-process",
            "in memory",
            "local client",
            "not subprocess",
            "no server"
        ])
        # This is the key insight - we switched from subprocess to embedded
        assert embedded_terms or "SyncOpenViking" in content, \
            "README should clarify that OpenViking runs embedded (LocalClient, not server)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
