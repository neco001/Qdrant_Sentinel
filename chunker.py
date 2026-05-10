EXT_TO_LANG = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
}

def build_chunks(nodes, source_bytes, max_chars=1500):
    """
    Build chunks from AST nodes with hierarchical context and recursive splitting.
    
    Args:
        nodes: List of node dictionaries from ast_walker
        source_bytes: Source code bytes
        max_chars: Maximum characters per chunk
    
    Returns:
        List of chunk dictionaries
    """
    # Decode source bytes to string
    source = source_bytes.decode('utf-8')
    lines = source.splitlines(keepends=True)
    
    # Build parent-child relationships
    node_hierarchy = {}
    for i, node in enumerate(nodes):
        node_start = node.get('start_line', 0)
        node_end = node.get('end_line', 0)
        
        parent = None
        for j, other_node in enumerate(nodes):
            if i == j:
                continue
            other_start = other_node.get('start_line', 0)
            other_end = other_node.get('end_line', 0)
            
            # Check if current node is within other node's range
            if other_start <= node_start and node_end <= other_end:
                # If we have multiple candidates, pick the most specific (innermost)
                if parent is None:
                    parent = j
                else:
                    prev_parent_node = nodes[parent]
                    if other_start >= prev_parent_node.get('start_line', 0) and other_end <= prev_parent_node.get('end_line', 0):
                        parent = j
        
        node_hierarchy[i] = parent
    
    chunks = []
    
    for idx, node in enumerate(nodes):
        node_start = node.get('start_line', 0)
        node_end = node.get('end_line', 0)
        
        # Extract source code for this node
        node_source = node.get('source', '')
        
        # Determine parent name
        parent_idx = node_hierarchy[idx]
        parent_name = None
        if parent_idx is not None:
            parent_name = nodes[parent_idx].get('name')
        
        # Construct full name
        node_name = node.get('name', f"unnamed_{idx}")
        if parent_name:
            full_name = f"{parent_name}.{node_name}"
        else:
            full_name = node_name
        
        # If node source is within limit, add as single chunk
        if len(node_source) <= max_chars:
            chunk = {
                'name': node_name,
                'parent_name': parent_name,
                'full_name': full_name,
                'type': node.get('type'),
                'start_line': node_start,
                'end_line': node_end,
                'source': node_source,
                'chunk_index': 0
            }
            chunks.append(chunk)
        else:
            # Split the node into multiple chunks
            sub_chunks = _split_node_into_chunks(
                node, node_source, node_start, max_chars, parent_name
            )
            chunks.extend(sub_chunks)
    
    return chunks


def _split_node_into_chunks(node, node_source, node_start_line, max_chars, parent_name):
    """
    Split a large node into multiple chunks.
    """
    chunks = []
    lines = node_source.splitlines(keepends=True)
    
    node_name = node.get('name', 'unnamed')
    if parent_name:
        base_full_name = f"{parent_name}.{node_name}"
    else:
        base_full_name = node_name
    
    current_chunk_lines = []
    current_char_count = 0
    chunk_index = 0
    
    for i, line in enumerate(lines):
        line_len = len(line)
        
        if current_char_count + line_len > max_chars and current_chunk_lines:
            # Finalize current chunk
            chunk_source = ''.join(current_chunk_lines)
            chunk = {
                'name': node_name,
                'parent_name': parent_name,
                'full_name': base_full_name, # In the test I expected full_name to be Database.connect, not Database.connect_0
                'type': node.get('type'),
                'start_line': node_start_line + (i - len(current_chunk_lines)),
                'end_line': node_start_line + i - 1,
                'source': chunk_source,
                'chunk_index': chunk_index
            }
            chunks.append(chunk)
            chunk_index += 1
            current_chunk_lines = []
            current_char_count = 0
            
        current_chunk_lines.append(line)
        current_char_count += line_len
        
    if current_chunk_lines:
        chunk_source = ''.join(current_chunk_lines)
        chunk = {
            'name': node_name,
            'parent_name': parent_name,
            'full_name': base_full_name,
            'type': node.get('type'),
            'start_line': node_start_line + (len(lines) - len(current_chunk_lines)),
            'end_line': node_start_line + len(lines) - 1,
            'source': chunk_source,
            'chunk_index': chunk_index
        }
        chunks.append(chunk)
        
    return chunks
