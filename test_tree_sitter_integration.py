"""
Tree-sitter Integration Tests.

Tests for:
1. Python version compatibility (3.12+)
2. tree-sitter importability
3. tree-sitter-languages importability
4. Basic Python code parsing functionality
"""
import sys
import pytest


def test_python_version():
    """Verify Python version is 3.12 or higher."""
    assert sys.version_info >= (3, 12), f"Python {sys.version_info} is not >= 3.12"


def test_tree_sitter_importable():
    """Verify tree-sitter can be imported."""
    try:
        import tree_sitter
    except ImportError as e:
        pytest.fail(f"tree-sitter import failed: {e}")


def test_tree_sitter_languages_importable():
    """Verify tree-sitter-languages can be imported."""
    try:
        import tree_sitter_languages
    except ImportError as e:
        pytest.fail(f"tree-sitter-languages import failed: {e}")


def test_basic_python_parsing():
    """Verify tree-sitter can parse a simple Python code snippet."""
    import tree_sitter
    import tree_sitter_languages
    
    # Get Python parser using get_parser (recommended API)
    parser = tree_sitter_languages.get_parser('python')
    
    # Parse simple Python code (tree-sitter requires bytes)
    code = b"def foo():\n    pass\n"
    tree = parser.parse(code)
    
    # Verify parsing succeeded
    assert tree is not None, "Parser returned None"
    assert tree.root_node is not None, "Root node is None"
    
    # Verify the tree has children (function definition)
    assert tree.root_node.child_count > 0, "Root node has no children"
    
    # Verify the first child is a function_definition
    first_child = tree.root_node.children[0]
    assert first_child.type == 'function_definition', f"Expected 'function_definition', got '{first_child.type}'"
