"""
Tipo de proyecto Express (Node.js).
Detección por package.json con "express" y sin @nestjs/core.
"""

import json
import os


def _detect(path: str) -> bool:
    path = os.path.normpath(os.path.abspath(str(path).strip()))
    if not path or not os.path.isdir(path):
        return False
    pkg = os.path.join(path, "package.json")
    if not os.path.isfile(pkg):
        return False
    try:
        with open(pkg, "r", encoding="utf-8") as f:
            data = json.load(f)
        deps = {**(data.get("dependencies") or {}), **(data.get("devDependencies") or {})}
        if "@nestjs/core" in deps:
            return False
        if "express" in deps:
            return True
    except (json.JSONDecodeError, OSError):
        pass
    return False


def _classify(file_paths: list[str], base_path: str) -> dict:
    base = os.path.normpath(os.path.abspath(base_path))
    routes = []
    middleware = []
    for fp in file_paths:
        full = os.path.normpath(os.path.abspath(fp))
        try:
            rel = os.path.relpath(full, base).replace("\\", "/")
        except ValueError:
            rel = full.replace("\\", "/")
        parts = rel.split("/")
        if "middleware" in parts or "middlewares" in parts:
            middleware.append(fp)
            continue
        if parts and parts[0] == "routes":
            routes.append(fp)
            continue
        if "route" in rel.lower() and (rel.endswith(".js") or rel.endswith(".ts")):
            routes.append(fp)
            continue
        name = os.path.basename(fp).lower()
        if name in ("app.js", "app.ts", "index.js", "index.ts", "server.js", "server.ts"):
            routes.append(fp)
    return {"routes": routes, "middleware": middleware}


def _build_prompt_route(schema: dict, code: str) -> str:
    schema_str = json.dumps(schema, indent=2)
    return f"""You are analyzing an Express.js codebase. Given a database schema (JSON) and a route/handler file, extract the dependency graph.

Database schema:
{schema_str}

Route file content:
```
{code}
```

Return a single JSON object with this exact structure (no markdown, no extra text):
{{
  "nodes": [
    {{ "id": "express_route:method:path", "label": "METHOD path", "kind": "express_route" }},
    {{ "id": "table:name", "label": "name", "kind": "table" }},
    {{ "id": "middleware:name", "label": "name", "kind": "middleware" }}
  ],
  "edges": [
    {{ "from": "node_id", "to": "node_id", "relation": "uses" | "calls" | "reads" | "writes" }}
  ]
}}

Rules:
- kind must be one of: express_route, table, middleware
- id for express_route: express_route:GET:/api/users or express_route:POST:/api/orders (method:path). Infer from app.get, app.post, router.get, router.post, etc.
- id for table: table:<name> from schema.
- Only include nodes and edges you can infer from this file and the schema.
"""


def _build_prompt_middleware(schema: dict, code: str) -> str:
    schema_str = json.dumps(schema, indent=2)
    return f"""You are analyzing an Express.js codebase. Given a database schema (JSON) and a middleware file, extract the dependency graph.

Database schema:
{schema_str}

Middleware file content:
```
{code}
```

Return a single JSON object with this exact structure (no markdown, no extra text):
{{
  "nodes": [
    {{ "id": "middleware:Name", "label": "Name", "kind": "middleware" }}
  ],
  "edges": []
}}

Rules:
- kind must be "middleware" only.
- id: middleware:<Name> from the exported function or file name.
- Only include nodes you can infer from this file.
"""


EXPRESS = {
    "name": "express",
    "detect": _detect,
    "extensions": (".js", ".ts"),
    "exclude_dirs": ("node_modules", "dist", "build", ".git"),
    "classify": _classify,
    "variants": {
        "routes": {
            "build_prompt": _build_prompt_route,
            "code_kind": "express_route",
        },
        "middleware": {
            "build_prompt": _build_prompt_middleware,
            "code_kind": "middleware",
        },
    },
}
