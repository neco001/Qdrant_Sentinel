import pytest
from ast_walker import extract_structural_nodes
from parser_wrapper import parse_file

def test_extract_python_function():
    code = """
class MyClass:
    def my_method(self):
        print("Hello")

def top_level_func():
    return 42
"""
    tree = parse_file("test.py", code)
    nodes = extract_structural_nodes(tree, code.encode("utf-8"))
    
    # We expect 3 nodes: MyClass, my_method, top_level_func
    # Actually, tree-sitter might return nested structures. 
    # Let's check names.
    names = [n['name'] for n in nodes]
    assert "MyClass" in names
    assert "my_method" in names
    assert "top_level_func" in names
    
    # Check details for one node
    func_node = next(n for n in nodes if n['name'] == 'top_level_func')
    assert func_node['type'] in ['function_definition', 'function']
    assert func_node['start_line'] > 0
    assert "def top_level_func():" in func_node['source']
