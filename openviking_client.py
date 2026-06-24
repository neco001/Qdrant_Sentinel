import subprocess
import json
import logging
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
            result = subprocess.run(
                [self.cli_path] + args,
                capture_output=True,
                text=True,
                check=True,
                timeout=timeout
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
        self, name: str, resource_type: str, tags: Optional[List[str]] = None
    ) -> Optional[str]:
        """
        Add a resource using the ov CLI.

        Args:
            name: Name of the resource.
            resource_type: Type of the resource.
            tags: Optional list of tags.

        Returns:
            Resource ID string if successful, None otherwise.
        """
        args = ["add", name, "--type", resource_type]
        
        if tags:
            args.extend(["--tags", ",".join(tags)])

        output = self._run_command(args)
        
        if output:
            try:
                # Assuming the CLI returns the ID directly or in a JSON format
                # Adjust parsing logic based on actual CLI output format
                data = json.loads(output)
                return data.get("id") or data.get("resource_id")
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
