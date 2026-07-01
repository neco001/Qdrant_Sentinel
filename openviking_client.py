import logging
import warnings
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# Try to import SyncOpenViking from openviking package
# Graceful degradation: if import fails, _client will be None
try:
    from openviking import SyncOpenViking, SyncHTTPClient
    _SYNC_OPENVIKING_AVAILABLE = True
except ImportError:
    SyncOpenViking = None  # type: ignore
    SyncHTTPClient = None  # type: ignore
    _SYNC_OPENVIKING_AVAILABLE = False
    logger.warning("SyncOpenViking and SyncHTTPClient not available. OpenVikingClient will operate in degraded mode.")


DEFAULT_DATA_PATH = "./openviking_data"


# Security Validation Helpers - Defense in depth for input sanitization
def _is_path_traversal_attempt(path: str) -> bool:
    r"""Check if path contains path traversal sequences (../ or ..\)."""
    if not isinstance(path, str):
        return False
    # Check for both Unix-style (../) and Windows-style (..\) traversal
    normalized = path.replace('\\', '/')
    return '/../' in normalized or normalized.startswith('../') or normalized.endswith('/..')


def _contains_null_bytes(path: str) -> bool:
    """Check if path contains null bytes (common extension bypass attack vector)."""
    if not isinstance(path, str):
        return False
    return '\x00' in path


def _is_valid_path_for_add_resource(path: str) -> bool:
    """
    Validate that a path is safe before passing to SyncOpenViking.add_resource().
    Returns True if safe, False if blocked. Logs security warnings on blocks.
    """
    if _contains_null_bytes(path):
        logger.warning(f"SECURITY: Blocked path containing null bytes: {path!r}")
        return False
    if _is_path_traversal_attempt(path):
        logger.warning(f"SECURITY: Blocked path traversal attempt: {path!r}")
        return False
    return True


def _is_empty_or_whitespace(query: str) -> bool:
    """Check if query is None, empty, or whitespace-only (for short-circuit optimization)."""
    if query is None:
        return True
    if not isinstance(query, str):
        return True
    return query.strip() == ""


def is_http_server_alive(host='127.0.0.1', port=1933, timeout=0.5) -> bool:
    """Check if HTTP server is alive by sending a HEAD request.

    Args:
        host: Server hostname/IP (default: '127.0.0.1')
        port: Server port (default: 1933)
        timeout: Connection timeout in seconds (default: 0.5)

    Returns:
        bool: True if server responds, False otherwise
    """
    import urllib.request
    url = f'http://{host}:{port}/'
    try:
        # Use HEAD request for efficiency
        req = urllib.request.Request(url, method='HEAD')
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except Exception:
        return False


