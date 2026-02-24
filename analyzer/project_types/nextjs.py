"""
Tipo de proyecto Next.js (App Router o Pages Router).
Detección por package.json (next) o carpetas app/, pages/.
"""

import json
import os


def _detect(path: str) -> bool:
    path = os.path.abspath(path)
    if not os.path.isdir(path):
        return False
    pkg = os.path.join(path, "package.json")
    if os.path.isfile(pkg):
        try:
            with open(pkg, "r", encoding="utf-8") as f:
                data = json.load(f)
            deps = {**(data.get("dependencies") or {}), **(data.get("devDependencies") or {})}
            if "next" in deps:
                return True
        except (json.JSONDecodeError, OSError):
            pass
    if os.path.isdir(os.path.join(path, "app")):
        return True
    if os.path.isdir(os.path.join(path, "pages")):
        return True
    return False


def _classify(file_paths: list[str], base_path: str) -> dict:
    base = os.path.normpath(os.path.abspath(base_path))
    pages = []
    api_routes = []
    components = []
    for fp in file_paths:
        full = os.path.normpath(os.path.abspath(fp))
        try:
            rel = os.path.relpath(full, base).replace("\\", "/")
        except ValueError:
            rel = full.replace("\\", "/")
        parts = rel.split("/")
        # App Router: app/**/page.tsx|js, app/api/**/route.ts|js
        if parts and parts[0] == "app":
            if "api" in parts and (parts[-1] == "route.ts" or parts[-1] == "route.tsx" or parts[-1] == "route.js" or parts[-1] == "route.jsx"):
                api_routes.append(fp)
                continue
            if parts[-1] in ("page.tsx", "page.ts", "page.jsx", "page.js"):
                pages.append(fp)
                continue
        # Pages Router: pages/*.tsx, pages/api/*.ts
        if parts and parts[0] == "pages":
            if len(parts) > 1 and parts[1] == "api":
                api_routes.append(fp)
                continue
            if parts[-1].endswith((".tsx", ".ts", ".jsx", ".js")):
                pages.append(fp)
                continue
        # components/
        if parts and parts[0] == "components":
            components.append(fp)
    return {"pages": pages, "api_routes": api_routes, "components": components}


def _build_prompt_page(schema: dict, code: str) -> str:
    schema_str = json.dumps(schema, indent=2)
    return f"""You are analyzing a Next.js codebase. Given a database schema (JSON) and a page file (App Router or Pages Router), extract the dependency graph.

Database schema:
{schema_str}

Page file content:
```
{code}
```

Return a single JSON object with this exact structure (no markdown, no extra text):
{{
  "nodes": [
    {{ "id": "page:path/name", "label": "display name", "kind": "page" }},
    {{ "id": "api_route:path", "label": "path", "kind": "api_route" }},
    {{ "id": "component:Name", "label": "Name", "kind": "component" }},
    {{ "id": "table:name", "label": "name", "kind": "table" }}
  ],
  "edges": [
    {{ "from": "node_id", "to": "node_id", "relation": "uses" | "calls" | "fetches" }}
  ]
}}

Rules:
- kind must be one of: page, api_route, component, table
- id for page: page:<route-path> (e.g. page:dashboard, page:users/[id]). Infer from file path (app/dashboard/page.tsx -> page:dashboard).
- id for api_route: api_route:<path> (e.g. api_route:api/users). Infer from file path (app/api/users/route.ts -> api_route:api/users).
- Only include nodes and edges you can infer from this page file and the schema.
- If the page fetches from an API route or uses components, add edges with relation "calls" or "uses".
"""


def _build_prompt_api_route(schema: dict, code: str) -> str:
    schema_str = json.dumps(schema, indent=2)
    return f"""You are analyzing a Next.js API route. Given a database schema (JSON) and the route handler code, extract the dependency graph.

Database schema:
{schema_str}

API route file content:
```
{code}
```

Return a single JSON object with this exact structure (no markdown, no extra text):
{{
  "nodes": [
    {{ "id": "api_route:path", "label": "path", "kind": "api_route" }},
    {{ "id": "table:name", "label": "name", "kind": "table" }}
  ],
  "edges": [
    {{ "from": "api_route:path", "to": "table:name", "relation": "reads" | "writes" }}
  ]
}}

Rules:
- kind must be api_route and table only.
- id for api_route: api_route:<path> inferred from file path (e.g. app/api/users/route.ts -> api_route:api/users).
- Only include nodes and edges you can infer from this file and the schema.
"""


def _build_prompt_component(schema: dict, code: str) -> str:
    schema_str = json.dumps(schema, indent=2)
    return f"""You are analyzing a Next.js component. Given a database schema (JSON) and the component file, extract the dependency graph.

Database schema:
{schema_str}

Component file content:
```
{code}
```

Return a single JSON object with this exact structure (no markdown, no extra text):
{{
  "nodes": [
    {{ "id": "component:Name", "label": "Name", "kind": "component" }},
    {{ "id": "component:ChildName", "label": "ChildName", "kind": "component" }}
  ],
  "edges": [
    {{ "from": "node_id", "to": "node_id", "relation": "uses" }}
  ]
}}

Rules:
- kind must be "component" only.
- id: component:<ComponentName> from the exported component name or file name.
- If this component imports and uses other components, add edges with relation "uses".
- Only include nodes and edges you can infer from this file.
"""


NEXTJS = {
    "name": "nextjs",
    "detect": _detect,
    "extensions": (".ts", ".tsx", ".js", ".jsx"),
    "exclude_dirs": ("node_modules", ".next", "dist", "build", ".git"),
    "classify": _classify,
    "variants": {
        "pages": {
            "build_prompt": _build_prompt_page,
            "code_kind": "page",
        },
        "api_routes": {
            "build_prompt": _build_prompt_api_route,
            "code_kind": "api_route",
        },
        "components": {
            "build_prompt": _build_prompt_component,
            "code_kind": "component",
        },
    },
}
