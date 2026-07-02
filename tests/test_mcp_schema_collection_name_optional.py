"""Tests for Task 3: Make collection_name optional in MCP tool schema

These are RED tests that should FAIL with the current schema (where collection_name is required).
After implementation, these tests should PASS.
"""

import pytest
from pathlib import Path


class TestMcpSchemaCollectionNameOptional:
    """Tests to verify collection_name is optional in search_qdrant tool schema"""

    @pytest.fixture
    def run_py_content(self):
        """Read the run.py file content"""
        run_py_path = Path(__file__).parent.parent / "mcp_server" / "run.py"
        return run_py_path.read_text(encoding="utf-8")

    def test_search_qdrant_schema_collection_name_not_in_required(self, run_py_content):
        """
        RED Test 1: Verify 'collection_name' is NOT in the 'required' array
        for search_qdrant tool in list_tools().
        
        Current schema (should fail this test):
            "required": ["collection_name", "query_text"]
        
        Expected schema (after fix):
            "required": ["query_text"]
        """
        # First verify the test structure exists (sanity check)
        assert 'search_qdrant' in run_py_content
        assert 'inputSchema' in run_py_content
        assert '"required":' in run_py_content
        
        # This is the RED test - it should FAIL with current code
        # because "required": ["collection_name", "query_text"] currently exists
        
        # Check that collection_name is NOT in the required array
        # Look for the specific required line near search_qdrant
        import re
        
        # Find all required arrays
        required_matches = re.findall(r'"required":\s*\[([^\]]+)\]', run_py_content)
        
        # The search_qdrant required array should NOT contain collection_name
        search_qdrant_required = None
        for match in required_matches:
            if 'query_text' in match or 'collection_name' in match:
                search_qdrant_required = match
                break
        
        # Sanity check: we found the required array
        assert search_qdrant_required is not None, "Could not find search_qdrant required array"
        
        # RED TEST: collection_name should NOT be in required
        assert '"collection_name"' not in search_qdrant_required, \
            f"Expected 'collection_name' to NOT be in required, but found: {search_qdrant_required}"

    def test_search_qdrant_schema_collection_name_description_optional(self, run_py_content):
        """
        RED Test 2: Verify 'collection_name' property description indicates it's optional
        and defaults to first collection in qdrant_index.toml.
        
        Current description (may fail this test):
            "description": "Name of the Qdrant collection to search"
        
        Expected description (after fix):
            "description": "Optional. Name of the Qdrant collection to search. 
                           If omitted, defaults to the first collection in qdrant_index.toml"
        """
        # Find the collection_name property description
        import re
        
        # Look for collection_name property block
        # Pattern: "collection_name": { ... "description": "..." }
        collection_pattern = r'"collection_name":\s*\{[^}]*"description":\s*"([^"]+)"'
        matches = re.findall(collection_pattern, run_py_content, re.DOTALL)
        
        assert len(matches) > 0, "Could not find collection_name property description"
        
        description = matches[0].lower()
        
        # RED TEST: description should mention it's optional
        assert "optional" in description, \
            f"Expected description to contain 'optional', got: {matches[0]}"
        
        # Description should mention default collection from config
        assert "first" in description or "default" in description, \
            f"Expected description to mention 'first' or 'default' collection, got: {matches[0]}"
        
        assert "qdrant_index.toml" in description or "config" in description, \
            f"Expected description to mention 'qdrant_index.toml' or 'config', got: {matches[0]}"

    def test_call_tool_uses_get_for_collection_name(self, run_py_content):
        """
        RED Test 3: Verify the call_tool handler for search_qdrant uses
        arguments.get("collection_name") instead of arguments["collection_name"],
        so it can handle cases where collection_name is not provided.
        
        Current code (should fail this test):
            collection_name=arguments["collection_name"],
        
        Expected code (after fix):
            collection_name=arguments.get("collection_name"),
        """
        # Look for the search_qdrant call in call_tool handler
        import re
        
        # Find how collection_name is accessed in call_tool
        # Pattern: collection_name=arguments[
        direct_access_pattern = r'collection_name\s*=\s*arguments\["collection_name"\]'
        get_access_pattern = r'collection_name\s*=\s*arguments\.get\("collection_name"\)'
        
        direct_matches = re.findall(direct_access_pattern, run_py_content)
        get_matches = re.findall(get_access_pattern, run_py_content)
        
        # RED TEST: Should use .get() not direct indexing
        assert len(direct_matches) == 0, \
            f"Expected no direct arguments['collection_name'] access, but found {len(direct_matches)} occurrence(s)"
        
        # Should use .get() instead
        assert len(get_matches) > 0, \
            "Expected arguments.get('collection_name') but found none"
