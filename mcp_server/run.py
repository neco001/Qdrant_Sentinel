"""MCP server entry point and initialization.

Creates and runs the MCP server with Qdrant + OpenViking integration tools.
"""
import sys
from pathlib import Path
from typing import Dict, Any, List
from mcp.server import Server
from mcp import stdio_server, Tool

from shared_config import load_config, AppConfig
from mcp_server.server import (
    search_qdrant,
    get_search_context,
    expand_context,
    find_by_structure
)


# Module-level shared configuration
shared_config: Dict[str, Any] = None


def load_shared_config() -> Dict[str, Any]:
    """Load shared configuration using shared_config.load_config.
    
    Returns:
        Configuration dictionary with qdrant, embeddings, openviking, and paths sections
    
    Raises:
        RuntimeError: If configuration cannot be loaded
    """
    global shared_config
    try:
        config = load_config()
        shared_config = config
        return config
    except Exception as e:
        raise RuntimeError(f"Failed to load configuration: {e}")


def create_server() -> Server:
    """Create and configure MCP server instance.
    
    Returns:
        Configured MCP Server instance
    
    Raises:
        RuntimeError: If configuration is missing or invalid
    """
    # Load configuration
    config = load_shared_config()
    
    if config is None:
        raise RuntimeError("Configuration is missing")
    
    # Validate required configuration sections
    if not isinstance(config, AppConfig) or not hasattr(config, 'qdrant'):
        raise RuntimeError("Qdrant configuration is missing")
    
    # Create MCP server
    server = Server("qdrant-sentinel")
    
    # Register tools
    @server.list_tools()
    async def list_tools() -> List[Tool]:
        """List available MCP tools."""
        return [
            Tool(
                name="search_qdrant",
                description="Perform semantic search on Qdrant collection",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "collection_name": {
                            "type": "string",
                            "description": "Name of the Qdrant collection to search"
                        },
                        "query_text": {
                            "type": "string",
                            "description": "Text query for semantic search"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results to return",
                            "default": 5
                        }
                    },
                    "required": ["collection_name", "query_text"]
                }
            ),
            Tool(
                name="get_search_context",
                description="Retrieve context layers from OpenViking for a Qdrant point",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "qdrant_id": {
                            "type": "string",
                            "description": "Qdrant point ID to get context for"
                        },
                        "tier": {
                            "type": "string",
                            "description": "Context tier - L0 (original), L1 (summarized), L2 (abstract)",
                            "default": "L1",
                            "enum": ["L0", "L1", "L2"]
                        }
                    },
                    "required": ["qdrant_id"]
                }
            ),
            Tool(
                name="expand_context",
                description="Expand context by finding parent/child relationships in SQLite",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "uri": {
                            "type": "string",
                            "description": "URI of the resource to expand context for"
                        },
                        "direction": {
                            "type": "string",
                            "description": "Direction to expand - parent, child, or both",
                            "default": "both",
                            "enum": ["parent", "child", "both"]
                        }
                    },
                    "required": ["uri"]
                }
            ),
            Tool(
                name="find_by_structure",
                description="Find files matching a path pattern in SQLite",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path_pattern": {
                            "type": "string",
                            "description": "Path pattern (supports wildcards like 'src/*.py')"
                        }
                    },
                    "required": ["path_pattern"]
                }
            )
        ]
    
    @server.call_tool()
    async def call_tool(name: str, arguments: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Route tool calls to appropriate handler."""
        if name == "search_qdrant":
            return search_qdrant(
                collection_name=arguments["collection_name"],
                query_text=arguments["query_text"],
                limit=arguments.get("limit", 5)
            )
        elif name == "get_search_context":
            return get_search_context(
                qdrant_id=arguments["qdrant_id"],
                tier=arguments.get("tier", "L1")
            )
        elif name == "expand_context":
            return expand_context(  # type: ignore
                uri=arguments["uri"],
                direction=arguments.get("direction", "both")
            )
        elif name == "find_by_structure":
            return find_by_structure(
                path_pattern=arguments["path_pattern"]
            )
        else:
            raise ValueError(f"Unknown tool: {name}")
    
    return server


async def run_server():
    """Async entry point for MCP server."""
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


def main():
    """Main entry point for MCP server.
    
    Creates server and runs stdio_server async context manager.
    Handles KeyboardInterrupt gracefully.
    """
    import asyncio
    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        # Graceful shutdown on Ctrl+C
        sys.exit(0)
    except Exception as e:
        # Log exception and exit
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
