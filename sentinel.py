import os
import shutil
import sys
# Fix OpenSSL uplink crash caused by AVG/Avast SSLKEYLOGFILE injection on Windows
os.environ.pop('SSLKEYLOGFILE', None)

import time
import hashlib
import sqlite3
import json
import logging
import asyncio
import signal
from pathlib import Path
from typing import List, Set, Dict, Any, Optional
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from qdrant_client import QdrantClient
from qdrant_client.http import models
from openai import OpenAI
from dotenv import load_dotenv
from tqdm import tqdm
import pathspec
import uuid
import tomli_w
import threading

# Global shutdown flag for PM2 compatibility
shutdown_flag = False

# Global rate limiter for embedding API (max 2 concurrent requests)
EMBEDDING_SEMAPHORE = threading.Semaphore(2)

logger = logging.getLogger(__name__)
import os
from parser_wrapper import parse_file
from ast_walker import extract_structural_nodes
from chunker import build_chunks, EXT_TO_LANG
from openviking_client import OpenVikingClient

# Load environment variables
load_dotenv()

def _load_from_env() -> tuple:
    """Load configuration from environment variables as fallback."""
    return (
        os.getenv("QDRANT_URL", "http://127.0.0.1:6333"),
        os.getenv("EMBEDDING_API_KEY"),
        os.getenv("EMBEDDING_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"),
        os.getenv("EMBEDDING_MODEL_NAME", "text-embedding-v4kt"),
        "sentinel_state.db",
        None
    )

