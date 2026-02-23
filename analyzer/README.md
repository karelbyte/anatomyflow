# Analyzer (Dependency extraction via LLM)

Python script that takes a database schema (JSON from the agent) and a **file or folder** (e.g. a Laravel controller or `app/Http/Controllers`), calls an LLM (Groq, OpenAI, Anthropic, Gemini, DeepSeek or OpenRouter) to infer dependencies per file, merges the results, and outputs a single graph in React Flow–compatible JSON.

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Set **IA_PROVIDER** in `.env` and the corresponding API key (see table below)

## Setup

Using **uv** (recommended):

```bash
cd analyzer
uv sync
```

Using pip (dependencies are in `pyproject.toml`):

```bash
cd analyzer
uv pip install -e .
```

Create a `.env` file (copy from `env.example`). Set **IA_PROVIDER** and the matching API key:

| IA_PROVIDER | API key (env var)   | Model used              |
|-------------|---------------------|--------------------------|
| `groq`      | `GROQ_API_KEY`      | llama-3.3-70b-versatile  |
| `openai`    | `OPENAI_API_KEY`    | gpt-4o-mini              |
| `anthropic` | `ANTHROPIC_API_KEY` | claude-3-5-sonnet-20241022 |
| `gemini`    | `GEMINI_API_KEY`    | gemini-2.5-flash         |
| `deepseek`  | `DEEPSEEK_API_KEY`  | deepseek-chat            |
| `openrouter` | `OPENROUTER_API_KEY` | OPENROUTER_MODEL (default: openrouter/free) |

**Nota:** `groq`, `openrouter` y `deepseek` usan la API compatible con OpenAI y requieren el paquete `openai` (incluido en `pyproject.toml`). Si usas OpenRouter y ves "openai package not installed", ejecuta `uv sync` en la carpeta `analyzer` (o `pip install openai`). Cuando el backend lanza el analizador, usa el Python del venv del analizador (`analyzer/.venv`) y el `.env` del analizador, así que `IA_PROVIDER` y las API keys se leen de `analyzer/.env`.

**OpenRouter**: Con `openrouter/free` el [Free Models Router](https://openrouter.ai/docs/guides/routing/routers/free-models-router) elige automáticamente un modelo gratuito. Para usar un modelo gratis concreto, asigna `OPENROUTER_MODEL` al id del modelo con sufijo `:free` (ej. `meta-llama/llama-3.2-3b-instruct:free`). [Modelos gratis](https://openrouter.ai/models?pricing=free).

Example `.env`:

```
IA_PROVIDER=groq
GROQ_API_KEY=gsk_...
```

## Usage

Run with **uv** (uses the project environment):

```bash
uv run python extract_deps.py schema.json path/to/OrderController.php
uv run python extract_deps.py schema.json path/to/app/Http/Controllers
uv run extract-deps schema.json path/to/Controllers
```

- **Single file**: analyzes that file as a controller and writes the graph.
- **Folder**: finds all `.php`/`.blade.php` files (excluding `vendor`, `node_modules`, `coverage`) and merges results into one graph. If the folder is a **Laravel project root** (detected via `composer.json` or presence of `app/Http/Controllers`, `app/Models`, `routes`), files are classified and analyzed by variant:
  - **Controllers** (`app/Http/Controllers`): table ↔ model ↔ controller ↔ route (prompt actual).
  - **Models** (`app/Models`): table ↔ model (maps_to); el código del modelo se asocia al nodo para verlo en el front.
  - **Routes** (`routes/*.php`): controller ↔ route (calls).
  All subgraphs are merged by node id; tables get DDL from the schema, controllers/models get their source code.

The provider is chosen from **IA_PROVIDER** in `.env`. If unset, the first available API key (Groq, OpenAI, Anthropic, Gemini, DeepSeek, OpenRouter) is used.

### Output

The graph is always written to disk. By default: `{schema_stem}.graph.json` next to the schema (e.g. `zermattcrmdb.json` → `zermattcrmdb.graph.json`). Use `--out path/to/file.json` to override.

```bash
uv run python extract_deps.py zermattcrmdb.json UserController.php
uv run python extract_deps.py zermattcrmdb.json ./app/Http/Controllers
uv run python extract_deps.py zermattcrmdb.json /path/to/laravel-project   # raíz: analiza controllers + models + routes
```

Output is React Flow format: `{ "nodes": [...], "edges": [...] }`. Use **Load graph JSON** in the frontend to visualize it.

## Inputs

- **schema.json**: Output from the Go agent (tables and columns).
- **file_or_folder**: A single file (treated as controller) or a directory. If it is the **root of a Laravel project**, the script detects it and analyzes **controllers**, **models** and **route files** with prompts adapted to each variant, then merges everything into one graph.

## Extensibilidad: otros stacks (Next.js, hexagonal, etc.)

El analizador usa un **registro de tipos de proyecto** (`analyzer/project_types/`). El primero que reconozca la raíz del proyecto se usa para clasificar archivos y elegir prompts por variante.

**Contrato de un tipo de proyecto** (dict):

| Campo | Descripción |
|-------|-------------|
| `name` | Identificador (ej. `"laravel"`). |
| `detect(root_path)` | Función: `True` si esta raíz corresponde a este stack. |
| `extensions` | Tupla de extensiones a escanear (ej. `(".php",)` o `(".ts", ".tsx")`). |
| `classify(files, base_path)` | Función: devuelve `{ "variante": [path, ...], ... }`. |
| `variants` | Dict: para cada variante, `build_prompt(schema, code)` y opcionalmente `code_kind` (tipo de nodo al que asociar el código). |

**Añadir un nuevo stack (p. ej. Next.js con arquitectura hexagonal):**

1. Crear `project_types/nextjs_hexagonal.py` (o el nombre que quieras).
2. Implementar `detect()` (p. ej. `package.json` con `"next"`, carpetas `src/use-cases`, `src/adapters`…).
3. Implementar `classify()` según tu estructura (use-cases, adapters, pages, api routes…).
4. Definir `variants` con un `build_prompt(schema, code)` por variante y el `code_kind` si quieres ver código en el panel.
5. Registrar en `project_types/__init__.py`: añadir el nuevo tipo a la lista en `get_project_types()` (el orden define prioridad de detección).

El grafo de salida sigue siendo el mismo: nodos con `id`, `label`, `kind` y opcionalmente `code`; aristas `from`/`to`/`relation`. Puedes usar `kind` existentes (table, model, controller, route) o nuevos (p. ej. use_case, adapter, page) y extender el frontend para colorear o filtrar por ellos.
