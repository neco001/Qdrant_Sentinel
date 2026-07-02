# shared_config.py
import os
import tomli
from dataclasses import dataclass, field
from typing import Optional, List
from pathlib import Path

class ConfigurationError(Exception):
    """Raised when configuration is missing or invalid."""
    pass

@dataclass
class QdrantConfig:
    url: str
    collections: List[str] = field(default_factory=list)

@dataclass
class EmbeddingsConfig:
    provider: str = 'openai_compatible'
    base_url: Optional[str] = None
    model_name: Optional[str] = None
    dimension: Optional[int] = None

@dataclass
class OpenVikingConfig:
    cli_path: str
    enabled: bool
    data_path: str = "./openviking_data"

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
        qdrant = QdrantConfig(
            url=qdrant_section["url"],
            collections=qdrant_section.get("collections", [])
        )
    except KeyError as e:
        raise ConfigurationError(f"Missing required key in [qdrant] section: {e}")

    # Validate and extract Embeddings config
    # CRITICAL: This config is shared between Sentinel and MCP to ensure vector compatibility
    # Environment variables override TOML values for unified .env-based configuration
    emb_section = data.get("embeddings", {})
    
    # Read from env vars (override TOML if set)
    env_provider = os.environ.get("EMBEDDING_PROVIDER") or emb_section.get("provider")
    env_base_url = os.environ.get("EMBEDDING_BASE_URL") or emb_section.get("base_url")
    env_model_name = os.environ.get("EMBEDDING_MODEL_NAME") or emb_section.get("model_name")
    env_dimension = os.environ.get("EMBEDDING_DIMENSION") or emb_section.get("dimension")
    
    # Provider is required - must be set in either .env or TOML
    if not env_provider:
        raise ConfigurationError(
            "Missing EMBEDDING_PROVIDER. Set EMBEDDING_PROVIDER in .env or [embeddings] provider in qdrant_index.toml"
        )
    
    # Convert dimension to int if it's a string from env
    if isinstance(env_dimension, str):
        try:
            env_dimension = int(env_dimension)
        except (ValueError, TypeError):
            env_dimension = None
    
    embeddings = EmbeddingsConfig(
        provider=env_provider,
        base_url=env_base_url,
        model_name=env_model_name,
        dimension=env_dimension,
    )

    # Validate and extract OpenViking config
    try:
        ov_section = data.get("openviking", {})
        openviking = OpenVikingConfig(
            cli_path=ov_section.get("cli_path", "ov"),
            enabled=ov_section.get("enabled", True),
            data_path=ov_section.get("data_path", "./openviking_data")
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
