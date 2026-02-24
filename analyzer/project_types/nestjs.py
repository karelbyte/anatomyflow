"""
Tipo de proyecto NestJS.
Detección por package.json con @nestjs/core.
"""

import json
import os


def _detect(path: str) -> bool:
    path = os.path.abspath(path)
    if not os.path.isdir(path):
        return False
    pkg = os.path.join(path, "package.json")
    if not os.path.isfile(pkg):
        return False
    try:
        with open(pkg, "r", encoding="utf-8") as f:
            data = json.load(f)
        deps = {**(data.get("dependencies") or {}), **(data.get("devDependencies") or {})}
        if "@nestjs/core" in deps:
            return True
    except (json.JSONDecodeError, OSError):
        pass
    return False


def _classify(file_paths: list[str], base_path: str) -> dict:
    base = os.path.normpath(os.path.abspath(base_path))
    controllers = []
    services = []
    modules = []
    for fp in file_paths:
        full = os.path.normpath(os.path.abspath(fp))
        try:
            rel = os.path.relpath(full, base).replace("\\", "/")
        except ValueError:
            rel = full.replace("\\", "/")
        name = os.path.basename(fp).lower()
        if name.endswith(".controller.ts") or name.endswith(".controller.js"):
            controllers.append(fp)
            continue
        if name.endswith(".service.ts") or name.endswith(".service.js"):
            services.append(fp)
            continue
        if name.endswith(".module.ts") or name.endswith(".module.js"):
            modules.append(fp)
    return {"controllers": controllers, "services": services, "modules": modules}


def _build_prompt_controller(schema: dict, code: str) -> str:
    schema_str = json.dumps(schema, indent=2)
    return f"""You are analyzing a NestJS codebase. Given a database schema (JSON) and a controller file, extract the dependency graph.

Database schema:
{schema_str}

Controller file content:
```
{code}
```

Return a single JSON object with this exact structure (no markdown, no extra text):
{{
  "nodes": [
    {{ "id": "controller:ClassName", "label": "ClassName", "kind": "controller" }},
    {{ "id": "service:ClassName", "label": "ClassName", "kind": "service" }},
    {{ "id": "table:name", "label": "name", "kind": "table" }}
  ],
  "edges": [
    {{ "from": "controller:ClassName", "to": "service:ClassName", "relation": "uses" }},
    {{ "from": "service:ClassName", "to": "table:name", "relation": "reads" | "writes" }}
  ]
}}

Rules:
- kind must be one of: controller, service, table
- id for controller: controller:<ClassName> (e.g. controller:UsersController).
- id for service: service:<ClassName> (e.g. service:UsersService).
- id for table: table:<name> from schema.
- Controllers inject and use services; services may read/write tables. Add edges accordingly.
- Only include nodes and edges you can infer from this file and the schema.
"""


def _build_prompt_service(schema: dict, code: str) -> str:
    schema_str = json.dumps(schema, indent=2)
    return f"""You are analyzing a NestJS codebase. Given a database schema (JSON) and a service file, extract the dependency graph.

Database schema:
{schema_str}

Service file content:
```
{code}
```

Return a single JSON object with this exact structure (no markdown, no extra text):
{{
  "nodes": [
    {{ "id": "service:ClassName", "label": "ClassName", "kind": "service" }},
    {{ "id": "table:name", "label": "name", "kind": "table" }}
  ],
  "edges": [
    {{ "from": "service:ClassName", "to": "table:name", "relation": "reads" | "writes" }}
  ]
}}

Rules:
- kind must be one of: service, table
- id for service: service:<ClassName> (e.g. service:UsersService).
- id for table: table:<name> from schema.
- Only include nodes and edges you can infer from this file and the schema.
"""


def _build_prompt_module(schema: dict, code: str) -> str:
    schema_str = json.dumps(schema, indent=2)
    return f"""You are analyzing a NestJS codebase. Given a database schema (JSON) and a module file, extract the dependency graph.

Database schema:
{schema_str}

Module file content:
```
{code}
```

Return a single JSON object with this exact structure (no markdown, no extra text):
{{
  "nodes": [
    {{ "id": "module:ModuleName", "label": "ModuleName", "kind": "module" }},
    {{ "id": "controller:ClassName", "label": "ClassName", "kind": "controller" }},
    {{ "id": "service:ClassName", "label": "ClassName", "kind": "service" }}
  ],
  "edges": [
    {{ "from": "module:ModuleName", "to": "controller:ClassName", "relation": "declares" }},
    {{ "from": "module:ModuleName", "to": "service:ClassName", "relation": "declares" }}
  ]
}}

Rules:
- kind must be one of: module, controller, service
- id for module: module:<ModuleName> (e.g. module:UsersModule).
- id for controller: controller:<ClassName>, service: service:<ClassName>.
- A module declares controllers and services (imports/providers). Add edges "declares" from module to each.
- Only include nodes and edges you can infer from this file.
"""


NESTJS = {
    "name": "nestjs",
    "detect": _detect,
    "extensions": (".ts", ".js"),
    "exclude_dirs": ("node_modules", "dist", "build", ".git"),
    "classify": _classify,
    "variants": {
        "controllers": {
            "build_prompt": _build_prompt_controller,
            "code_kind": "controller",
        },
        "services": {
            "build_prompt": _build_prompt_service,
            "code_kind": "service",
        },
        "modules": {
            "build_prompt": _build_prompt_module,
            "code_kind": "module",
        },
    },
}
