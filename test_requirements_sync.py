"""
Test for requirements.txt sync with pyproject.toml.

Verifies that tree-sitter dependencies are present in requirements.txt
to ensure consistency between configuration files.
"""
import pytest


def test_tree_sitter_in_requirements():
    """Verify tree-sitter is listed in requirements.txt."""
    with open('requirements.txt', 'r') as f:
        content = f.read()
    
    assert 'tree-sitter' in content.lower(), "tree-sitter not found in requirements.txt"


def test_tree_sitter_languages_in_requirements():
    """Verify tree-sitter-languages is listed in requirements.txt."""
    with open('requirements.txt', 'r') as f:
        content = f.read()
    
    assert 'tree-sitter-languages' in content.lower(), "tree-sitter-languages not found in requirements.txt"


def test_tree_sitter_version_pinned():
    """Verify tree-sitter version is pinned (not unpinned)."""
    with open('requirements.txt', 'r') as f:
        lines = f.readlines()
    
    for line in lines:
        if 'tree-sitter' in line.lower() and not line.strip().startswith('#'):
            assert '==' in line, "tree-sitter version should be pinned with =="
            break
    else:
        pytest.fail("tree-sitter not found in requirements.txt")
