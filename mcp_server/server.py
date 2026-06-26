"""MCP server for Qdrant + OpenViking integration.

Provides read-only tools for semantic search, context retrieval, and
structural navigation across indexed codebases.
"""
import sqlite3
from typing import List, Dict, Any, Optional
from pathlib import Path

from qdrant_client import QdrantClient
from openai import OpenAI

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared_config import load_config
from openviking_client import OpenVikingClient


# Lazy initialization globals
_config = None
_qdrant_client = None
_embedding_client = None
_ov_client = None
_STATE_DB_PATH = None


def _load_config():
    """Load configuration (patchable for testing)."""
    return load_config()


def _create_qdrant_client(url: str):
    """Create Qdrant client (patchable for testing)."""
    return QdrantClient(url=url)


def _create_embedding_client(api_key: str, base_url: str):
    """Create OpenAI embedding client (patchable for testing)."""
    return OpenAI(api_key=api_key, base_url=base_url)


def _create_ov_client():
    """Create OpenViking client (patchable for testing)."""
    return OpenVikingClient()


def _get_config():
    """Lazy load configuration."""
    global _config
    if _config is None:
        _config = _load_config()
    return _config


def _get_qdrant_client():
    """Lazy load Qdrant client."""
    global _qdrant_client
    if _qdrant_client is None:
        config = _get_config()
        _qdrant_client = _create_qdrant_client(config.qdrant.url)
    return _qdrant_client


def _get_embedding_client():
    """Lazy load OpenAI embedding client."""
    global _embedding_client
    if _embedding_client is None:
        config = _get_config()
        _embedding_client = _create_embedding_client(
            config.embeddings.api_key,
            config.embeddings.base_url
        )
    return _embedding_client


def _get_ov_client():
    """Lazy load OpenViking client."""
    global _ov_client
    if _ov_client is None:
        _ov_client = _create_ov_client()
    return _ov_client


def _get_state_db_path():
    """Lazy load state database path."""
    global _STATE_DB_PATH
    if _STATE_DB_PATH is None:
        config = _get_config()
        _STATE_DB_PATH = config.paths.state_db
    return _STATE_DB_PATH


def reset_state():
    """Reset all cached state for testing purposes.
    
    This function clears all lazy-loaded clients and configuration,
    allowing tests to patch dependencies and force re-initialization.
    """
    global _config, _qdrant_client, _embedding_client, _ov_client, _STATE_DB_PATH
    _config = None
    _qdrant_client = None
    _embedding_client = None
    _ov_client = None
    _STATE_DB_PATH = None


def search_qdrant(collection_name: str, query_text: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Perform semantic search on Qdrant collection.
    
    Args:
        collection_name: Name of the Qdrant collection to search
        query_text: Text query for semantic search
        limit: Maximum number of results to return (default: 5)
    
    Returns:
        List of search results with score, id, and payload
    
    Raises:
        Exception: If collection doesn't exist or connection fails
    """
    # Validate configuration
    config = _get_config()
    if not hasattr(config, 'qdrant'):
        raise AttributeError("Qdrant configuration missing")
    if not hasattr(config, 'embeddings'):
        raise AttributeError("Embeddings configuration missing")
    
    # Get clients
    qdrant_client = _get_qdrant_client()
    embedding_client = _get_embedding_client()
    
    # Verify collection exists (read-only check)
    try:
        qdrant_client.get_collection(collection_name)
    except Exception as e:
        raise Exception(f"Collection '{collection_name}' not found or inaccessible: {e}")
    
    # Generate embedding for query
    response = embedding_client.embeddings.create(
        model=config.embeddings.model_name,
        input=[query_text]
    )
    query_vector = response.data[0].embedding
    
    # Perform search (read-only)
    results = qdrant_client.search(
        collection_name=collection_name,
        query_vector=query_vector,
        limit=limit
    )
    
    # Format results
    formatted_results = []
    for result in results:
        formatted_results.append({
            "id": str(result.id),
            "score": result.score,
            "payload": result.payload
        })
    
    return formatted_results


def get_search_context(qdrant_id: str, tier: str = "L1") -> List[Dict[str, Any]]:
    """Retrieve context layers from OpenViking for a Qdrant point.
    
    Args:
        qdrant_id: Qdrant point ID to get context for
        tier: Context tier - "L0" (original), "L1" (summarized), "L2" (abstract)
    
    Returns:
        List of context resources from OpenViking
    
    Raises:
        ValueError: If tier is invalid
        FileNotFoundError: If OpenViking CLI is not available
    """
    # Validate tier
    valid_tiers = ["L0", "L1", "L2"]
    if tier not in valid_tiers:
        raise ValueError(f"Invalid tier '{tier}'. Must be one of: {valid_tiers}")
    
    # Query OpenViking for context (read-only)
    ov_client = _get_ov_client()
    query = f"qdrant_id:{qdrant_id} tier:{tier}"
    
    try:
        resources = ov_client.find_resources(query)
        return resources
    except (FileNotFoundError, RuntimeError, Exception) as e:
        # Graceful degradation: return empty list on OpenViking failures
        # This prevents the MCP tool from crashing if OpenViking is unavailable
        return []


def expand_context(uri: str, direction: str = "both") -> Dict[str, List[Dict[str, Any]]]:
    """Expand context by finding parent/child relationships in SQLite.
    
    Args:
        uri: URI of the resource to expand context for
        direction: "parent" (find parents), "child" (find children), or "both"
    
    Returns:
        Dictionary with 'parents' and/or 'children' lists containing Qdrant IDs
    
    Raises:
        sqlite3.Error: If database connection fails
    """
    result = {}
    
    # Connect to SQLite in read-only mode
    db_path = _get_state_db_path()
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    
    try:
        cursor = conn.cursor()
        
        if direction in ["parent", "both"]:
            # Find parent Qdrant IDs
            cursor.execute("""
                SELECT qdrant_id FROM ov_mappings 
                WHERE ov_resource_id = ?
            """, (uri,))
            
            parents = [{"qdrant_id": row[0]} for row in cursor.fetchall()]
            result["parents"] = parents
        
        if direction in ["child", "both"]:
            # Find child Qdrant IDs
            cursor.execute("""
                SELECT ov_resource_id FROM ov_mappings 
                WHERE qdrant_id = ?
            """, (uri,))
            
            children = [{"uri": row[0]} for row in cursor.fetchall()]
            result["children"] = children
        
        return result
    
    finally:
        conn.close()


def find_by_structure(path_pattern: str) -> List[Dict[str, Any]]:
    """Find files matching a path pattern in SQLite.
    
    Args:
        path_pattern: Path pattern (supports wildcards like "src/*.py")
    
    Returns:
        List of matching files with Qdrant ID, URI, and timestamp
    
    Raises:
        sqlite3.Error: If database connection fails
    """
    # Connect to SQLite in read-only mode
    db_path = _get_state_db_path()
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    
    try:
        cursor = conn.cursor()
        
        # Use LIKE for pattern matching (read-only)
        pattern = path_pattern.replace("*", "%")
        cursor.execute("""
            SELECT qdrant_id, ov_resource_id, indexed_at 
            FROM ov_mappings 
            WHERE ov_resource_id LIKE ?
        """, (pattern,))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "qdrant_id": row[0],
                "uri": row[1],
                "indexed_at": row[2]
            })
        
        return results
    
    finally:
        conn.close()
