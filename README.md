# Qdrant Sentinel

## Do I need this? What for?

If you are working with **AI agents** (like Claude, ChatGPT, or Antigravity) and you want them to have a **deep, always up-to-date understanding of your codebase**, you need this.

Manually feeding files to an LLM is tedious and slow. **Qdrant Sentinel** automates this by:

1.  **Watching** your project folders in real-time.
2.  **Indexing** every line of code into a [Qdrant](https://qdrant.tech/) vector database.
3.  **Syncing** only what changed, so your "AI brain" always has the latest context without re-processing everything.

It's the "bridge" between your local files and your AI tools' semantic memory.

---

## Better Together

While **Qdrant Sentinel** handles the _indexing_ (getting data in), it works best when paired with the **[Qdrant Universal MCP Server](https://github.com/neco001/qdrant2.git)**.

The MCP server allows your AI agents to actually _query_ and _use_ the data indexed by the Sentinel. Together, they form a complete, autonomous memory system for your development workflow.

---

## Prerequisites: Set Up Qdrant

Before running the Sentinel, you need a running Qdrant instance.

### Option A: Local Setup (Docker) - Recommended

The easiest way to run Qdrant locally is via Docker:

```bash
docker run -d \
  --name qdrant \
  --restart unless-stopped \
  -p 6333:6333 \
  -v qdrant_data:/qdrant/storage \
  qdrant/qdrant
```

### Option B: Qdrant Cloud - Free Tier Available

1. Sign up at [Qdrant Cloud](https://cloud.qdrant.io/).
2. Create a free cluster.
3. Copy your **Cluster URL** and **API Key**.

---

## Features

- **Real-time Monitoring**: Uses `watchdog` to detect file changes and instantly update the index.
- **Multi-project Support**: Index multiple independent repositories into separate Qdrant collections.
- **Intelligent Filtering**: Respects `.gitignore`, `.git/info/exclude`, and `.rooignore`. Automatically skips binary files and large assets.
- **Batch Processing**: Efficiently handles initial scans with multi-threaded indexing and batch embedding requests.
- **State Persistence**: Tracks file hashes in a local SQLite database to avoid redundant indexing.
- **Flexible Embeddings**: Compatible with OpenAI-style embedding APIs (e.g., OpenAI, DashScope/Alibaba).

## 🚀 Installation

This project uses [uv](https://github.com/astral-sh/uv) for lightning-fast dependency management.

1. **Clone the repository:**

   ```bash
   git clone https://github.com/neco001/qdrant-sentinel.git
   cd qdrant-sentinel
   ```

2. **Install dependencies:**
   ```bash
   uv sync
   ```

## ⚙️ Configuration

### 1. Environment Variables

Create a `.env` file from the example:

```bash
cp .env.example .env
```

Edit `.env` and provide your credentials:

- `QDRANT_URL`: Your Qdrant instance URL (default: `http://localhost:6333`).
- `EMBEDDING_API_KEY`: Your API key for embeddings (OpenAI or DashScope).
- `EMBEDDING_BASE_URL`: Base URL for the embedding API.
- `EMBEDDING_MODEL_NAME`: The model to use (e.g. `text-embedding-v4` from Alibaba DashScope).

### 2. Projects to Index

Create a `projects.json` file to define which directories should be watched:

```bash
cp projects.json.example projects.json
```

Example configuration:

```json
{
  "watch_paths": ["C:/Repos/my-awesome-app", "C:/Repos/another-project"]
}
```

## 🏃 Usage

### Manual Execution

Run the sentinel directly:

```bash
uv run qdrant-sentinel
```

### Background Service (PM2)

If you have [PM2](https://pm2.keymetrics.io/) installed, you can run the sentinel as a persistent background process:

```bash
pm2 start ecosystem.config.js
```

## 📄 License

MIT License. See `LICENSE` for details.

---

_Miłego dnia 😀_