# Configuration
try:
    from shared_config import load_config, ConfigurationError
    
    config = load_config()
    
    # Load from config file with fallback to environment variables
    QDRANT_URL = config.qdrant.url if hasattr(config, 'qdrant') else os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
    EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY")  # Always from environment for security
    EMBEDDING_BASE_URL = config.embeddings.base_url if hasattr(config, 'embeddings') else os.getenv("EMBEDDING_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
    EMBEDDING_MODEL_NAME = config.embeddings.model_name if hasattr(config, 'embeddings') else os.getenv("EMBEDDING_MODEL_NAME", "text-embedding-v4")
    STATE_DB_PATH = config.paths.state_db if hasattr(config, 'paths') else "sentinel_state.db"
    
    # Expose config as module-level attribute for backward compatibility
    _config = config
    
except ImportError:
    # Fallback to environment variables if shared_config is not available
    logger.warning("shared_config module not found, using environment variables")
    QDRANT_URL, EMBEDDING_API_KEY, EMBEDDING_BASE_URL, EMBEDDING_MODEL_NAME, STATE_DB_PATH, _config = _load_from_env()

except ConfigurationError as e:
    # Fallback to environment variables if configuration fails
    logger.warning(f"Configuration error: {e}, using environment variables")
    QDRANT_URL, EMBEDDING_API_KEY, EMBEDDING_BASE_URL, EMBEDDING_MODEL_NAME, STATE_DB_PATH, _config = _load_from_env()
class QdrantSentinel:
    VECTOR_SIZE = 1024  # Explicit class-level constant (task 8 completion)
    AUTO_UPDATE_GITIGNORE = True  # Server-managed .gitignore updates (user-chosen Option A)
    def __init__(self, watch_paths: List[str]):
        self.watch_paths = [Path(p).resolve() for p in watch_paths]
        self.client = QdrantClient(url=QDRANT_URL, check_compatibility=False)
        self.ai_client = OpenAI(api_key=EMBEDDING_API_KEY, base_url=EMBEDDING_BASE_URL)
        # Use data_path from config if available, otherwise let OpenVikingClient use its default
        ov_data_path = _config.openviking.data_path if _config and hasattr(_config, 'openviking') and hasattr(_config.openviking, 'data_path') else None
        self.ov_client = OpenVikingClient(data_path=ov_data_path)
        self.init_db()

    def init_db(self):
        """Initialize SQLite DB to store file hashes and OpenViking ID mappings."""
        with sqlite3.connect(STATE_DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS file_states (
                    file_path TEXT PRIMARY KEY,
                    hash TEXT,
                    last_indexed REAL,
                    collection_name TEXT
                )
            """)
            # Create OpenViking ID mapping table for bidirectional mapping
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ov_mappings (
                    qdrant_id TEXT PRIMARY KEY,
                    ov_resource_id TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Create indexes for efficient reverse lookups and file-based queries
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ov_resource ON ov_mappings(ov_resource_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ov_file ON ov_mappings(file_path)")

    def get_file_hash(self, path: Path) -> str:
        """Calculate MD5 hash of a file."""
        hasher = hashlib.md5()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def get_collection_name(self, project_path: Path) -> str:
        """Derive collection name from project path for human readability."""
        return f"qdr-{project_path.name.lower()}"

    def should_ignore(self, path: Path, project_root: Path) -> bool:
        """Check if file should be ignored based on various ignore files."""
        # 1. Hardcoded common patterns as first defense
        hardcoded_ignore = {
            '.git', '__pycache__', 'node_modules', '.venv', 'venv', 
            '.vscode', '.idea', 'dist', 'build'
        }
        if any(part in hardcoded_ignore for part in path.parts):
            return True

        # 2. Collect all ignore files
        ignore_files = [
            project_root / ".gitignore",
            project_root / ".git" / "info" / "exclude",
            project_root / ".rooignore"
        ]
        
        try:
            rel_path = str(path.relative_to(project_root))
        except ValueError:
            return True

        for ignore_file in ignore_files:
            if ignore_file.exists():
                try:
                    with open(ignore_file, 'r', encoding='utf-8') as f:
                        spec = pathspec.PathSpec.from_lines('gitwildmatch', f)
                        if spec.match_file(rel_path):
                            return True
                except Exception:
                    pass

        # 3. Skip binary and large files
        if path.is_file():
            if path.stat().st_size > 500 * 1024: # Skip files > 500KB for speed
                return True
            try:
                with open(path, 'tr', encoding='utf-8') as f:
                    f.read(512)
            except Exception:
                return True

        return False

    def chunk_text(self, text: str, chunk_size: int = 1000) -> List[str]:
        """Simple line-based chunking."""
        lines = text.split('\n')
        chunks = []
        current_chunk = []
        current_size = 0
        
        for line in lines:
            if current_size + len(line) > chunk_size and current_chunk:
                chunks.append('\n'.join(current_chunk))
                current_chunk = []
                current_size = 0
            current_chunk.append(line)
            current_size += len(line)
        
        if current_chunk:
            chunks.append('\n'.join(current_chunk))
        return chunks

    def index_file(self, file_path: Path, project_root: Path):
        """Index a single file into Qdrant."""
        try:
            if self.should_ignore(file_path, project_root):
                return

            current_hash = self.get_file_hash(file_path)
            collection_name = self.get_collection_name(project_root)
            
            with sqlite3.connect(STATE_DB_PATH) as conn:
                res = conn.execute("SELECT hash FROM file_states WHERE file_path = ?", (str(file_path),)).fetchone()
                if res and res[0] == current_hash:
                    return

            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Semantic chunking attempt
            source_bytes = content.encode('utf-8', errors='replace')
            tree = parse_file(str(file_path), content)
            
            semantic_chunks = []
            if tree:
                nodes = extract_structural_nodes(tree, source_bytes)
                semantic_chunks = build_chunks(nodes, source_bytes)
            
            final_chunks = []
            final_payloads = []

            if semantic_chunks:
                # Use semantic chunks with extended metadata
                language = EXT_TO_LANG.get(file_path.suffix.lower(), "unknown")
                for c in semantic_chunks:
                    final_chunks.append(c['source'])
                    final_payloads.append({
                        "text": c['source'],
                        "file_path": str(file_path.relative_to(project_root)),
                        "project": project_root.name,
                        "chunk_index": c['chunk_index'],
                        "symbol_name": c['name'],
                        "symbol_type": c['type'],
                        "parent_symbol": c.get('parent_name'),
                        "language": language,
                        "line_range": [c['start_line'], c['end_line']]
                    })
            else:
                # Fallback to simple line-based chunking
                chunks = self.chunk_text(content)
                for i, chunk in enumerate(chunks):
                    if not chunk.strip(): continue
                    final_chunks.append(chunk)
                    final_payloads.append({
                        "text": chunk, 
                        "file_path": str(file_path.relative_to(project_root)), 
                        "project": project_root.name, 
                        "chunk_index": i
                    })

            if not final_chunks:
                return

            # Ensure collection exists (atomic check)
            if not self.client.collection_exists(collection_name):
                try:
                    self.client.create_collection(
                        collection_name=collection_name,
                        vectors_config=models.VectorParams(size=self.VECTOR_SIZE, distance=models.Distance.COSINE),  # Fixed VECTOR_SIZE reference to class-level constant
                        on_disk_payload=True
                    )
                except Exception:
                    pass # Probably created by another thread

            all_embeddings = []
            # Alibaba/OpenAI support batching multiple inputs in one request
            for j in range(0, len(final_chunks), 10):
                batch = [c.strip() for c in final_chunks[j:j+10] if c.strip()]
                if not batch: continue
                
                # Rate limiting: max 2 concurrent embedding requests
                with EMBEDDING_SEMAPHORE:
                    emb_res = self.ai_client.embeddings.create(
                        input=batch,
                        model=EMBEDDING_MODEL_NAME,
                        dimensions=self.VECTOR_SIZE  # Ensure consistent dimension
                    )
                    all_embeddings.extend([e.embedding for e in emb_res.data])
                    time.sleep(0.5)  # Rate limiting to avoid 429 errors

            # Clear old points for this file to prevent duplicates and orphaned chunks
            rel_path = str(file_path.relative_to(project_root))
            if self.client.collection_exists(collection_name):
                self.client.delete(
                    collection_name=collection_name,
                    points_selector=models.Filter(
                        must=[
                            models.FieldCondition(key="file_path", match=models.MatchValue(value=rel_path)),
                        ]
                    )
                )

            points = []
            for i, (payload, embedding) in enumerate(zip(final_payloads, all_embeddings)):
                # Use a deterministic ID based on file path and chunk index to allow overwriting
                point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{collection_name}_{rel_path}_{i}"))
                points.append(models.PointStruct(
                    id=point_id, vector=embedding,
                    payload=payload
                ))

            if points:
                # Dual-write pipeline: Qdrant + OpenViking
                with sqlite3.connect(STATE_DB_PATH) as conn:
                    for point in points:
                        # Convert PointStruct to dict for index_point_dual_write
                        point_dict = {
                            'id': point.id,
                            'vector': point.vector,
                            'payload': point.payload
                        }
                        # Call dual-write function (graceful degradation handled internally)
                        success = index_point_dual_write(
                            point=point_dict,
                            qdrant_client=self.client,
                            ov_client=self.ov_client,
                            conn=conn,
                            collection_name=collection_name,
                            project_root=project_root
                        )
                        if not success:
                            logger.error(f"Failed to index point for {file_path} in collection {collection_name}")

            with sqlite3.connect(STATE_DB_PATH) as conn:
                conn.execute("INSERT OR REPLACE INTO file_states (file_path, hash, last_indexed, collection_name) VALUES (?, ?, ?, ?)",
                           (str(file_path), current_hash, time.time(), collection_name))

        except Exception as e:
            logger.error(f"Error indexing {file_path}: {e}")

    def write_qdrant_index(self, index_data: dict, output_path: str):
        """Atomic TOML write for qdrant_index.toml using tomli_w

        Args:
            index_data: TOML-serializable data (must include VECTOR_SIZE reference)
            output_path: Target file path for qdrant_index.toml
        """
        # Validate output path
        output_path = Path(output_path)
        if not output_path.parent.exists():
            raise FileNotFoundError(f"Parent directory {output_path.parent} does not exist")

        # Add VECTOR_SIZE constant to index data
        index_data["vector_size"] = self.VECTOR_SIZE

        # Atomic write implementation
        tmp_path = output_path.with_suffix(".tmp")
        try:
            # Write to temporary file
            with open(tmp_path, "wb") as f:
                tomli_w.dump(index_data, f)
            # Replace target file atomically
            os.replace(tmp_path, output_path)
        except Exception as e:
            if tmp_path.exists():
                os.remove(tmp_path)
            raise RuntimeError(f"Failed to write qdrant_index.toml: {str(e)}") from e

    def update_gitignore_for_project(self, project_root: Path):
        """Update project .gitignore to include qdrant_index.toml (server-managed via flag)"""
        gitignore_path = project_root / ".gitignore"
        target_entry = "qdrant_index.toml"

        if not self.AUTO_UPDATE_GITIGNORE:
            return

        try:
            # Surgical read (antidegeneration: no full file load for >50 lines)
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # Check for existing entry (case-insensitive)
            entry_exists = any(line.strip().lower() == target_entry.lower() for line in lines)
            if not entry_exists:
                # Surgical append (antidegeneration compliance)
                # Ensure file ends with newline to prevent merged entries
                with open(gitignore_path, 'a', encoding='utf-8') as f:
                    if lines and not lines[-1].endswith('\n'):
                        f.write('\n')
                    f.write(f"{target_entry}\n")
        except FileNotFoundError:
            # Create .gitignore if missing (atomic single-line write)
            with open(gitignore_path, 'w', encoding='utf-8') as f:
                f.write(f"{target_entry}\n")

    def initial_scan(self):
        """Scan all watched paths for changes using a thread pool, skipping ignored dirs early. Post-scan per-project TOML write."""
        from concurrent.futures import ThreadPoolExecutor
        
        all_files = []  # Restored all_files initialization
        project_index_map = {}
        hardcoded_ignore = {
            '.git', '__pycache__', 'node_modules', '.venv', 'venv',
            '.vscode', '.idea', 'dist', 'build'
        }
        
        for project_path in self.watch_paths:
            project_root = Path(project_path)
            project_index_map[str(project_root)] = {"project_path": str(project_root), "scanned_files": []}
            print(f"Scanning: {project_path}")
            try:
                # Efficient walk that skips ignored directories
                for root, dirs, files in os.walk(project_path):
                    # Modify dirs in-place to skip ignored ones
                    dirs[:] = [d for d in dirs if d not in hardcoded_ignore]
                    
                    for file in files:
                        file_path = Path(root) / file
                        project_index_map[str(project_root)]["scanned_files"].append(str(file_path.relative_to(project_root)))
                        all_files.append((file_path, project_path))
            except Exception as e:
                print(f"Error scanning {project_path}: {e}")

        print(f"Starting parallel indexing of {len(all_files)} files...")
        with ThreadPoolExecutor(max_workers=20) as executor:
            # Removed tqdm to prevent terminal flicker in background processes
            executor.map(lambda p: self.index_file(*p), all_files)
        print("Initial scan complete. Writing per-project TOML indexes...")

        # Write per-project qdrant_index.toml after parallel indexing
        for project_root_str, index_data in project_index_map.items():
            self.write_qdrant_index(index_data, str(Path(project_root_str) / "qdrant_index.toml"))
            self.update_gitignore_for_project(Path(project_root_str))  # Integrate .gitignore update with post-scan TOML write

    def start_watching(self):
        """Start real-time monitoring."""
        global shutdown_flag
        observer = Observer()
        handler = SentinelHandler(self)
        
        active_watches = 0
        for path in self.watch_paths:
            try:
                observer.schedule(handler, str(path), recursive=True)
                active_watches += 1
            except Exception as e:
                print(f"Error: Could not watch {path}: {e}")
        
        if active_watches > 0:
            try:
                observer.start()
                print(f"Sentinel is watching {active_watches} projects.")
                while not shutdown_flag:
                    time.sleep(1)
            except Exception as e:
                print(f"Critical error in observer: {e}")
            finally:
                observer.stop()
                observer.join()
        else:
            print("No valid paths to watch. Sentinel exiting.")

class SentinelHandler(FileSystemEventHandler):
    def __init__(self, sentinel: QdrantSentinel):
        self.sentinel = sentinel
        self.last_modified_times = {}  # Debounce tracking: {file_path_str: last_triggered_time}

    def on_modified(self, event):
        if not event.is_directory:
            path = Path(event.src_path)
            path_str = str(path)
            current_time = time.time()
            debounce_seconds = 5

            # 5s debounce check (prevent duplicate TOML writes)
            if path_str in self.last_modified_times and (current_time - self.last_modified_times[path_str] < debounce_seconds):
                return

            # Find which project this belongs to
            for project_root in self.sentinel.watch_paths:
                if project_root in path.parents:
                    self.last_modified_times[path_str] = current_time
                    self.sentinel.index_file(path, project_root)
                    break

import uuid
from openviking_client import OpenVikingClient

def get_db_connection():
    """Returns a connection to the SQLite state database."""
    return sqlite3.connect(STATE_DB_PATH)


def index_point_dual_write(point: Dict[str, Any], qdrant_client, ov_client, conn, collection_name: str, project_root: Optional[Path] = None) -> bool:
    """
    Upserts a point to Qdrant and OpenViking with transactional integrity.
    
    Args:
        point: Qdrant point dict with id, vector, and payload
        qdrant_client: Qdrant client instance
        ov_client: OpenViking client instance
        conn: SQLite connection for mapping storage
        collection_name: Qdrant collection name to write to
        project_root: Project root path for reconstructing absolute file paths
        
    Returns:
        bool: True if Qdrant succeeded (with or without OpenViking), False if Qdrant failed
    """
    qdrant_id = str(point['id'])
    file_path = point['payload'].get('file_path', 'unknown')
    language = point['payload'].get('language', 'unknown')
    
    # Reconstruct absolute path for OpenViking if project_root is provided
    ov_file_path = file_path
    if project_root and not os.path.isabs(file_path):
        ov_file_path = str(project_root / file_path)
    
    # Step 1: Upsert to Qdrant
    try:
        qdrant_client.upsert(
            collection_name=collection_name,
            points=[point]
        )
    except Exception as qdrant_err:
        logger.error(f"Qdrant upsert failed for {file_path} in collection {collection_name}: {qdrant_err}")
        return False
    
    # Step 2: Add to OpenViking
    ov_id = None
    try:
        ov_response = ov_client.add_resource(
            path=ov_file_path,
            wait=False  # Don't wait for async processing to complete
        )
        # add_resource now returns a string ID directly, not a dict
        ov_id = ov_response
    except Exception as ov_err:
        logger.warning(f"OpenViking write failed for {ov_file_path}: {ov_err}. Continuing with Qdrant-only.")
        return True  # Qdrant succeeded, OpenViking failed - this is acceptable
    
    # Step 3: Store mapping in SQLite (only if OpenViking succeeded and returned valid ID)
    if ov_id is not None:
        try:
            conn.execute(
                "INSERT INTO ov_mappings (qdrant_id, ov_resource_id, file_path) VALUES (?, ?, ?)",
                (qdrant_id, ov_id, file_path)
            )
            conn.commit()
        except sqlite3.Error as db_err:
            # SQLite insert failed - rollback both SQLite and Qdrant
            logger.error(f"SQLite mapping failed, rolling back Qdrant point {qdrant_id}: {db_err}")
            conn.rollback()
            try:
                qdrant_client.delete(
                    collection_name=collection_name,
                    points_selector=[qdrant_id]
                )
            except Exception as delete_err:
                logger.error(f"Failed to rollback Qdrant point {qdrant_id}: {delete_err}")
            raise  # Re-raise to signal failure
    else:
        logger.warning(f"OpenViking returned None for {file_path}. Skipping SQLite mapping. Qdrant-only mode.")
    
    return True
def get_ov_mapping(qdrant_id: str, conn) -> Optional[str]:
    """
    Retrieve OpenViking resource ID by Qdrant point ID.
    
    Args:
        qdrant_id: Qdrant point ID
        conn: SQLite connection
        
    Returns:
        OpenViking resource ID or None if not found
    """
    cursor = conn.cursor()
    cursor.execute(
        "SELECT ov_resource_id FROM ov_mappings WHERE qdrant_id = ?",
        (qdrant_id,)
    )
    result = cursor.fetchone()
    return result[0] if result and len(result) > 0 else None


def get_qdrant_mapping(ov_resource_id: str, conn) -> Optional[str]:
    """
    Retrieve Qdrant point ID by OpenViking resource ID.
    
    Args:
        ov_resource_id: OpenViking resource ID
        conn: SQLite connection
        
    Returns:
        Qdrant point ID or None if not found
    """
    cursor = conn.cursor()
    cursor.execute(
        "SELECT qdrant_id FROM ov_mappings WHERE ov_resource_id = ?",
        (ov_resource_id,)
    )
    result = cursor.fetchone()
    return result[0] if result and len(result) > 0 else None


def get_qdrant_client():
    """Get Qdrant client instance (helper for testing)."""
    return QdrantClient(url=os.getenv("QDRANT_URL", "http://127.0.0.1:6333"), check_compatibility=False)


def get_db_connection():
    """Get SQLite database connection (helper for testing)."""
    return sqlite3.connect(STATE_DB_PATH)


def get_status_report(qdrant_client, sqlite_conn):
    """
    Generate a status report comparing Qdrant points and OpenViking mappings.
    
    Args:
        qdrant_client: QdrantClient instance
        sqlite_conn: SQLite connection object
        
    Returns:
        dict: Status report with keys:
            - total_qdrant_points: Total points in Qdrant collection
            - total_ov_resources: Total resources in ov_mappings table
            - mapped_count: Resources with valid qdrant_id mappings
            - unmapped_qdrant_count: Qdrant points without mapping
    """

    # Get all collections starting with qdr- prefix
    collections = qdrant_client.get_collections()
    total_qdrant_points = 0
    
    for collection in collections.collections:
        if collection.name.startswith("qdr-"):
            count = qdrant_client.count(collection.name, exact=True)
            total_qdrant_points += count.count
    
    # Query SQLite for OpenViking mapping stats (single optimized query)
    cursor = sqlite_conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) as total, COUNT(qdrant_id) as mapped FROM ov_mappings"
    )
    total_ov_resources, mapped_count = cursor.fetchone()
    cursor.close()
    
    # Calculate unmapped Qdrant points (prevent negative counts)
    unmapped_qdrant_count = max(0, total_qdrant_points - mapped_count)
    
    return {
        "total_qdrant_points": total_qdrant_points,
        "total_ov_resources": total_ov_resources,
        "mapped_count": mapped_count,
        "unmapped_qdrant_count": unmapped_qdrant_count
    }


def confirm_rebuild(stats: dict) -> bool:
    """
    Show rebuild confirmation prompt and get user confirmation.
    
    Args:
        stats: Dictionary with statistics about data to be deleted
            - qdrant_collections: Number of Qdrant collections
            - sqlite_file_hashes: Number of file_hashes rows
            - sqlite_ov_mappings: Number of ov_mappings rows
            - openviking_resources: Number of OpenViking resources
    
    Returns:
        True if user confirms, False otherwise
    """
    print("\n⚠️  WARNING: This will delete ALL indexed data!")
    print(f"    - Qdrant collections: {stats.get('qdrant_collections', 0)}")
    print(f"    - SQLite file_states: {stats.get('sqlite_file_states', 0)}")
    print(f"    - SQLite ov_mappings: {stats.get('sqlite_ov_mappings', 0)}")
    print(f"    - OpenViking resources: {stats.get('openviking_resources', 0)}")
    print()
    
    response = input("Proceed? [y/N]: ").strip().lower()
    return response == 'y'


def create_backup() -> bool:
    """
    Create backup of SQLite database and Qdrant collections.
    
    Returns:
        True if backup succeeded, asFalse otherwise
    """
    import shutil
    from datetime import datetime
    
    try:
        # Backup SQLite database
        state_db_path = Path(STATE_DB_PATH)
        if state_db_path.exists():
            backup_path = state_db_path.with_suffix(state_db_path.suffix + '.backup')
            shutil.copy2(state_db_path, backup_path)
            logger.info(f"✅ Backup created: {backup_path}")
        else:
            logger.warning(f"State DB not found: {state_db_path}")
        
        # TODO: Backup Qdrant collections (export snapshots)
        # This requires Qdrant client access and snapshot export functionality
        
        return True
    except Exception as e:
        logger.error(f"Backup failed: {e}")
        return False


def restore_backup() -> bool:
    """
    Restore from backup if rebuild fails.
    
    Returns:
        True if restore succeeded, False otherwise
    """
    import shutil
    
    try:
        # Restore SQLite database
        state_db_path = Path(STATE_DB_PATH)
        backup_path = state_db_path.with_suffix(state_db_path.suffix + '.backup')
        
        if backup_path.exists():
            shutil.copy2(backup_path, state_db_path)
            logger.info(f"✅ Backup restored: {state_db_path}")
        else:
            logger.error(f"Backup not found: {backup_path}")
            return False
        
        # TODO: Restore Qdrant collections from backup
        
        return True
    except Exception as e:
        logger.error(f"Restore failed: {e}")
        return False


def rebuild_index(
    project_name: Optional[str] = None,
    backup: bool = False,
    qdrant_only: bool = False,
    dry_run: bool = False,
    skip_confirmation: bool = False
) -> bool:
    """
    Perform full rebuild of indexed data.
    
    Args:
        project_name: Rebuild only specific project (None = all projects)
        backup: Create backup before rebuild
        qdrant_only: Rebuild only Qdrant (keep SQLite mappings)
        dry_run: Show what will be deleted without deleting
        skip_confirmation: Skip confirmation prompt (for automation)
    
    Returns:
        True if rebuild succeeded, False otherwise
    """
    from qdrant_client import QdrantClient
    from openviking_client import OpenVikingClient
    
    try:
        # Initialize clients (using helper functions for testability)
        qdrant_client = get_qdrant_client()
        # Use data_path from config if available, otherwise let OpenVikingClient use its default
        ov_data_path = _config.openviking.data_path if _config and hasattr(_config, 'openviking') and hasattr(_config.openviking, 'data_path') else None
        ov_client = OpenVikingClient(data_path=ov_data_path)
        
        # Step 1: Gather statistics
        collections = qdrant_client.get_collections().collections
        # Only target qdr-* collections for deletion to prevent accidental removal of other collections
        collections = [c for c in collections if c.name.startswith("qdr-")]
        if project_name:
            collections = [c for c in collections if c.name == project_name]
        
        stats = {
            'qdrant_collections': len(collections),
            'sqlite_file_states': 0,
            'sqlite_ov_mappings': 0,
            'openviking_resources': 0
        }
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Count file_states
            cursor.execute("SELECT COUNT(*) FROM file_states")
            stats['sqlite_file_states'] = cursor.fetchone()[0]
            
            # Count ov_mappings
            cursor.execute("SELECT COUNT(*) FROM ov_mappings")
            stats['sqlite_ov_mappings'] = cursor.fetchone()[0]
        
        # Count OpenViking resources (estimated)
        try:
            ov_resources = ov_client.find_resources("")
            stats['openviking_resources'] = len(ov_resources)
        except:
            stats['openviking_resources'] = stats['sqlite_ov_mappings']  # Fallback estimate
        
        # Show dry-run info and return early
        if dry_run:
            print("\n📋 DRY RUN - No changes will be made")
            print(f"    - Qdrant collections to delete: {[c.name for c in collections]}")
            print(f"    - SQLite file_states rows: {stats['sqlite_file_states']}")
            print(f"    - SQLite ov_mappings rows: {stats['sqlite_ov_mappings']}")
            print(f"    - OpenViking resources: {stats['openviking_resources']} (estimated)")
            print()
            return True  # Dry-run successful
        
        # Step 2: Confirmation
        if not skip_confirmation and not confirm_rebuild(stats):
            print("❌ Rebuild cancelled by user")
            return False
        
        # Step 3: Backup (if requested)
        if backup:
            if not create_backup():
                print("❌ Backup failed, aborting rebuild")
                return False
            print("✅ Backup created successfully")
        
        # Step 4: Delete old data
        # Delete Qdrant collections
        for collection in collections:
            logger.info(f"Deleting Qdrant collection: {collection.name}")
            qdrant_client.delete_collection(collection.name)
        
        # Clear SQLite tables (unless qdrant_only)
        if not qdrant_only:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                if project_name:
                    cursor.execute("DELETE FROM file_states WHERE collection_name LIKE ?", (f"%{project_name}%",))
                    cursor.execute("DELETE FROM ov_mappings WHERE file_path LIKE ?", (f"%{project_name}%",))
                else:
                    cursor.execute("DELETE FROM file_states")
                    cursor.execute("DELETE FROM ov_mappings")
                
                conn.commit()
                logger.info("✅ Cleared SQLite tables")
        
        logger.info(f"✅ Deleted Qdrant collections: {len(collections)}")
        
        # Step 5: Rescan and Reindex
        config_path = Path(__file__).parent / "projects.json"
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = json.load(f)
            watch_paths = config.get("watch_paths", [])
            
            if project_name:
                # Filter watch_paths by matching collection name
                # Collection name is derived from path: "project-{path.name.lower()}"
                watch_paths = [
                    wp for wp in watch_paths
                    if f"project-{Path(wp).name.lower()}" == project_name
                ]
            
            sentinel = QdrantSentinel(watch_paths)
            sentinel.initial_scan()
            
            logger.info(f"✅ Reindexing {len(watch_paths)} project(s)")
        
        print("✅ Rebuild complete!")
        return True
        
    except Exception as e:
        logger.error(f"Rebuild failed: {e}")
        
        # Rollback if backup exists
        if backup:
            print("Attempting rollback from backup...")
            if restore_backup():
                print("✅ Rollback successful")
            else:
                print("❌ Rollback failed")
        
        return False


async def signal_handler(sig_num=None):
    """Signal handler for SIGTERM/SIGINT - graceful shutdown for PM2 compatibility."""
    global shutdown_flag
    
    # Early return if already shutting down to prevent race condition
    if shutdown_flag:
        return
    
    shutdown_flag = True
    signal_name = signal.Signals(sig_num).name if sig_num else "UNKNOWN"
    logger.info(f"Shutdown signal ({signal_name}) received - initiating graceful shutdown")


async def async_main():
    """Async main function for Qdrant Sentinel."""
    import argparse
    global shutdown_flag
    
    # Get event loop and register signal handlers
    loop = asyncio.get_event_loop()
    
    # Register signal handlers for PM2 compatibility
    try:
        loop.add_signal_handler(signal.SIGTERM, lambda: asyncio.create_task(signal_handler(signal.SIGTERM)))
        loop.add_signal_handler(signal.SIGINT, lambda: asyncio.create_task(signal_handler(signal.SIGINT)))
    except NotImplementedError:
        # Windows doesn't support add_signal_handler
        logger.warning("Signal handlers not supported on this platform")
    
    parser = argparse.ArgumentParser(description="Qdrant Sentinel - Code Indexer")
    parser.add_argument("--rebuild", action="store_true", help="Full rebuild of index")
    parser.add_argument("--project", type=str, help="Rebuild specific project only")
    parser.add_argument("--backup", action="store_true", help="Create backup before rebuild")
    parser.add_argument("--qdrant-only", action="store_true", help="Rebuild only Qdrant (keep SQLite)")
    parser.add_argument("--dry-run", action="store_true", help="Show what will be deleted")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    
    args = parser.parse_args()
    
    # Handle rebuild command
    if args.rebuild:
        success = rebuild_index(
            project_name=args.project,
            backup=args.backup,
            qdrant_only=args.qdrant_only,
            dry_run=args.dry_run,
            skip_confirmation=args.yes
        )
        sys.exit(0 if success else 1)
    
    try:
        # Normal operation
        # Load configuration from projects.json
        config_path = Path(__file__).parent / "projects.json"
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = json.load(f)
            watch_paths = config.get("watch_paths", [])
        else:
            print("Error: projects.json not found.")
            print("Please create projects.json based on projects.json.example")
            return
        
        if not watch_paths:
            print("Error: No watch_paths defined in projects.json")
            return

        sentinel = QdrantSentinel(watch_paths)
        sentinel.initial_scan()
        sentinel.start_watching()
        
    finally:
        # Remove signal handlers on exit
        try:
            try:
                loop.remove_signal_handler(signal.SIGTERM)
                loop.remove_signal_handler(signal.SIGINT)
            except (NotImplementedError, ValueError):
                pass  # Handlers may not be registered or platform doesn't support it
        except Exception as e:
            logger.warning(f"Error removing signal handlers: {e}")


def main():
    """Synchronous entry point that runs async_main."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
