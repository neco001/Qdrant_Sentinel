import os
# Fix OpenSSL uplink crash caused by AVG/Avast SSLKEYLOGFILE injection on Windows
os.environ.pop('SSLKEYLOGFILE', None)

import time
import hashlib
import sqlite3
import json
from pathlib import Path
from typing import List, Set, Dict, Any
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from qdrant_client import QdrantClient
from qdrant_client.http import models
from openai import OpenAI
from dotenv import load_dotenv
from tqdm import tqdm
import pathspec
import uuid
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
    def __init__(self, watch_paths: List[str]):
        self.watch_paths = [Path(p).resolve() for p in watch_paths]
        self.client = QdrantClient(url=QDRANT_URL)
        self.ai_client = OpenAI(api_key=EMBEDDING_API_KEY, base_url=EMBEDDING_BASE_URL)
        self.init_db()

    def init_db(self):
        """Initialize SQLite DB to store file hashes."""
        with sqlite3.connect(STATE_DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS file_states (
                    file_path TEXT PRIMARY KEY,
                    hash TEXT,
                    last_indexed REAL,
                    collection_name TEXT
                )
            """)

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
                        vectors_config=models.VectorParams(size=1024, distance=models.Distance.COSINE),
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

    def initial_scan(self):
        """Scan all watched paths for changes using a thread pool, skipping ignored dirs early."""
        from concurrent.futures import ThreadPoolExecutor
        
        all_files = []
        hardcoded_ignore = {
            '.git', '__pycache__', 'node_modules', '.venv', 'venv', 
            '.vscode', '.idea', 'dist', 'build'
        }
        
        for project_path in self.watch_paths:
            print(f"Scanning: {project_path}")
            try:
                # Efficient walk that skips ignored directories
                for root, dirs, files in os.walk(project_path):
                    # Modify dirs in-place to skip ignored ones
                    dirs[:] = [d for d in dirs if d not in hardcoded_ignore]
                    
                    for file in files:
                        file_path = Path(root) / file
                        all_files.append((file_path, project_path))
            except Exception as e:
                print(f"Error scanning {project_path}: {e}")

        print(f"Starting parallel indexing of {len(all_files)} files...")
        with ThreadPoolExecutor(max_workers=20) as executor:
            # Removed tqdm to prevent terminal flicker in background processes
            executor.map(lambda p: self.index_file(*p), all_files)
        print("Initial scan complete.")

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

    def on_modified(self, event):
        if not event.is_directory:
            path = Path(event.src_path)
            # Find which project this belongs to
            for project_root in self.sentinel.watch_paths:
                if project_root in path.parents:
                    self.sentinel.index_file(path, project_root)
                    break

import uuid
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
