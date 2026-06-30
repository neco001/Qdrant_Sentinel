"""MCP server for Qdrant + OpenViking integration.

Provides read-only tools for semantic search, context retrieval, and
structural navigation across indexed codebases.
"""
import sqlite3
from typing import List, Dict, Any, Optional
from pathlib import Path

from qdrant_client import QdrantClient

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared_config import load_config
from embedding_service.factory import EmbeddingServiceFactory
from openviking_client import OpenVikingClient


# Lazy initialization globals
_config = None
_qdrant_client = None
_embedding_service = None
_ov_client = None
_STATE_DB_PATH = None


def _load_config():
    """Load configuration (patchable for testing)."""
    return load_config()


def _create_qdrant_client(url: str):
    """Create Qdrant client (patchable for testing)."""
    return QdrantClient(url=url, check_compatibility=False)


def _create_embedding_service(provider: str, api_key: str, model_name: str, base_url: str, vector_size: int):
    """Create embedding service using factory (patchable for testing)."""
    return EmbeddingServiceFactory.create(
        provider=provider,
        api_key=api_key,
        model_name=model_name,
        base_url=base_url,
        vector_size=vector_size,
    )


def _create_ov_client():
    """Create OpenViking client (patchable for testing)."""
    config = _get_config()
    # Use data_path from config if available, otherwise let OpenVikingClient use its default
    ov_data_path = config.openviking.data_path if config and hasattr(config, 'openviking') and hasattr(config.openviking, 'data_path') else None
    return OpenVikingClient(data_path=ov_data_path)


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


def _get_embedding_service():
    """Lazy load embedding service using factory."""
    global _embedding_service
    if _embedding_service is None:
        config = _get_config()
        import os
        api_key_env = config.embeddings.api_key_env_var or "EMBEDDING_API_KEY"
        api_key = os.getenv(api_key_env)
        if not api_key:
            raise ValueError(f"API key not found in environment variable: {api_key_env}")
        
        _embedding_service = _create_embedding_service(
            provider=config.embeddings.provider,
            api_key=api_key,
            model_name=config.embeddings.model_name,
            base_url=config.embeddings.base_url,
            vector_size=config.embeddings.dimension or 1024,
        )
    return _embedding_service


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
    global _config, _qdrant_client, _embedding_service, _ov_client, _STATE_DB_PATH
    _config = None
    _qdrant_client = None
    _embedding_service = None
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
    embedding_service = _get_embedding_service()
    
    # Verify collection exists (read-only check)
    try:
        qdrant_client.get_collection(collection_name)
    except Exception as e:
        raise Exception(f"Collection '{collection_name}' not found or inaccessible: {e}")
    
    # Generate embedding for query using factory service
    query_vector = embedding_service.embed(query_text)
    
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


if __name__ == "__main__":
    import logging
    import anyio
    from mcp.server.stdio import stdio_server
    from mcp.server.session import ServerSession
    from mcp.server.models import InitializationOptions
    from mcp.types import ServerCapabilities
    import importlib.metadata

    # Set up logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("mcp_server")

    async def receive_loop(session: ServerSession):
        logger.info("Starting MCP server receive loop")
        async for message in session.incoming_messages:
            if isinstance(message, Exception):
                logger.error("Error: %s", message)
                continue
            logger.info("Received message: %s", message)

    async def main():
        try:
            version = importlib.metadata.version("mcp")
            async with stdio_server() as (read_stream, write_stream):
                async with (
                    ServerSession(
                        read_stream,
                        write_stream,
                        InitializationOptions(
                            server_name="Qdrant+OpenViking MCP Server",
                            server_version=version,
                            capabilities=ServerCapabilities(),
                        ),
                    ) as session,
                    write_stream,
                ):
                    await receive_loop(session)
        except Exception as e:
            logger.error("Server error: %s", e)
            raise

    logger.info("Starting Qdrant+OpenViking MCP Server")
    anyio.run(main, backend="trio")