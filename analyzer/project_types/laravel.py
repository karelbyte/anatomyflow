"""
Tipo de proyecto Laravel: controladores, modelos, rutas.
Detección por composer.json (laravel/framework) o carpetas app/Http/Controllers, app/Models, routes.
"""

import json
import os


def _detect(path: str) -> bool:
    path = os.path.abspath(path)
    if not os.path.isdir(path):
        return False
    composer = os.path.join(path, "composer.json")
    if os.path.isfile(composer):
        try:
            with open(composer, "r", encoding="utf-8") as f:
                data = json.load(f)
            req = data.get("require") or {}
            if "laravel/framework" in req or "laravel/framework" in (data.get("require-dev") or {}):
                return True
        except (json.JSONDecodeError, OSError):
            pass
    for sub in ("app/Http/Controllers", "app/Models", "routes"):
        if os.path.isdir(os.path.join(path, sub)):
            return True
    return False


def _classify(file_paths: list[str], base_path: str) -> dict:
    base = os.path.normpath(os.path.abspath(base_path))
    controllers = []
    models = []
    routes = []
    views = []
    for fp in file_paths:
        full = os.path.normpath(os.path.abspath(fp))
        try:
            rel = os.path.relpath(full, base)
        except ValueError:
            rel = full
        parts = rel.replace("\\", "/").split("/")
        if fp.endswith(".blade.php") and "views" in parts:
            views.append(fp)
            continue
        if "Models" in parts:
            models.append(fp)
            continue
        if len(parts) >= 1 and parts[0] == "routes" and fp.endswith(".php"):
            routes.append(fp)
            continue
        if "Controllers" in parts or "Http" in parts:
            controllers.append(fp)
            continue
        controllers.append(fp)
    return {"controllers": controllers, "models": models, "routes": routes, "views": views}


def _build_prompt_controller(schema: dict, code: str) -> str:
    schema_str = json.dumps(schema, indent=2)
    return f"""You are analyzing a legacy codebase. Given a database schema (JSON) and a controller file content, extract the dependency graph.

Database schema:
{schema_str}

Controller file content:
```
{code}
```

Return a single JSON object with this exact structure (no markdown, no extra text):
{{
  "nodes": [
    {{ "id": "unique_id", "label": "display name", "kind": "table" }},
    {{ "id": "unique_id", "label": "display name", "kind": "model" }},
    {{ "id": "unique_id", "label": "display name", "kind": "controller" }},
    {{ "id": "unique_id", "label": "display name", "kind": "route" }},
    {{ "id": "view:dot.path", "label": "dot.path", "kind": "view" }}
  ],
  "edges": [
    {{ "from": "node_id", "to": "node_id", "relation": "uses" | "maps_to" | "calls" | "renders" }}
  ]
}}

Rules:
- kind must be one of: table, model, controller, route, view
- For Laravel: link table -> model (maps_to), model -> controller (uses), controller -> route (calls). Use table names from the schema and infer model/controller/route names from the code.
- If the controller returns a view (e.g. return view('users.index') or view('users.show', ...)), add a node with kind "view", id "view:users.index" (dot path), and an edge from controller to that view with relation "renders".
- id must be unique (e.g. table:orders, model:Order, controller:OrderController, route:POST /api/orders, view:users.index).
- Only include nodes and edges you can infer from the schema and the controller code.
"""


def _build_prompt_model(schema: dict, code: str) -> str:
    schema_str = json.dumps(schema, indent=2)
    return f"""You are analyzing a Laravel codebase. Given a database schema (JSON) and an Eloquent MODEL file (app/Models/*.php), extract the dependency graph for this model only.

Database schema:
{schema_str}

Model file content:
```
{code}
```

Return a single JSON object with this exact structure (no markdown, no extra text):
{{
  "nodes": [
    {{ "id": "table:table_name", "label": "table_name", "kind": "table" }},
    {{ "id": "model:ModelName", "label": "ModelName", "kind": "model" }}
  ],
  "edges": [
    {{ "from": "table:table_name", "to": "model:ModelName", "relation": "maps_to" }}
  ]
}}

Rules:
- kind must be table or model only (no controller/route in model files).
- id: table:<name> and model:<ClassName>. Use table names from the schema; model name from the class.
- One model class maps to one table (maps_to). If the model uses $table, use that; else infer from class name (Order -> orders).
- Only include nodes and edges you can infer from this single model file and the schema.
"""


def _build_prompt_routes(schema: dict, code: str) -> str:
    schema_str = json.dumps(schema, indent=2)
    return f"""You are analyzing a Laravel codebase. Given a database schema (JSON) and a ROUTES file (routes/*.php), extract the dependency graph: routes and which controllers they call.

Database schema:
{schema_str}

Routes file content:
```
{code}
```

Return a single JSON object with this exact structure (no markdown, no extra text):
{{
  "nodes": [
    {{ "id": "controller:ControllerName", "label": "ControllerName", "kind": "controller" }},
    {{ "id": "route:METHOD /path", "label": "METHOD /path", "kind": "route" }}
  ],
  "edges": [
    {{ "from": "controller:ControllerName", "to": "route:METHOD /path", "relation": "calls" }}
  ]
}}

Rules:
- kind: controller and route only (no table/model in routes files).
- id: controller:<ClassName>, route:<METHOD> <path> (e.g. route:GET /api/orders, route:POST /api/orders).
- Edge: controller -> route with relation "calls" (the route calls/invokes the controller).
- Only include nodes and edges you can infer from this routes file.
"""


def _build_prompt_views(schema: dict, code: str) -> str:
    return """You are analyzing a Laravel Blade view. Given the view file content, extract the view identifier and any sub-views (includes/components).

View file content:
```
{code}
```

Return a single JSON object with this exact structure (no markdown, no extra text):
{{
  "nodes": [
    {{ "id": "view:dot.path.name", "label": "dot.path.name", "kind": "view" }},
    ...
  ],
  "edges": [
    {{ "from": "view:parent", "to": "view:child", "relation": "includes" }}
  ]
}}

Rules:
- kind must be "view" only.
- id must be "view:<name>" where name is the Blade view name (e.g. view:users.index, view:components.alert). Infer from file path or @extends/@section.
- If the file @include or @component other views, add edges with relation "includes".
- Only include nodes and edges you can infer from this file.
""".format(code=code)


LARAVEL = {
    "name": "laravel",
    "detect": _detect,
    "extensions": (".php", ".blade.php"),
    "exclude_dirs": ("vendor", "node_modules", "coverage"),  # dependencias y reportes
    "classify": _classify,
    "variants": {
        "controllers": {
            "build_prompt": _build_prompt_controller,
            "code_kind": "controller",
        },
        "models": {
            "build_prompt": _build_prompt_model,
            "code_kind": "model",
        },
        "routes": {
            "build_prompt": _build_prompt_routes,
            "code_kind": None,
        },
        "views": {
            "build_prompt": _build_prompt_views,
            "code_kind": "view",
        },
    },
}