class OpenVikingClient:
    """
    Wrapper for the native OpenViking SyncOpenViking API (embedded mode).
    Provides methods to add resources and find resources via direct Python API calls.
    
    Backward compatible with the old subprocess-based CLI wrapper interface.
    """

    def __init__(self, data_path: Optional[str] = None, cli_path: Optional[str] = None):
        """
        Initialize the OpenViking client.

        Args:
            data_path: Path to the OpenViking data directory. Defaults to "./openviking_data".
            cli_path: DEPRECATED. Former path to the ov CLI executable. Now ignored with warning.
        """
        # Handle deprecated cli_path parameter for backward compatibility
        if cli_path is not None:
            warnings.warn(
                f"The 'cli_path' parameter is deprecated and will be removed in a future version. "
                f"OpenVikingClient now uses the native SyncOpenViking API (embedded mode). "
                f"Use 'data_path' instead if you need to customize the data directory. "
                f"Provided cli_path: {cli_path}",
                DeprecationWarning,
                stacklevel=2
            )
            logger.warning(f"Deprecated cli_path parameter provided: {cli_path} - ignoring, using native mode")

        import os
        # Determine effective data_path
        self._data_path = data_path if data_path is not None else DEFAULT_DATA_PATH
        self._cli_path = cli_path  # Store for backward compat inspection (e.g., tests checking cli_path attr)
        self.url = os.getenv("OPENVIKING_URL", "http://127.0.0.1:1933")
        
        # Initialize the native SyncOpenViking client with graceful degradation
        self._client: Optional[Any] = None
        self._is_http_client = False
        
        if not _SYNC_OPENVIKING_AVAILABLE:
            logger.warning(
                f"SyncOpenViking not available. OpenVikingClient initialized in degraded mode. "
                f"Methods will return None/empty lists."
            )
            return
        
        # 1. Try to connect to a running HTTP server first to avoid LOCK conflicts
        if SyncHTTPClient is not None:
            from urllib.parse import urlparse
            import time
            try:
                parsed = urlparse(self.url)
                host = parsed.hostname or '127.0.0.1'
                port = parsed.port or 1933
                
                # If running as a daemon service (e.g., via PM2 with OPEN_VIKING_ENABLED='true'),
                # wait for the HTTP server to start up instead of falling back to embedded mode immediately.
                # This prevents startup race conditions where Sentinel locks the database before the server starts.
                is_daemon = os.getenv("OPEN_VIKING_ENABLED") == "true"
                max_retries = 20 if is_daemon else 1
                retry_interval = 0.5
                
                for attempt in range(max_retries):
                    if is_http_server_alive(host=host, port=port):
                        self._client = SyncHTTPClient(url=self.url)
                        self._is_http_client = True
                        logger.info(f"OpenVikingClient connected to HTTP server at {self.url} (attempt {attempt + 1})")
                        return
                    if is_daemon and attempt < max_retries - 1:
                        logger.info(f"Waiting for OpenViking HTTP server at {self.url} to start... (attempt {attempt + 1}/{max_retries})")
                        time.sleep(retry_interval)
                
                logger.debug(f"HTTP server check at {self.url} failed. Falling back to native/embedded.")
            except Exception as http_err:
                logger.debug(f"HTTP server check/connection failed: {http_err}. Falling back to native/embedded.")

        # 2. Fall back to local native DB (Embedded Mode)
        try:
            self._client = SyncOpenViking(path=self._data_path)
            logger.info(f"OpenVikingClient initialized natively with data_path: {self._data_path}")
        except Exception as e:
            logger.error(
                f"Failed to initialize native SyncOpenViking with data_path={self._data_path}: {e}. "
                f"Operating in degraded mode."
            )
            self._client = None

    @property
    def cli_path(self) -> str:
        """
        Backward compatibility property for code that inspects self.cli_path.
        Returns the deprecated cli_path if provided, otherwise a default string.
        """
        return self._cli_path if self._cli_path is not None else "ov"

    def add_resource(
        self, path: str, wait: bool = False, timeout: int = 30
    ) -> Optional[str]:
        """
        Add a resource using the native SyncOpenViking API.

        Args:
            path: Local path or URL to import.
            wait: Ignored in native mode (API is synchronous by design).
            timeout: Ignored in native mode.

        Returns:
            Resource ID string if successful, None otherwise.
        """
        if self._client is None:
            logger.warning(f"Cannot add_resource: SyncOpenViking client not available. Path: {path}")
            return None
        
        # Security: Block path traversal and null-byte attacks before reaching SyncOpenViking
        if not _is_valid_path_for_add_resource(path):
            return None
        
        try:
            # SyncOpenViking.add_resource returns a Dict[str, Any] with resource info
            # build_index=False: Skip redundant embedding since Qdrant already has embeddings
            # SyncHTTPClient does not support the build_index keyword argument.
            if self._is_http_client:
                result = self._client.add_resource(path)
            else:
                result = self._client.add_resource(path, build_index=False)
            
            if result is None:
                logger.warning(f"SyncOpenViking.add_resource returned None for path: {path}")
                return None
            
            # Extract ID from various possible keys (maintaining backward compat logic)
            if isinstance(result, dict):
                resource_id = (
                    result.get("id")
                    or result.get("temp_file_id")
                    or result.get("resource_id")
                    or result.get("uri")
                )
                if resource_id is not None:
                    return str(resource_id)
                else:
                    logger.warning(f"SyncOpenViking.add_resource returned dict but no ID found. Keys: {list(result.keys())}")
                    return None
            else:
                # Unexpected return type - try to stringify
                logger.warning(f"SyncOpenViking.add_resource returned unexpected type: {type(result)}. Attempting string conversion.")
                return str(result)
                
        except Exception as e:
            logger.error(f"Error in native add_resource for path {path}: {e}")
            return None

    def find_resources(self, query: str) -> List[Dict[str, Any]]:
        """
        Find resources using the native SyncOpenViking API.

        Args:
            query: Search query string.

        Returns:
            List of resource dictionaries if successful, empty list otherwise.
        """
        if self._client is None:
            logger.warning(f"Cannot find_resources: SyncOpenViking client not available. Query: {query}")
            return []
        
        # Performance short-circuit: Empty/whitespace queries return immediately
        if _is_empty_or_whitespace(query):
            return []
        
        try:
            # SyncOpenViking.find returns an iterable of FindResult objects (or similar)
            # We need to convert them to dictionaries
            results_iterator = self._client.find(query)
            
            if results_iterator is None:
                return []
            
            results: List[Dict[str, Any]] = []
            
            for item in results_iterator:
                # Convert FindResult-like objects to dicts
                if isinstance(item, dict):
                    results.append(item)
                else:
                    # Try to convert object to dict via __dict__ or attributes
                    try:
                        if hasattr(item, '__dict__'):
                            results.append(dict(item.__dict__))
                        elif hasattr(item, 'model_dump'):
                            # Pydantic v2
                            results.append(item.model_dump())
                        elif hasattr(item, 'dict'):
                            # Pydantic v1
                            results.append(item.dict())
                        else:
                            # Last resort: try dir() based extraction
                            item_dict = {}
                            for attr in dir(item):
                                if not attr.startswith('_'):
                                    try:
                                        val = getattr(item, attr)
                                        if not callable(val):
                                            item_dict[attr] = val
                                    except Exception:
                                        pass
                            if item_dict:
                                results.append(item_dict)
                    except Exception as e:
                        logger.warning(f"Failed to convert FindResult item to dict: {e}")
                        continue
            
            return results
            
        except Exception as e:
            logger.error(f"Error in native find_resources for query '{query}': {e}")
            return []
