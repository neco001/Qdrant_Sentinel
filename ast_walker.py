import tree_sitter
from typing import List, Dict, Any, Optional


def extract_structural_nodes(tree: tree_sitter.Tree, source_code: bytes) -> List[Dict[str, Any]]:
    """
    Extracts significant structural nodes from a tree-sitter tree using iterative traversal.
    
    Args:
        tree: The tree-sitter tree to traverse
        source_code: The original source code bytes
    
    Returns:
        A list of dictionaries containing metadata about structural nodes
    """
    if not tree or not tree.root_node:
        return []
    
    # Mapping from tree-sitter node types to our canonical structural types
    STRUCTURAL_TYPES = {
        # Python
        'class_definition', 'function_definition',
        
        # JavaScript/TypeScript
        'class_declaration', 'function_declaration', 'function_expression', 
        'method_definition', 'arrow_function',
        
        # Go
        'type_declaration', 'function_declaration', 'method_declaration',
        
        # Rust
        'struct_item', 'enum_item', 'trait_item', 'impl_item', 'fn_item',
        
        # Java
        'class_declaration', 'interface_declaration', 'method_declaration', 'enum_declaration',
        
        # C/C++
        'struct_specifier', 'union_specifier', 'class_specifier', 
        'function_definition', 'function_declaration',
    }

    results = []
    stack = [tree.root_node]
    
    while stack:
        node = stack.pop()
        
        # Add children to stack for continued traversal (reverse order to maintain original source order)
        for child in reversed(node.children):
            stack.append(child)
            
        # Check if node is structural
        if node.type in STRUCTURAL_TYPES:
            node_info = _extract_node_info(node, source_code)
            if node_info:
                results.append(node_info)
                
    return results


def _extract_node_info(node: tree_sitter.Node, source_code: bytes) -> Optional[Dict[str, Any]]:
    """Extract information from a structural node."""
    name = _get_node_name(node, source_code)
    
    # Get the source code for this node
    source_bytes = source_code[node.start_byte:node.end_byte]
    source_str = source_bytes.decode('utf-8', errors='replace')
    
    # Calculate 1-indexed line numbers
    start_line = node.start_point[0] + 1
    end_line = node.end_point[0] + 1
    
    return {
        'name': name or 'anonymous',
        'type': node.type,
        'source': source_str,
        'start_line': start_line,
        'end_line': end_line,
        'start_byte': node.start_byte,
        'end_byte': node.end_byte
    }


def _get_node_name(node: tree_sitter.Node, source_code: bytes) -> Optional[str]:
    """Extract the name of a node based on its type."""
    # 1. Try explicit 'name' field
    if hasattr(node, 'child_by_field_name'):
        name_node = node.child_by_field_name('name')
        if name_node:
            return name_node.text.decode('utf-8', errors='replace')

    # 2. Special handling for Go type declarations (type_declaration -> type_spec -> name)
    if node.type == 'type_declaration':
        for child in node.children:
            if child.type == 'type_spec':
                name_node = child.child_by_field_name('name')
                if name_node:
                    return name_node.text.decode('utf-8', errors='replace')

    # 3. Fallback: check common identifier child types
    name_node_types = {'identifier', 'name', 'type_identifier', 'declarator'}
    for child in node.children:
        if child.type in name_node_types:
            return child.text.decode('utf-8', errors='replace')
            
    return None
