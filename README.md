# Project Anatomy (AI-Driven Legacy Architect – PoC)

PoC for mapping relationships between legacy code, database schema, and API routes. Pipeline: **Agent (Go)** → schema JSON → **Analyzer (Python + LLM)** → graph JSON → **Frontend (React + React Flow)**.

## Repository layout

| Folder      | Role |
|------------|------|
| `agent/`   | Go binary: connects to MySQL/Postgres, reads `information_schema`, outputs schema JSON. |
| `analyzer/`| Python script: takes schema JSON + controller file, calls OpenAI or Anthropic, outputs graph JSON (nodes/edges). |
| `frontend/`| React (Vite) + React Flow: loads graph JSON and renders interactive diagram. |

## Quick start

1. **Schema** (requires a running DB):
   ```bash
   cd agent && go mod tidy && go build -o schema-extractor .
   ./schema-extractor -db mysql -dsn "user:pass@tcp(localhost:3306)/dbname" > schema.json
   ```

2. **Graph** (requires `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`):
   ```bash
   cd analyzer && uv sync
   uv run python extract_deps.py ../schema.json path/to/Controller.php --out graph.json
   ```

3. **Visualize**:
   ```bash
   cd frontend && npm install && npm run dev
   ```
   In the app, use **Load graph JSON** and select `graph.json`.

## Docs

- [agent/README.md](agent/README.md) – build and run the schema extractor.
- [analyzer/README.md](analyzer/README.md) – run dependency extraction with OpenAI/Anthropic.
- [frontend/README.md](frontend/README.md) – run and build the graph UI.

## Product vision

See [ideas.md](ideas.md) for full product vision and architecture. This repo implements the PoC steps: schema extraction, LLM-based dependency extraction, and a basic React Flow visualizer.
