# Qdrant Sentinel

## Do I need this? What for?

If you are working with **AI agents** (like Claude, ChatGPT, or Antigravity) and you want them to have a **deep, always up-to-date understanding of your codebase**, you need this.

Manually feeding files to an LLM is tedious and slow. **Qdrant Sentinel** automates this by:
1.  **Watching** your project folders in real-time.
2.  **Indexing** every line of code into a [Qdrant](https://qdrant.tech/) vector database.
3.  **Syncing** only what changed, so your "AI brain" always has the latest context.

### Data Flow
```mermaid
graph LR
    A[Local Code] -->|Real-time Watch| B(Qdrant Sentinel)
    B -->|Dual-Write| C[(Qdrant DB)]
    B -->|Dual-Write| D[(OpenViking)]
    C <-->|Query/Retrieval| E[Universal MCP Server]
    D <-->|Context Retrieval| E
    E <-->|Context| F[AI Agent / Claude]
```

---

## Quick Start

1. **Clone & Install**: `git clone ... && uv sync`
2. **Configure**: Copy `.env.example` to `.env` & `projects.json.example` to `projects.json`.
3. **Run**: `pm2 start ecosystem.config.js` (or `uv run qdrant-sentinel`)

---

## Better Together (Production-Grade RAG)

While **Qdrant Sentinel** handles _indexing_ (getting data in), it works best when paired with **[Qdrant Universal MCP Server](https://github.com/neco001/qdrant2.git)** and **[OpenViking](https://github.com/volcengine/OpenViking)**.

### Why this architecture?
Unlike monolithic MCP servers that try to index code on-the-fly (and stall your LLM interface), this **split architecture** ensures:
- **Index is always ready**: Sentinel runs as a background daemon.
- **Low Overhead**: The AI only queries what it needs via MCP tool.
- **Stability**: Large scans doesn't crash your Claude Desktop session.
- **Dual-Write Pipeline**: Synchronized indexing to both Qdrant (vector search) and OpenViking (context database) for comprehensive code understanding.

| Feature | Standard MCP Indexers | Qdrant Sentinel + Universal MCP + OpenViking |
| :--- | :---: | :---: |
| **Indexing Mode** | On-demand (stalls UI) | **Background Daemon** (Always-on) |
| **Multi-project** | Often single-folder | **Unlimited projects** via config |
| **Vector Integrity** | Basic (may pad vectors) | **Strict dimension enforcement** |
| **Model Support** | Often OpenAI only | **Universal Proxy** (DashScope, Ollama, etc.) |
| **Context Management** | Flat vector storage | **Hierarchical filesystem + L0/L1/L2 layers** |
| **Memory** | Conversation history only | **User + Agent experience memory** |

---

## Prerequisites: Set Up Qdrant

Before running the Sentinel, you need a running Qdrant instance.

### Option A: Local Setup (Docker) - Recommended
```bash
docker run -d --name qdrant -p 6333:6333 -v qdrant_data:/qdrant/storage qdrant/qdrant
```

### Option B: Qdrant Cloud
Sign up at [Qdrant Cloud](https://cloud.qdrant.io/) and get your Cluster URL and API Key.

---

## Features

- **Structural Code Analysis**: Uses **Tree-sitter** for high-precision AST-based parsing of Python, JavaScript, TypeScript, Go, Rust, C/C++, Java, and more.
- **Augmented Semantic Indexing**: Instead of naive line-based splitting, it extracts entire classes, functions, and methods as logical units.
- **Hierarchical Metadata**: Automatically tags chunks with parent symbols, symbol types, and line ranges for advanced RAG retrieval.
- **Real-time Monitoring**: Uses `watchdog` to detect file changes and instantly update the index.
- **Deterministic Sync**: Uses stable UUIDs and automated cleanup to ensure the index stays perfectly in sync with the current state of your code.
- **Multi-project Support**: Index multiple independent repositories into separate Qdrant collections.
- **Intelligent Filtering**: Respects `.gitignore`, `.git/info/exclude`, and `.rooignore`.
- **State Persistence**: Tracks file hashes in a local SQLite database to avoid redundant indexing.
- **Per-Project Configuration**: Generates `qdrant_index.toml` files for each project with custom indexing settings.
- **Automatic .gitignore Management**: Optionally auto-updates `.gitignore` to exclude `qdrant_index.toml` files.
- **Debounced Updates**: Implements 5-second debounce to prevent rapid-fire reindexing during file storms.
- **Atomic Configuration Writes**: Ensures TOML configuration files are written atomically to prevent corruption.
- **Dual-Write Pipeline**: Atomically indexes code to both Qdrant and OpenViking with SQLite cross-reference mapping and automatic rollback on failure.
- **Graceful Degradation**: Continues operation if OpenViking is unavailable, with full recovery on reconnect.

## Configuration

### Environment Variables (.env)
- `QDRANT_URL`: Qdrant instance URL (default: `http://localhost:6333`)
- `QDRANT_API_KEY`: Qdrant API key (for cloud instances)
- `EMBEDDING_MODEL`: Embedding model to use (default: `text-embedding-3-small`)
- `EMBEDDING_API_KEY`: API key for embedding service
- `AUTO_UPDATE_GITIGNORE`: Automatically update `.gitignore` files (default: `true`)

### Projects Configuration (projects.json)
```json
{
  "projects": [
    {
      "name": "my-project",
      "path": "/path/to/project",
      "collection_name": "my_project_index",
      "enabled": true
    }
  ]
}
```

### Per-Project Configuration (qdrant_index.toml)
Each project gets a `qdrant_index.toml` file with project-specific settings:

```toml
[qdrant]
collection_name = "my_project_index"
vector_size = 1536
created_at = "2024-06-09T09:30:00Z"
last_updated = "2024-06-09T09:35:00Z"

[settings]
auto_update_gitignore = true
exclude_patterns = ["*.tmp", "*.log"]
include_patterns = ["*.py", "*.js", "*.ts"]
```

## Installation

This project uses [uv](https://github.com/astral-sh/uv) for dependency management.

1. **Clone & Setup:**
   ```bash
   git clone https://github.com/neco001/Qdrant_Sentinel.git
   cd Qdrant_Sentinel
   uv sync
   ```

2. **Configuration:**
   - Copy `.env.example` to `.env` and fill in your API keys.
   - Copy `projects.json.example` to `projects.json` and add your project paths.

## Usage

### Manual Execution

```bash
uv run qdrant-sentinel
```

### Background Service (PM2)
```bash
pm2 start ecosystem.config.js
```

### Monitoring and Debugging

The Sentinel provides detailed logging:
- **INFO**: Normal operations (file changes, indexing progress)
- **WARNING**: Configuration issues, skipped files
- **ERROR**: Critical failures (API errors, file access issues)

### Advanced Features

#### Automatic .gitignore Management
When `AUTO_UPDATE_GITIGNORE=true`, Sentinel automatically adds `qdrant_index.toml` to each project's `.gitignore` file. This prevents version control conflicts and keeps your repository clean.

#### Debounced Updates
The Sentinel implements a 5-second debounce mechanism to handle file storms (e.g., during git operations or bulk file saves). This prevents excessive reindexing and improves performance.

#### Atomic Configuration Writes
All TOML configuration files are written atomically using temporary files and atomic moves, preventing corruption even if the process is interrupted.

#### Dual-Write Pipeline
The Sentinel atomically writes to both Qdrant and OpenViking for each indexed point. If OpenViking fails, the operation degrades gracefully (Qdrant write succeeds). If the SQLite mapping fails, both writes are rolled back to maintain consistency.

## License

MIT License. See `LICENSE` for details.

## Third-Party Licenses & Attributions

This project integrates with the following third-party software:

### OpenViking
- **License**: AGPLv3
- **Source**: [https://github.com/volcengine/OpenViking](https://github.com/volcengine/OpenViking)
- **Usage**: Context database for AI agents with hierarchical filesystem paradigm
- **Attribution**: This project uses OpenViking for augmented context management and memory storage. OpenViking is licensed under AGPLv3, and its source code is available at the above repository.

### Qdrant
- **License**: Apache 2.0
- **Source**: [https://github.com/qdrant/qdrant](https://github.com/qdrant/qdrant)
- **Usage**: Vector database for semantic search and retrieval

---

_Have a great day_
