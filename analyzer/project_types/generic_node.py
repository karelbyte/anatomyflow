"""
Modo genérico para proyectos Node.js: sin asumir convenciones (MVC, hexagonal, DDD, etc.).
Analiza todos los archivos .js/.ts con un único prompt que pide descubrir unidades lógicas
y dependencias; el LLM elige el kind (repository, service, controller, handler, etc.).
"""

import json
import os


def _detect(path: str) -> bool:
    path = os.path.normpath(os.path.abspath(str(path).strip()))
    if not path or not os.path.isdir(path):
        return False
    pkg = os.path.join(path, "package.json")
    return os.path.isfile(pkg)


def _classify(file_paths: list[str], base_path: str) -> dict:
    """No clasifica por carpetas: todos los archivos se analizan igual (descubrimiento real)."""
    return {"files": list(file_paths)}


def _build_prompt(schema: dict, code: str, file_path: str = "") -> str:
    schema_str = json.dumps(schema, indent=2)
    path_hint = f"\nFile path: {file_path}" if file_path else ""
    return f"""You are analyzing ONE file from a Node.js/TypeScript codebase. Build a minimal dependency graph for this file only. Be strict: only what is actually in the code.{path_hint}

Database schema (if empty, ignore):
{schema_str}

File content:
```
{code}
```

Rules (critical):
1. **One node per file**. This file must produce exactly ONE node. The node represents this file as a whole. Do NOT create multiple nodes (no "controller", "service", etc. unless they are the only export). Do NOT invent classes or names that do not appear in the code.
2. **Node id**: Use the file path as basis so it is unique. Example: if file is "src/repositories/user.repository.ts", use id "module:src/repositories/user.repository" or "repository:user.repository" (only if the code actually exports something named like that). Use "module:" + path without extension, or "kind:ExactExportName" if there is a single clear export.
3. **Node label**: The actual export name from the file (e.g. class name or main function name), or the file name without extension. Nothing invented.
4. **kind**: One of: module, repository, service, handler, use_case, entity, adapter, factory, middleware, route, component, other. Pick the one that best matches what the file actually does. If unsure, use "module".
5. **Edges**: Only to nodes that are explicitly imported or required in this file. Use the same id format (e.g. if they import from "./other", the "to" id might be "module:path/to/other"). Do NOT invent edges to controllers or services that are not in the imports.

Return a single JSON object (no markdown, no extra text):
{{
  "nodes": [
    {{ "id": "module:path/to/file", "label": "ActualExportName", "kind": "module" }}
  ],
  "edges": [
    {{ "from": "this_file_id", "to": "imported_id", "relation": "imports" }}
  ]
}}

Remember: ONE node for this file. Only real exports and real imports. No invented names.
"""


GENERIC_NODE = {
    "name": "generic_node",
    "detect": _detect,
    "extensions": (".js", ".ts", ".jsx", ".tsx"),
    "exclude_dirs": ("node_modules", "dist", "build", ".git", "coverage"),
    "classify": _classify,
    "variants": {
        "files": {
            "build_prompt": _build_prompt,
            "code_kind": None,  # attach code to all nodes from this file
        },
    },
}
