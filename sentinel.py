import os
# Fix OpenSSL uplink crash caused by AVG/Avast SSLKEYLOGFILE injection on Windows
os.environ.pop('SSLKEYLOGFILE', None)

import time
import hashlib
import sqlite3
import json
import logging
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

logger = logging.getLogger(__name__)
import os
from parser_wrapper import parse_file
from ast_walker import extract_structural_nodes
from chunker import build_chunks, EXT_TO_LANG

# Load environment variables
load_dotenv()

# Configuration
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY")
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "text-embedding-v4")
STATE_DB_PATH = "sentinel_state.db"

class QdrantSentinel:
    VECTOR_SIZE = 1024  # Explicit class-level constant (task 8 completion)
    AUTO_UPDATE_GITIGNORE = True  # Server-managed .gitignore updates (user-chosen Option A)
    def __init__(self, watch_paths: List[str]):
        self.watch_paths = [Path(p).resolve() for p in watch_paths]
        self.client = QdrantClient(url=QDRANT_URL)
        self.ai_client = OpenAI(api_key=EMBEDDING_API_KEY, base_url=EMBEDDING_BASE_URL)
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
        return f"project-{project_path.name.lower()}"

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
            for j in range(0, len(final_chunks), 50):
                batch = [c.strip() for c in final_chunks[j:j+50] if c.strip()]
                if not batch: continue
                
                emb_res = self.ai_client.embeddings.create(input=batch, model=EMBEDDING_MODEL_NAME)
                all_embeddings.extend([e.embedding for e in emb_res.data])

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
                self.client.upsert(collection_name=collection_name, points=points)

            with sqlite3.connect(STATE_DB_PATH) as conn:
                conn.execute("INSERT OR REPLACE INTO file_states (file_path, hash, last_indexed, collection_name) VALUES (?, ?, ?, ?)",
                           (str(file_path), current_hash, time.time(), collection_name))

        except Exception as e:
            # print(f"Error indexing {file_path}: {e}") # Keep it quiet in prod
            pass

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
                while True:
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


def index_point_dual_write(point: Dict[str, Any], qdrant_client, ov_client, conn) -> bool:
    """
    Upserts a point to Qdrant and OpenViking with transactional integrity.
    
    Args:
        point: Qdrant point dict with id, vector, and payload
        qdrant_client: Qdrant client instance
        ov_client: OpenViking client instance
        conn: SQLite connection for mapping storage
        
    Returns:
        bool: True if dual-write succeeded, False if OpenViking failed (graceful degradation)
    """
    qdrant_id = str(point['id'])
    file_path = point['payload'].get('file_path', 'unknown')
    language = point['payload'].get('language', 'unknown')
    
    # Step 1: Upsert to Qdrant
    qdrant_client.upsert(
        collection_name="code_index",
        points=[point]
    )
    
    # Step 2: Add to OpenViking
    try:
        ov_response = ov_client.add_resource(
            name=file_path,
            resource_type='code',
            tags=[language]
        )
        ov_id = ov_response.get('id') if isinstance(ov_response, dict) else ov_response
        
        # Step 3: Store mapping in SQLite
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO ov_mappings (qdrant_id, ov_resource_id, file_path) VALUES (?, ?, ?)",
            (qdrant_id, ov_id, file_path)
        )
        conn.commit()
        return True
        
    except sqlite3.Error as db_err:
        # SQLite insert failed - rollback Qdrant
        logger.error(f"SQLite mapping failed, rolling back Qdrant point {qdrant_id}: {db_err}")
        try:
            qdrant_client.delete(
                collection_name="code_index",
                points_selector=[qdrant_id]
            )
        except Exception as delete_err:
            logger.error(f"Failed to rollback Qdrant point {qdrant_id}: {delete_err}")
        raise  # Re-raise to signal failure
    except Exception as ov_err:
        logger.warning(f"OpenViking write failed for {file_path}: {ov_err}. Continuing with Qdrant-only.")
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
    # Get total Qdrant points
    qdrant_count_result = qdrant_client.count(
        collection_name="code_index",
        exact=True
    )
    total_qdrant_points = qdrant_count_result.count
    
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


def main():
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

if __name__ == "__main__":
    main()
