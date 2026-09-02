# RAG-Based Local Coding Agent

A fully local, retrieval-augmented generation (RAG) coding assistant for **Java**, **Python**, and **Go** codebases. It parses your repositories with `tree-sitter`, embeds every function/method into a [Qdrant](https://qdrant.tech/) vector database, and answers questions about your code with a local LLM served by [Ollama](https://ollama.com/) — no data ever leaves your machine.

The agent understands your question, **generates its own optimized query**, decides **how many documents it needs**, retrieves the relevant code from the vector database, and can **write the generated answer (code or Markdown) to files** on disk.

---

## Features

- **AST-level code indexing** — `tree-sitter` parsers split Java/Python/Go files into one chunk per function/method, enriched with metadata (project, language, package/module, class, name, line range, file path) and the preceding docstring/comment.
- **Self-directed retrieval** — the agent rewrites the user's question for better vector matching (`update_query`), chooses the `limit` for each search itself (starts at `3` and increases if context is insufficient), and filters results by a **similarity score threshold of 0.4**.
- **File generation** — answers are saved as files with proper extensions (`.py`, `.java`, `.go`, `.md`, ...) inside a per-session folder via the `create_file` tool.
- **Context compaction** — manual `/compact` command plus automatic compaction when the prompt token count crosses a threshold; the conversation is summarized into `CONTEXT*.md` files and long-term memory is restored from them.
- **Two frontends** — an interactive CLI and a Streamlit web UI with session management, file panel, and live tool-call visualization.
- **Session persistence** — sessions are identified by a UUID; chat history (`history.json`) and generated artifacts survive restarts and can be resumed.
- **Token accounting** — a LangChain callback handler tracks prompt/eval token counts from Ollama and drives automatic compaction.

---

## Architecture

### Indexing pipeline (run once per codebase)

```
/tmp/Repos/<repo>/...          (Java, Python, Go sources)
        │
        ▼
tree-sitter parsers (.java / .py / .go)
        │   one chunk per function / method +
        │   metadata (project, language, package,
        │   class, name, line range, file path)
        │   + preceding comment / docstring
        ▼
Ollama embedding API           (qwen3-embedding:0.6b, 1024-dim)
        │
        ▼
Qdrant collection "codebase"   (cosine similarity)
```

The **embedding text** of each chunk is `comment + code`, so docstrings and Javadoc/Godoc comments boost retrieval quality. The full payload stored in Qdrant contains the raw code, the comment, and all metadata.

### Query flow (agent at work)

```
User question
     │
     ▼
LangGraph agent  (LangChain create_agent + ChatOllama via Ollama)
     │   1. update_query    → rewrites the question into an effective
     │                        vector-search query
     │   2. search_codebase → embeds the query, searches the Qdrant
     │                        "codebase" collection, returns payloads
     │                        with score > 0.4 (limit chosen by the model)
     │   3. (repeat with a broader/adjusted query if results are poor)
     ▼
Answer grounded strictly in the retrieved code
     │
     ▼
create_file → saved under  SESSION_PATH/<session_id>/
```

The system prompt restricts the assistant to software-engineering topics and to the provided context; the agent answers in **Turkish** (see `prompts/prompts2.py` if you want to change this).

---

## Project Structure

```
├── interface/
│   └── app.py                  # Streamlit web UI (chat, sessions, file panel, compaction)
├── local_llm/
│   └── agent.py                # CLI agent (LangGraph agent, tools, compaction loop)
├── prompts/
│   ├── prompts.py              # Legacy system prompt (kept for reference)
│   └── prompts2.py             # Active system prompt used by both frontends
├── qdrant_pipeline/
│   └── qdrant_main.py          # Indexing pipeline: chunk → embed → upsert into Qdrant
├── splitters/
│   └── text_splitters.py       # tree-sitter parsing & chunk extraction (Java/Python/Go)
├── token_tracker/
│   └── base_callback_handler.py# LangChain callback for Ollama token usage stats
├── compaction.md               # Template/instructions for context compaction summaries
└── .env.example                # Example environment configuration
```

---

## Prerequisites

| Requirement | Notes |
|---|---|
| **Python 3.10+** | Tested with 3.12+ |
| **Qdrant server** | Expects `http://localhost:6333` — e.g. `docker run -p 6333:6333 qdrant/qdrant` |
| **Ollama server** | Expects `http://127.0.0.1:11434` (configurable) |
| **Ollama models** | `glm-5.2:cloud` (chat agent), `qwen3-embedding:0.6b` (embeddings), `ornith:35b` (optional — session titles in the web UI) |

```bash
ollama pull glm-5.2:cloud
ollama pull qwen3-embedding:0.6b
ollama pull ornith:35b        # optional, used by the web UI for chat titles
```

---

## Installation

```bash
git clone <repo-url>
cd rag_based_local_coding_agent

python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env           # then edit the values
```

---

## Indexing Your Repositories

1. Place the repositories you want to make searchable under **`/tmp/Repos`** (hardcoded in `splitters/text_splitters.py:8` and `qdrant_pipeline/qdrant_main.py:16` — adjust if needed):

   ```
   /tmp/Repos/
   ├── MyJavaApp/          →  indexed (Java)
   ├── my_python_service/  →  indexed (Python)
   └── my-go-tool/         →  indexed (Go)
   ```

   Only `.java`, `.py`, and `.go` files are parsed; everything else is skipped.

2. Make sure Qdrant and Ollama are running, then rebuild the index:

   ```bash
   python -m qdrant_pipeline.qdrant_main
   ```

   This **deletes and recreates** the `codebase` collection, embeds every function/method found, and upserts it into Qdrant.

---

## Usage

### CLI Agent

```bash
python -m local_llm.agent
```

- Each run creates a new session (UUID). Generated files land in `SESSION_PATH/<session_id>/`.
- Resume a previous session (restores its `CONTEXT*.md` summaries):

  ```bash
  python -m local_llm.agent -id <session_id>
  ```

- Type `/compact` at any time to force context compaction.
- The CLI **automatically compacts** when the accumulated prompt token count reaches **60,000**.
- `Ctrl+C` exits.

### Streamlit Web UI

```bash
streamlit run interface/app.py
```

- **Sidebar** — start a new chat, switch between saved sessions (auto-titled by the `ornith:35b` model), delete sessions.
- **Chat area** — shows the agent's tool calls (`search_codebase`, `create_file`, ...) and responses live; type `/compact` to trigger compaction manually.
- **File panel** — browse, preview, inspect full-screen, and download every file the agent created in the current session.
- Sessions persist to `history.json` on disk; the UI **automatically compacts** when the prompt token count reaches **750,000**.
- The UI uses a larger context window (`num_ctx=1000000`) than the CLI (`num_ctx=262144`).

---

## Configuration

All configuration is read from a `.env` file (see `.env.example`):

| Variable | Description | Example |
|---|---|---|
| `EMBED_URL` | Ollama embedding endpoint used by the indexer and the `search_codebase` tool | `http://127.0.0.1:11434/api/embed` |
| `OLLAMA_URL` | Ollama base URL used by `ChatOllama` | `http://127.0.0.1:11434/` |
| `SESSION_PATH` | Root directory for per-session artifacts | `/tmp/RagLLM` |
| `ORNITH_URL` | Optional alternative Ollama endpoint (for the title-generation model) | `http://127.0.0.1:11434/` |

---

## Session Artifacts

Everything an agent session produces is stored under `SESSION_PATH/<session_id>/`:

```
SESSION_PATH/<session_id>/
├── title.txt            # Chat title (web UI only, generated by ornith:35b)
├── history.json         # Serialized LangGraph message history (web UI)
├── CONTEXT0.md, ...     # Compaction summaries — the session's long-term memory
└── <generated files>    # Code/docs written by the create_file tool
```

---

## Context Compaction

When the context grows too large (`/compact` command, or the token threshold is hit), the agent:

1. Sends the conversation history + retrieved documents to the LLM with the template in **`compaction.md`** (Objective / Important Details / Work State / Next Move / Relevant Files).
2. Saves the summary as the next `CONTEXT<n>.md` file in the session folder.
3. Deletes the old message history and re-injects all `CONTEXT*.md` files as the new base context — so the conversation can continue indefinitely without losing earlier decisions.

---

## Retrieval Details

- **Vector size / metric**: 1024-dim, cosine similarity (`qdrant_pipeline/qdrant_main.py:17`).
- **Embedding model**: `qwen3-embedding:0.6b` via the Ollama `/api/embed` endpoint.
- **Score threshold**: results below `0.4` similarity are discarded (`local_llm/agent.py:208`, `interface/app.py:105`).
- **Search limit**: the agent decides; the system prompt instructs it to start with `limit=3` and increase it when the retrieved context is insufficient.
- **Zero-results protocol**: if nothing is found, the agent broadens the search by focusing on `project`, `language`, or `file_path` fields stored in the payloads.

## Notes

- The agent replies in **Turkish** by default, per the active system prompt in `prompts/prompts2.py`.
- The chat model (`glm-5.2:cloud`) and generation settings (temperature `0.4`) are defined in `local_llm/agent.py` and `interface/app.py` — swap in any Ollama-compatible model there.
- Only software-related questions are answered; off-topic requests are politely refused by design.
