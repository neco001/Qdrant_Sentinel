import pytest
import os
from parser_wrapper import parse_file

def test_parse_python_file():
    code = """
def hello_world():
    print("Hello, world!")
"""
    # Create a temporary file
    test_file = "test_hello.py"
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(code)
    
    try:
        tree = parse_file(test_file, code)
        assert tree is not None
        # Check root node
        assert tree.root_node.type == "module"
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)

def test_parse_unsupported_file():
    code = "Some random text"
    test_file = "test.txt"
    tree = parse_file(test_file, code)
    assert tree is None
