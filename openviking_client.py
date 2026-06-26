import subprocess
import json
import logging
import os
import shutil
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class OpenVikingClient:
    """
    Wrapper for the OpenViking (ov) CLI tool.
    Provides methods to add resources and find resources via subprocess calls.
    """

    def __init__(self, cli_path: str = "ov"):
        """
        Initialize the OpenViking client.

        Args:
            cli_path: Path to the ov CLI executable. Defaults to "ov".
        """
        self.cli_path = cli_path

    def _run_command(self, args: List[str], timeout: int = 30) -> Optional[str]:
        """
        Internal helper to execute a subprocess command safely.

        Args:
            args: List of arguments to pass to the CLI.
            timeout: Seconds to wait before timing out.

        Returns:
            stdout string if successful, None if failed.
        """
        try:
            # Prepare environment with augmented PATH for Windows npm global packages
            env = os.environ.copy()
            if os.name == 'nt':
                npm_global = os.path.join(os.environ.get('APPDATA', ''), 'npm')
                if os.path.exists(npm_global) and npm_global not in env.get('PATH', ''):
                    env['PATH'] = f"{npm_global};{env.get('PATH', '')}"
                    logger.debug(f"Augmented PATH with npm global directory: {npm_global}")
            
            # Resolve executable path on Windows (handle .cmd/.bat files)
            cli_path = self.cli_path
            if os.name == 'nt':
                resolved = shutil.which(self.cli_path)
                if resolved:
                    cli_path = resolved
                    logger.debug(f"Resolved OpenViking CLI: {cli_path}")
                else:
                    logger.warning(f"Could not resolve OpenViking CLI: {self.cli_path}")
            
            result = subprocess.run(
                [cli_path] + args,
                capture_output=True,
                text=True,
                check=True,
                timeout=timeout,
                env=env
            )
            return result.stdout.strip()
        except FileNotFoundError:
            logger.error(f"OpenViking CLI not found at: {self.cli_path}")
            return None
        except subprocess.TimeoutExpired:
            logger.error(f"OpenViking CLI command timed out: {' '.join(args)}")
            return None
        except subprocess.CalledProcessError as e:
            logger.error(
                f"OpenViking CLI command failed with exit code {e.returncode}. "
                f"Stderr: {e.stderr.strip() if e.stderr else 'Empty'}. "
                f"Stdout: {e.stdout.strip() if e.stdout else 'Empty'}"
            )
            return None
        except Exception as e:
            logger.error(f"Unexpected error running OpenViking CLI: {e}")
            return None

    def add_resource(
        self, path: str, wait: bool = False, timeout: int = 30
    ) -> Optional[str]:
        """
        Add a resource using the ov CLI.

        Args:
            path: Local path or URL to import.
            wait: Whether to wait until processing is complete.
            timeout: Seconds to wait before timing out.

        Returns:
            Resource ID string if successful, None otherwise.
        """
        args = ["add-resource", path]
        
        if wait:
            args.append("--wait")

        output = self._run_command(args, timeout=timeout)
        
        if output:
            try:
                # Parse JSON output to extract resource ID
                data = json.loads(output)
                # OpenViking may return the ID in various formats
                if isinstance(data, dict):
                    return data.get("id") or data.get("temp_file_id") or data.get("resource_id") or data.get("uri")
                elif isinstance(data, list) and len(data) > 0:
                        return data[0].get("id") or data[0].get("temp_file_id") or data[0].get("resource_id")
                else:
                    return str(data)
            except json.JSONDecodeError:
                # Fallback: if output is not JSON, assume it is the ID itself
                return output
        
        return None

    def find_resources(self, query: str) -> List[Dict[str, Any]]:
        """
        Find resources using the ov CLI.

        Args:
            query: Search query string.

        Returns:
            List of resource dictionaries if successful, empty list otherwise.
        """
        args = ["find", query]

        output = self._run_command(args)

        if output:
            try:
                data = json.loads(output)
                # Ensure we return a list, even if CLI returns a dict with a 'results' key
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict) and "results" in data:
                    return data["results"]
                elif isinstance(data, dict) and "items" in data:
                    return data["items"]
                else:
                    return [data]
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse OpenViking find response: {e}")
                return []
        
        return []
