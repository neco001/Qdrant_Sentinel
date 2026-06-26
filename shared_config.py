# shared_config.py
import os
import tomli
from dataclasses import dataclass
from typing import Optional
from pathlib import Path

class ConfigurationError(Exception):
    """Raised when configuration is missing or invalid."""
    pass

@dataclass
class QdrantConfig:
    url: str

@dataclass
class EmbeddingsConfig:
    base_url: str
    model_name: str
    dimension: int

@dataclass
class OpenVikingConfig:
    cli_path: str
    enabled: bool

@dataclass
class PathsConfig:
    data_root: str
    state_db: str

@dataclass
class AppConfig:
    qdrant: QdrantConfig
    embeddings: EmbeddingsConfig
    openviking: OpenVikingConfig
    paths: PathsConfig

def load_config(project_root: Optional[str] = None) -> AppConfig:
    """
    Loads configuration from qdrant_index.toml.
    
    Args:
        project_root: The root directory of project. If None, uses current working directory.
        
    Returns:
        AppConfig: A dataclass containing all configuration sections.
        
    Raises:
        ConfigurationError: If TOML file is missing or required keys are absent.
        FileNotFoundError: If project_root does not exist.
    """
    if project_root is None:
        project_root = os.getcwd()
    
    root_path = Path(project_root)
    if not root_path.exists():
        raise FileNotFoundError(f"Project root does not exist: {project_root}")
    
    config_path = root_path / "qdrant_index.toml"
    if not config_path.exists():
        raise ConfigurationError(
            f"Configuration file not found at {config_path}. "
            "Please ensure 'qdrant_index.toml' exists in project root."
        )
    
    try:
        with open(config_path, "rb") as f:
            data = tomli.load(f)
    except tomli.TOMLDecodeError as e:
        raise ConfigurationError(f"Failed to parse {config_path}: {e}")
    except Exception as e:
        raise ConfigurationError(f"Failed to read {config_path}: {e}")

    # Validate and extract Qdrant config
    try:
        qdrant_section = data["qdrant"]
        qdrant = QdrantConfig(url=qdrant_section["url"])
    except KeyError as e:
        raise ConfigurationError(f"Missing required key in [qdrant] section: {e}")

    # Validate and extract Embeddings config
    # CRITICAL: This config is shared between Sentinel and MCP to ensure vector compatibility
    try:
        emb_section = data["embeddings"]
        embeddings = EmbeddingsConfig(
            base_url=emb_section["base_url"],
            model_name=emb_section["model_name"],
            dimension=emb_section["dimension"]
        )
    except KeyError as e:
        raise ConfigurationError(f"Missing required key in [embeddings] section: {e}")

    # Validate and extract OpenViking config
    try:
        ov_section = data.get("openviking", {})
        openviking = OpenVikingConfig(
            cli_path=ov_section.get("cli_path", "ov"),
            enabled=ov_section.get("enabled", True)
        )
    except Exception as e:
        raise ConfigurationError(f"Invalid configuration in [openviking] section: {e}")

    # Validate and extract Paths config
    try:
        paths_section = data["paths"]
        paths = PathsConfig(
            data_root=paths_section.get("data_root", "."),
            state_db=paths_section.get("state_db", "sentinel_state.db")
        )
    except KeyError as e:
        raise ConfigurationError(f"Missing required key in [paths] section: {e}")

    return AppConfig(
        qdrant=qdrant,
        embeddings=embeddings,
        openviking=openviking,
        paths=paths
    )
