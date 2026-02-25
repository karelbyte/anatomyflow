import json
import math
import os
import re
import signal
import sys
from pathlib import PurePosixPath

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

def load_schema(path: str) -> dict:
    if not os.path.isfile(path):
        abs_path = os.path.abspath(path)
        raise FileNotFoundError(
            f"Schema file not found: {path!r} (resolved to {abs_path}). "
            "Run the agent first; it saves the schema as {database}.json (e.g. in the agent/ folder)."
        )
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_file(path: str) -> str:
    if not os.path.isfile(path):
        abs_path = os.path.abspath(path)
        raise FileNotFoundError(f"File not found: {path!r} (resolved to {abs_path}).")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

from project_types import get_project_types, get_project_type_by_name
from project_types.laravel import LARAVEL

def filter_files_by_excluded_paths(files: list[str], base_path: str, excluded_paths: list[str]) -> list[str]:
    """Excluye archivos cuya ruta relativa coincide o está bajo alguna de excluded_paths (rutas con /)."""
    if not excluded_paths:
        return files
    base = os.path.normpath(os.path.abspath(base_path))
    normalized_excluded = [os.path.normpath(p).replace("\\", "/").rstrip("/") for p in excluded_paths]
    out = []
    for fp in files:
        full = os.path.normpath(os.path.abspath(fp))
        try:
            rel = os.path.relpath(full, base).replace("\\", "/")
        except ValueError:
            out.append(fp)
            continue
        skip = False
        for ex in normalized_excluded:
            if rel == ex or rel.startswith(ex + "/"):
                skip = True
                break
        if not skip:
            out.append(fp)
    return out


def _has_node_like_files(path: str, exclude_dirs: tuple[str, ...], max_entries: int = 200) -> bool:
    """True si hay archivos .js o .ts bajo path (para fallback cuando no hay package.json)."""
    skip = set(exclude_dirs) | {"node_modules", "vendor", ".git"}
    n = 0
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in skip]
        for name in files:
            if name.lower().endswith((".js", ".ts")):
                return True
            n += 1
            if n >= max_entries:
                return False
    return False


def collect_files(
    path: str,
    extensions: tuple = (".php",),
    exclude_dirs: tuple[str, ...] = (),
) -> list[str]:
    """Recorre path (archivo o carpeta) y devuelve archivos con las extensiones dadas.
    exclude_dirs: nombres de carpetas a no recorrer (ej. 'vendor', 'node_modules')."""
    path = os.path.abspath(path)
    if os.path.isfile(path):
        return [path]
    if not os.path.isdir(path):
        raise FileNotFoundError(f"Path is not a file or directory: {path!r}")
    skip = set(exclude_dirs)
    out = []
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in skip]
        for name in files:
            if name.lower().endswith(extensions):
                out.append(os.path.join(root, name))
    return sorted(out)

def call_openai(prompt: str) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("openai package not installed. Run: pip install openai")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable not set")
    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    return resp.choices[0].message.content.strip()

def call_groq(prompt: str) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("openai package not installed. Run: pip install openai")
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY environment variable not set (or add it to .env)")
    client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    return resp.choices[0].message.content.strip()

def call_anthropic(prompt: str) -> str:
    try:
        from anthropic import Anthropic
    except ImportError:
        raise RuntimeError("anthropic package not installed. Run: pip install anthropic")
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable not set")
    client = Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()

def call_gemini(prompt: str) -> str:
    try:
        from google import genai
    except ImportError:
        raise RuntimeError("google-genai package not installed. Run: pip install google-genai")
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable not set")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    return response.text.strip()

def call_deepseek(prompt: str) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("openai package not installed. Run: pip install openai")
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY environment variable not set")
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    return resp.choices[0].message.content.strip()

def call_openrouter(prompt: str) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError(
            "openai package not installed. OpenRouter uses the OpenAI-compatible API. Run: pip install openai (o uv sync en la carpeta analyzer)"
        )
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY environment variable not set")
    model = os.environ.get("OPENROUTER_MODEL", "openrouter/free")
    client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
    except Exception as e:
        err_str = str(e).lower()
        if "405" in err_str or "blocked" in err_str or "provider" in err_str:
            raise RuntimeError(
                f"OpenRouter returned an error (model {model!r} may be unavailable or blocked). "
                "Set OPENROUTER_MODEL in analyzer/.env to a specific model, e.g.: "
                "OPENROUTER_MODEL=meta-llama/llama-3.1-8b-instruct:free "
                "or OPENROUTER_MODEL=google/gemma-2-9b-it:free"
            ) from e
        raise
    # Con openrouter/free el router elige un modelo gratis; la respuesta indica cuál se usó
    if getattr(resp, "model", None):
        print(f"    OpenRouter model used: {resp.model}", file=sys.stderr)
    if not getattr(resp, "choices", None) or len(resp.choices) == 0:
        raise RuntimeError("OpenRouter devolvió respuesta sin choices (vacía o filtrada)")
    msg = resp.choices[0].message
    content = getattr(msg, "content", None) if msg else None
    if content is None or (isinstance(content, str) and not content.strip()):
        raise RuntimeError("OpenRouter devolvió contenido vacío o null")
    return content.strip() if isinstance(content, str) else str(content)

IA_PROVIDER_CONFIG = {
    "groq": {"key_env": "GROQ_API_KEY", "call": call_groq},
    "openai": {"key_env": "OPENAI_API_KEY", "call": call_openai},
    "anthropic": {"key_env": "ANTHROPIC_API_KEY", "call": call_anthropic},
    "gemini": {"key_env": "GEMINI_API_KEY", "call": call_gemini},
    "deepseek": {"key_env": "DEEPSEEK_API_KEY", "call": call_deepseek},
    "openrouter": {"key_env": "OPENROUTER_API_KEY", "call": call_openrouter},
}

def parse_llm_json(raw: str) -> dict:
    raw = raw.strip()
    if not raw:
        raise json.JSONDecodeError("Empty LLM response", "", 0)
    if raw.startswith("```"):
        lines = raw.split("\n")
        start = 1 if lines[0].startswith("```json") else 1
        try:
            end = next(i for i, L in enumerate(lines) if i > 0 and L.strip() == "```")
        except StopIteration:
            end = len(lines)
        raw = "\n".join(lines[start:end])
    data = json.loads(raw)
    if not isinstance(data, dict) or "nodes" not in data:
        raise ValueError("LLM response is not a graph object (expected dict with 'nodes')")
    return data

def schema_to_ddl(schema: dict, table_name: str):
    """Genera DDL (CREATE TABLE) para una tabla del esquema. table_name sin prefijo 'table:'."""
    tables = schema.get("tables") or []
    table_name_lower = (table_name or "").strip().lower()
    for t in tables:
        name = (t.get("name") or t.get("table_name") or "").strip()
        if name.lower() == table_name_lower:
            cols = t.get("columns") or []
            lines = [f"  {c.get('name', '')} {c.get('type', 'text')}" for c in cols if c.get("name")]
            return "CREATE TABLE " + name + " (\n" + ",\n".join(lines) + "\n);"
    return None


def _schema_table_names(schema: dict) -> set:
    """Conjunto de nombres de tabla del esquema (solo lo que existe en la DB). Comparación case-insensitive."""
    names = set()
    for t in schema.get("tables") or []:
        name = (t.get("name") or t.get("table_name") or "").strip()
        if name:
            names.add(name.lower())
    return names


def _schema_has_tables(schema: dict) -> bool:
    """True si el schema tiene al menos una tabla (análisis con BD). Si no, solo estructura de código."""
    return bool(schema.get("tables"))


NO_SCHEMA_PROMPT_SUFFIX = """

Important: No database schema was provided. Extract only code structure (controllers, routes, pages, components, services, etc.). Do NOT include any nodes with kind "table". Return a single valid JSON object with "nodes" and "edges" arrays only. No markdown, no extra text."""


def _filter_tables_to_schema_only(graph: dict, schema: dict) -> None:
    """Elimina nodos tipo 'table' que no existan en el esquema (DB real). También elimina aristas que los referencian."""
    valid = _schema_table_names(schema)
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    to_remove = set()
    for n in nodes:
        if (n.get("kind") or "").lower() != "table":
            continue
        raw_id = n.get("id") or ""
        table_name = (raw_id.split(":", 1)[-1] if ":" in raw_id else raw_id).strip()
        if table_name.lower() not in valid:
            to_remove.add(raw_id)
    if not to_remove:
        return
    graph["nodes"] = [n for n in nodes if n.get("id") not in to_remove]
    graph["edges"] = [e for e in edges if e.get("from") not in to_remove and e.get("to") not in to_remove]


def _mark_orphans(graph: dict) -> None:
    """Marca nodos huérfanos (sin aristas entrantes ni salientes) en graph['nodes']."""
    node_ids = {n["id"] for n in graph.get("nodes", [])}
    connected = set()
    for e in graph.get("edges", []):
        fid, tid = e.get("from"), e.get("to")
        if fid:
            connected.add(fid)
        if tid:
            connected.add(tid)
    orphan_ids = node_ids - connected
    for n in graph.get("nodes", []):
        n["orphan"] = n["id"] in orphan_ids


def _attach_route_controller_paths(graph: dict) -> None:
    """Para cada nodo route, si hay un controller que apunta a él, guarda controller_path y method_name."""
    nodes_by_id = {n["id"]: n for n in graph.get("nodes", [])}
    for e in graph.get("edges", []):
        cid, rid = e.get("from"), e.get("to")
        if not cid or not rid:
            continue
        controller = nodes_by_id.get(cid)
        route = nodes_by_id.get(rid)
        if not controller or not route or (route.get("kind") or "").lower() != "route":
            continue
        if not controller.get("file_path"):
            continue
        route["controller_path"] = controller["file_path"]
        if "." in (route.get("id") or ""):
            route["method_name"] = (route["id"].split(".", 1)[-1] or "").strip()
        else:
            route["method_name"] = ""


def _filter_external_nodes(graph: dict) -> None:
    """
    Elimina solo nodos realmente externos (no pertenecen al grafo del codebase).
    Se mantienen: (1) nodos con file_path, (2) nodos conectados a ellos por aristas (route, table, view, model
    que no tienen file_path propio pero sí pertenecen al proyecto). Así no se rompen Laravel (route/table) ni
    otros tipos que generen nodos sintéticos; Node/Express/Next/Nest siguen igual porque sus nodos tienen file_path.
    """
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    # Semilla: nodos con file_path (archivos del codebase)
    keep_ids = {n["id"] for n in nodes if n.get("file_path")}
    # Expandir: nodos conectados a los que mantenemos (pertenecen al grafo)
    changed = True
    while changed:
        changed = False
        for e in edges:
            a, b = e.get("from"), e.get("to")
            if a in keep_ids and b not in keep_ids:
                keep_ids.add(b)
                changed = True
            if b in keep_ids and a not in keep_ids:
                keep_ids.add(a)
                changed = True
    graph["nodes"] = [n for n in nodes if n["id"] in keep_ids]
    graph["edges"] = [e for e in edges if e.get("from") in keep_ids and e.get("to") in keep_ids]


def _infer_kind_from_path(file_path: str) -> str:
    """Infiere un rol (kind) a partir de la ruta del archivo para nodos que vienen como 'module'."""
    path = (file_path or "").replace("\\", "/").lower()
    if "/repository/" in path or "/repositories/" in path or path.endswith(".repository.ts") or path.endswith(".repository.js"):
        return "repository"
    if "/route/" in path or "/routes/" in path or ".routes." in path:
        return "route"
    if "/middleware/" in path or ".middleware." in path:
        return "middleware"
    if "/domain/" in path:
        return "entity"
    if "/config/" in path:
        return "adapter"
    if "/auth/" in path or "/service/" in path or "/services/" in path:
        return "service"
    if "/handler/" in path or "/handlers/" in path or "/use-case/" in path or "/usecase/" in path:
        return "handler"
    if path.endswith("app.ts") or path.endswith("app.js") or path.endswith("index.ts") or path.endswith("index.js") or "/server" in path:
        return "module"
    return "module"


def _apply_inferred_kinds(graph: dict) -> None:
    """Para nodos con kind 'module' y file_path, reasigna kind según la ruta (repository, route, middleware, etc.)."""
    for n in graph.get("nodes", []):
        if (n.get("kind") or "").lower() == "module" and n.get("file_path"):
            n["kind"] = _infer_kind_from_path(n["file_path"])


def merge_graphs(graphs: list[dict]) -> dict:
    nodes_by_id = {}
    edges_set = set()
    for g in graphs:
        for n in g.get("nodes", []):
            nid = n.get("id")
            if not nid:
                continue
            if nid not in nodes_by_id:
                nodes_by_id[nid] = {"id": nid, "label": n.get("label", nid), "kind": n.get("kind", "default")}
            if n.get("code") and not nodes_by_id[nid].get("code"):
                nodes_by_id[nid]["code"] = n["code"]
            if n.get("file_path") and not nodes_by_id[nid].get("file_path"):
                nodes_by_id[nid]["file_path"] = n["file_path"]
        for e in g.get("edges", []):
            fid, tid = e.get("from"), e.get("to")
            if fid and tid:
                edges_set.add((fid, tid, e.get("relation", "uses")))
    nodes_list = list(nodes_by_id.values())
    edges_list = [{"from": a, "to": b, "relation": r} for a, b, r in edges_set]
    return {"nodes": nodes_list, "edges": edges_list}

def _build_adjacency(edges: list[dict]) -> tuple[dict, dict]:
    incoming = {}
    outgoing = {}
    for e in edges:
        a, b = e.get("from"), e.get("to")
        if not a or not b:
            continue
        if b not in incoming:
            incoming[b] = []
        incoming[b].append(a)
        if a not in outgoing:
            outgoing[a] = []
        outgoing[a].append(b)
    return incoming, outgoing


def _ensure_local_import_edges(graph: dict) -> None:
    """
    Asegura que haya aristas "imports" entre módulos TypeScript/JavaScript
    cuando hay imports locales (./, ../) en el código fuente, incluso si el
    extractor LLM no las devolvió explícitamente.
    """
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    nodes_by_id = {n.get("id"): n for n in nodes if n.get("id")}
    existing = {(e.get("from"), e.get("to"), e.get("relation", "uses")) for e in edges}

    exts_ts_js = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
    new_edges: list[dict] = []
    new_nodes: list[dict] = []

    for n in nodes:
        nid = n.get("id") or ""
        code = n.get("code") or ""
        file_path = n.get("file_path") or ""
        if not nid or not code or not file_path:
            continue
        if not file_path.endswith(exts_ts_js):
            continue

        specs: set[str] = set()
        # import X from './foo'
        for m in re.finditer(r"from\s+['\"]([^'\"]+)['\"]", code):
            specs.add(m.group(1))
        # import './foo'
        for m in re.finditer(r"\bimport\s+['\"]([^'\"]+)['\"]", code):
            specs.add(m.group(1))

        base_dir = PurePosixPath(file_path).parent

        # 1) Imports locales TS/JS
        for spec in specs:
            # Solo imports locales del propio codebase
            if not spec.startswith("."):
                continue
            try:
                raw_path = (base_dir / spec).as_posix()
                norm_path = os.path.normpath(raw_path).replace("\\", "/")
                # Los nodos TS/JS usan id sin extensión (.ts/.js/etc)
                target_rel = re.sub(r"\.(ts|tsx|js|jsx|mjs|cjs)$", "", norm_path)
            except Exception:
                continue

            target_id = f"module:{target_rel}"
            if target_id not in nodes_by_id:
                continue

            key = (nid, target_id, "imports")
            if key in existing:
                continue

            new_edges.append({"from": nid, "to": target_id, "relation": "imports"})
            existing.add(key)

        # 2) Angular templateUrl / styleUrl(s) → nodos de vista/estilo
        # templateUrl: './login.component.html'
        tpl_match = re.search(r"templateUrl\s*:\s*['\"]([^'\"]+)['\"]", code)
        template_specs: list[str] = []
        if tpl_match:
            template_specs.append(tpl_match.group(1).strip())

        # styleUrl: './login.component.scss'
        style_specs: list[str] = []
        single_style = re.search(r"styleUrl\s*:\s*['\"]([^'\"]+)['\"]", code)
        if single_style:
            style_specs.append(single_style.group(1).strip())
        for m in re.finditer(r"styleUrls?\s*:\s*\[([^\]]*)\]", code, flags=re.S):
            inner = m.group(1)
            for sm in re.finditer(r"['\"]([^'\"]+)['\"]", inner):
                style_specs.append(sm.group(1).strip())

        def _ensure_file_node(spec: str, kind: str, relation: str) -> None:
            nonlocal nodes, nodes_by_id, new_nodes, new_edges, existing
            try:
                raw_path = (base_dir / spec).as_posix()
                target_rel = os.path.normpath(raw_path).replace("\\", "/")
            except Exception:
                return
            node_id = f"{kind}:{target_rel}"
            if node_id not in nodes_by_id:
                label = PurePosixPath(target_rel).name
                node = {
                    "id": node_id,
                    "label": label,
                    "kind": kind if kind != "style" else "style",
                    "file_path": target_rel,
                }
                nodes_by_id[node_id] = node
                new_nodes.append(node)
            key = (nid, node_id, relation)
            if key in existing:
                return
            new_edges.append({"from": nid, "to": node_id, "relation": relation})
            existing.add(key)

        for spec in template_specs:
            _ensure_file_node(spec, "view", "template")
        for spec in style_specs:
            _ensure_file_node(spec, "style", "styles")

    if new_nodes:
        nodes.extend(new_nodes)
        graph["nodes"] = nodes
    if new_edges:
        edges.extend(new_edges)
        graph["edges"] = edges

def _cluster_around_controller(controller_id: str, incoming: dict, outgoing: dict) -> set:
    cluster = {controller_id}
    queue = [controller_id]
    while queue:
        cur = queue.pop()
        for prev in incoming.get(cur, []):
            if prev not in cluster:
                cluster.add(prev)
                queue.append(prev)
        for nxt in outgoing.get(cur, []):
            if nxt not in cluster:
                cluster.add(nxt)
                queue.append(nxt)
    return cluster

def _layout_by_clusters(graph: dict) -> list[dict]:
    nodes_by_id = {n["id"]: n for n in graph.get("nodes", [])}
    edges = graph.get("edges", [])
    incoming, outgoing = _build_adjacency(edges)
    # Semilla de clusters: controller, page, express_route, handler, service (modo genérico)
    controller_ids = [nid for nid, n in nodes_by_id.items() if n.get("kind") == "controller"]
    page_ids = [nid for nid, n in nodes_by_id.items() if n.get("kind") == "page"]
    express_route_ids = [nid for nid, n in nodes_by_id.items() if n.get("kind") == "express_route"]
    handler_ids = [nid for nid, n in nodes_by_id.items() if n.get("kind") == "handler"]
    service_ids = [nid for nid, n in nodes_by_id.items() if n.get("kind") == "service"]
    seed_ids = controller_ids or page_ids or express_route_ids or handler_ids or service_ids
    assigned = set()
    clusters = []
    for cid in seed_ids:
        cluster_ids = _cluster_around_controller(cid, incoming, outgoing)
        cluster_ids = [nid for nid in cluster_ids if nid in nodes_by_id and nid not in assigned]
        if not cluster_ids:
            continue
        for nid in cluster_ids:
            assigned.add(nid)
        clusters.append(cluster_ids)
    orphan = [nid for nid in nodes_by_id if nid not in assigned]
    if orphan:
        clusters.append(orphan)

    # Kinds: convencionales + genéricos (repository, use_case, handler, adapter, entity, factory, other)
    kind_order = {
        "table": 0, "model": 1, "entity": 1, "repository": 2, "service": 2, "use_case": 3,
        "controller": 3, "handler": 3, "adapter": 4, "route": 4, "express_route": 4,
        "view": 5, "style": 5, "page": 5, "api_route": 5, "component": 5, "middleware": 4, "module": 0,
        "factory": 2, "other": 9,
    }
    kinds_layout = [
        "table", "model", "entity", "repository", "service", "use_case", "factory",
        "controller", "handler", "adapter", "route", "express_route", "middleware",
        "view", "style", "page", "api_route", "component", "module", "other",
    ]
    cluster_gap = 28
    node_w = 200
    node_h = 85
    padding = 24
    clusters_per_row = 6

    # Layout circular/radial dentro de cada cluster: nodos ordenados por kind+label, dispuestos en círculo
    def _place_cluster_circular(cluster_ids, nodes_by_id, kind_order, kinds_layout):
        by_kind = {k: [] for k in kinds_layout}
        for nid in cluster_ids:
            n = nodes_by_id.get(nid)
            if not n:
                continue
            k = (n.get("kind") or "default").strip().lower()
            if k not in kind_order:
                k = "other"
            if k not in by_kind:
                by_kind[k] = []
            by_kind[k].append((nid, n.get("label", nid)))
        for k in by_kind:
            by_kind[k].sort(key=lambda x: x[1])
        ordered = []
        for kind in kinds_layout:
            ordered.extend(by_kind.get(kind, []))
        if not ordered:
            return {}, float("inf"), float("inf"), float("-inf"), float("-inf")
        n_nodes = len(ordered)
        # Radio para que los nodos no se solapen: cuerda entre centros >= node_w
        min_radius = (node_w / 2) / math.sin(math.pi / n_nodes) if n_nodes > 1 else 80
        radius = max(100, min_radius)
        local_pos = {}
        cluster_min_x = float("inf")
        cluster_min_y = float("inf")
        cluster_max_x = float("-inf")
        cluster_max_y = float("-inf")
        for i, (nid, _) in enumerate(ordered):
            angle = 2 * math.pi * i / n_nodes - math.pi / 2  # empieza arriba
            cx = radius * math.cos(angle)
            cy = radius * math.sin(angle)
            # React Flow usa esquina superior izquierda
            x = cx - node_w / 2
            y = cy - node_h / 2
            local_pos[nid] = {"x": x, "y": y}
            cluster_min_x = min(cluster_min_x, x)
            cluster_min_y = min(cluster_min_y, y)
            cluster_max_x = max(cluster_max_x, x + node_w)
            cluster_max_y = max(cluster_max_y, y + node_h)
        return local_pos, cluster_min_x, cluster_min_y, cluster_max_x, cluster_max_y

    cluster_data = []
    for cluster_ids in clusters:
        local_pos, cmin_x, cmin_y, cmax_x, cmax_y = _place_cluster_circular(
            cluster_ids, nodes_by_id, kind_order, kinds_layout
        )
        if cmin_x == float("inf"):
            continue
        cw = (cmax_x - cmin_x) + 2 * padding
        ch = (cmax_y - cmin_y) + 2 * padding
        cluster_data.append((cluster_ids, local_pos, cmin_x, cmin_y, cmax_x, cmax_y, cw, ch))

    # Segunda pasada: colocar clusters en filas con gap fijo (empaquetado)
    positions = {}
    node_to_cluster = {}
    result = []
    cursor_x = 0
    cursor_y = 0
    row_heights = []
    for idx, (cluster_ids, local_pos, cmin_x, cmin_y, cmax_x, cmax_y, cw, ch) in enumerate(cluster_data):
        col_in_row = idx % clusters_per_row
        if col_in_row == 0 and idx > 0:
            cursor_x = 0
            cursor_y += (max(row_heights) if row_heights else 0) + cluster_gap
            row_heights = []
        offset_x = cursor_x + padding - cmin_x
        offset_y = cursor_y + padding - cmin_y
        bg_id = f"cluster-bg-{idx}"
        for nid, lp in local_pos.items():
            positions[nid] = {"x": lp["x"] + offset_x, "y": lp["y"] + offset_y}
            node_to_cluster[nid] = bg_id
        row_heights.append(ch)
        result.append({
            "id": bg_id,
            "type": "clusterBg",
            "position": {"x": cursor_x, "y": cursor_y},
            "data": {"width": cw, "height": ch, "label": ""},
        })
        cursor_x += cw + cluster_gap

    for n in graph.get("nodes", []):
        nid = n.get("id")
        pos = positions.get(nid, {"x": 0, "y": 0})
        data = {"label": n.get("label", nid), "kind": n.get("kind", "default"), "orphan": n.get("orphan", False)}
        cluster_id = node_to_cluster.get(nid)
        if cluster_id:
            data["clusterId"] = cluster_id
        if n.get("code"):
            data["code"] = n["code"]
        if n.get("file_path"):
            data["file_path"] = n["file_path"]
        if n.get("controller_path"):
            data["controller_path"] = n["controller_path"]
        if n.get("method_name") is not None:
            data["method_name"] = n["method_name"]
        result.append({
            "id": nid,
            "type": "default",
            "position": pos,
            "data": data,
        })
    return result

def to_react_flow(graph: dict) -> dict:
    nodes = _layout_by_clusters(graph)
    edges = []
    for e in graph.get("edges", []):
        fid = e.get("from")
        tid = e.get("to")
        if fid and tid:
            edge_id = f"{fid}->{tid}"
            edges.append({
                "id": edge_id,
                "source": fid,
                "target": tid,
                "data": {"relation": e.get("relation", "uses")},
            })
    return {"nodes": nodes, "edges": edges}


CHECKPOINT_EVERY = 5  # Escribir checkpoint cada 5 archivos (guardado automático para poder reanudar)
MAX_RETRIES = 2  # Reintentos para archivos que fallan (ej. error de API); se procesan al final


def write_checkpoint(checkpoint_path: str, graphs: list, processed_paths: set) -> None:
    """Guarda checkpoint para poder reanudar después."""
    try:
        data = {"graphs": graphs, "processed_paths": list(processed_paths)}
        with open(checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError as e:
        print(f"Warning: could not write checkpoint: {e}", file=sys.stderr)


def load_checkpoint(checkpoint_path: str):
    """Carga checkpoint; devuelve (graphs, processed_paths_set)."""
    with open(checkpoint_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    graphs = data.get("graphs") or []
    processed = set(data.get("processed_paths") or [])
    return graphs, processed


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Extract dependency graph from codebase using LLM")
    parser.add_argument("schema_path", help="Path to schema JSON")
    parser.add_argument("target_path", help="Path to file or folder to analyze")
    parser.add_argument("--out", dest="out_path", help="Output graph JSON path")
    parser.add_argument("--exclude-file", dest="exclude_file", help="JSON file with list of excluded paths")
    parser.add_argument("--project-type", dest="project_type", help="Force project type (e.g. laravel, nextjs, generic_node). Overrides auto-detect.")
    parser.add_argument("--checkpoint-path", dest="checkpoint_path", help="Path to checkpoint file (save/resume)")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint if it exists")
    args, _ = parser.parse_known_args()

    schema_path = args.schema_path
    target_path = args.target_path
    out_path = args.out_path
    user_excluded_paths = []
    if args.exclude_file and os.path.isfile(args.exclude_file):
        try:
            with open(args.exclude_file, "r", encoding="utf-8") as f:
                user_excluded_paths = json.load(f)
            if not isinstance(user_excluded_paths, list):
                user_excluded_paths = []
        except (OSError, json.JSONDecodeError):
            pass
    if out_path is None:
        schema_dir = os.path.dirname(os.path.abspath(schema_path))
        schema_stem = os.path.splitext(os.path.basename(schema_path))[0]
        out_path = os.path.join(schema_dir, f"{schema_stem}.graph.json")

    checkpoint_path = args.checkpoint_path
    do_resume = args.resume and checkpoint_path and os.path.isfile(checkpoint_path)
    if do_resume:
        graphs, processed_set = load_checkpoint(checkpoint_path)
        print(f"Resuming: {len(graphs)} graphs, {len(processed_set)} files already done", file=sys.stderr)
    else:
        graphs = []
        processed_set = set()

    def save_checkpoint_if_needed():
        if checkpoint_path and processed_set and len(processed_set) % CHECKPOINT_EVERY == 0:
            write_checkpoint(checkpoint_path, graphs, processed_set)

    def on_sigterm(_signum, _frame):
        if checkpoint_path:
            write_checkpoint(checkpoint_path, graphs, processed_set)
            print("Checkpoint saved (SIGTERM). You can resume later.", file=sys.stderr)
        sys.exit(143)

    if checkpoint_path:
        try:
            signal.signal(signal.SIGTERM, on_sigterm)
        except (AttributeError, ValueError):
            pass

    base = os.path.normpath(os.path.abspath(
        target_path if os.path.isdir(target_path) else os.path.dirname(target_path)
    ))
    target_path = base
    project_type = None
    forced_type_name = getattr(args, "project_type", None) if args else None
    if forced_type_name and forced_type_name.strip():
        project_type = get_project_type_by_name(forced_type_name.strip())
        if project_type:
            print(f"Using project type: {project_type['name']!r} (user-selected)", file=sys.stderr)
        else:
            print(f"Unknown --project-type {forced_type_name!r}, falling back to auto-detect", file=sys.stderr)
    if project_type is None:
        for pt in get_project_types():
            if pt["detect"](base):
                project_type = pt
                break

    # Siempre excluir vendor/node_modules/coverage; el tipo de proyecto puede añadir más
    default_exclude = ("vendor", "node_modules", "coverage")

    # Fallback 1: si hay package.json pero ningún tipo lo detectó (path/encoding), usar generic_node
    if project_type is None and os.path.isfile(os.path.join(base, "package.json")):
        types_by_name = {pt["name"]: pt for pt in get_project_types()}
        project_type = types_by_name.get("generic_node")

    # Fallback 2: si sigue sin tipo pero hay archivos .js/.ts, usar generic_node (evita "no .php files" en repos Node)
    if project_type is None and _has_node_like_files(base, default_exclude):
        types_by_name = {pt["name"]: pt for pt in get_project_types()}
        project_type = types_by_name.get("generic_node")

    if project_type and not forced_type_name:
        print(f"Using project type: {project_type['name']!r}", file=sys.stderr)

    extensions = project_type["extensions"] if project_type else (".php",)
    exclude_dirs = tuple(project_type.get("exclude_dirs") or ()) if project_type else ()
    exclude_dirs = tuple(set(default_exclude) | set(exclude_dirs))
    try:
        files = collect_files(target_path, extensions, exclude_dirs=exclude_dirs)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    files = filter_files_by_excluded_paths(files, base, user_excluded_paths)

    if not files:
        ext_str = ", ".join(extensions)
        print(f"No files with extensions {ext_str!r} found under {target_path!r}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(files)} file(s) to analyze", file=sys.stderr)

    schema = load_schema(schema_path)
    if not _schema_has_tables(schema):
        print("No database schema (empty or no tables). Extracting code structure only.", file=sys.stderr)

    provider = None
    flag_provider = None
    for name in IA_PROVIDER_CONFIG:
        if f"--{name}" in sys.argv:
            flag_provider = name
            break
    provider_name = (flag_provider or os.environ.get("IA_PROVIDER") or "").strip().lower()
    if provider_name and provider_name in IA_PROVIDER_CONFIG:
        cfg = IA_PROVIDER_CONFIG[provider_name]
        if not os.environ.get(cfg["key_env"]):
            print(f"Provider {provider_name!r} requires {cfg['key_env']} to be set.", file=sys.stderr)
            sys.exit(1)
        provider = cfg["call"]
    else:
        for _name, cfg in IA_PROVIDER_CONFIG.items():
            if os.environ.get(cfg["key_env"]):
                provider = cfg["call"]
                break
    if provider is None:
        valid = ", ".join(IA_PROVIDER_CONFIG)
        print(f"Set IA_PROVIDER in .env to one of: {valid}", file=sys.stderr)
        print("And set the corresponding API key: GROQ_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY, DEEPSEEK_API_KEY, OPENROUTER_API_KEY", file=sys.stderr)
        sys.exit(1)

    to_retry = []  # (filepath, rel, build_prompt_fn, code_kind) para reintentar al final

    if project_type:
        classified = project_type["classify"](files, base)
        counts = {v: len(paths) for v, paths in classified.items() if paths}
        print(f"Project type: {project_type['name']!r} — {counts}", file=sys.stderr)
        total = sum(len(p) for p in classified.values())
        pending = total - len(processed_set) if do_resume else total
        if do_resume and pending < total:
            print(f"  → Se omiten {len(processed_set)} ya hechos; se analizarán {pending} restantes.", file=sys.stderr)
        idx = 0
        current_run = 0
        for variant_name, path_list in classified.items():
            if not path_list:
                continue
            variant_config = project_type["variants"].get(variant_name)
            if not variant_config:
                continue
            build_prompt_fn = variant_config["build_prompt"]
            code_kind = variant_config.get("code_kind")
            for filepath in path_list:
                idx += 1
                rel = os.path.relpath(filepath, base).replace("\\", "/")
                if rel in processed_set:
                    continue
                current_run += 1
                print(f"  [{current_run}/{pending}] [{variant_name}] {rel}", file=sys.stderr)
                try:
                    code = load_file(filepath)
                    try:
                        prompt = build_prompt_fn(schema, code, file_path=rel)
                    except TypeError:
                        prompt = build_prompt_fn(schema, code)
                    if not _schema_has_tables(schema):
                        prompt += NO_SCHEMA_PROMPT_SUFFIX
                    raw = provider(prompt)
                    graph = parse_llm_json(raw)
                    if code_kind is not None:
                        kind_lower = (code_kind or "").lower()
                        for n in graph.get("nodes", []):
                            if (n.get("kind") or "").lower() == kind_lower:
                                n["code"] = code
                                n["file_path"] = rel
                    else:
                        # code_kind is None (Laravel routes, generic_node): all nodes from this file get code + file_path
                        nodes = graph.get("nodes", [])
                        for nd in nodes:
                            nd["code"] = code
                            nd["file_path"] = rel
                    graphs.append(graph)
                    processed_set.add(rel)
                    save_checkpoint_if_needed()
                except json.JSONDecodeError as e:
                    print(f"    LLM_INVALID_JSON: {e}", file=sys.stderr)
                    to_retry.append((filepath, rel, build_prompt_fn, code_kind))
                except (ValueError, Exception) as e:
                    print(f"    LLM_ERROR: {e}", file=sys.stderr)
                    to_retry.append((filepath, rel, build_prompt_fn, code_kind))
    else:
        fallback_prompt = LARAVEL["variants"]["controllers"]["build_prompt"]
        pending = len(files) - len(processed_set) if do_resume else len(files)
        if do_resume and pending < len(files):
            print(f"  → Se omiten {len(processed_set)} ya hechos; se analizarán {pending} restantes.", file=sys.stderr)
        current_run = 0
        for i, filepath in enumerate(files):
            rel = os.path.relpath(filepath, base).replace("\\", "/")
            if rel in processed_set:
                continue
            current_run += 1
            print(f"  [{current_run}/{pending}] {rel}", file=sys.stderr)
            try:
                code = load_file(filepath)
                prompt = fallback_prompt(schema, code)
                if not _schema_has_tables(schema):
                    prompt += NO_SCHEMA_PROMPT_SUFFIX
                raw = provider(prompt)
                graph = parse_llm_json(raw)
                for n in graph.get("nodes", []):
                    if (n.get("kind") or "").lower() == "controller":
                        n["code"] = code
                        n["file_path"] = rel
                graphs.append(graph)
                processed_set.add(rel)
                save_checkpoint_if_needed()
            except json.JSONDecodeError as e:
                print(f"    LLM_INVALID_JSON: {e}", file=sys.stderr)
                to_retry.append((filepath, rel, fallback_prompt, "controller"))
            except (ValueError, Exception) as e:
                print(f"    LLM_ERROR: {e}", file=sys.stderr)
                to_retry.append((filepath, rel, fallback_prompt, "controller"))

    # Reintentos: los que fallaron se procesan de nuevo al final (hasta MAX_RETRIES veces), con el mismo proveedor/modelo.
    for attempt in range(MAX_RETRIES):
        if not to_retry:
            break
        print(f"  Reintento {attempt + 1}/{MAX_RETRIES}: {len(to_retry)} archivo(s)", file=sys.stderr)
        next_retry = []
        for filepath, rel, build_prompt_fn, code_kind in to_retry:
            try:
                code = load_file(filepath)
                try:
                    prompt = build_prompt_fn(schema, code, file_path=rel)
                except TypeError:
                    prompt = build_prompt_fn(schema, code)
                if not _schema_has_tables(schema):
                    prompt += NO_SCHEMA_PROMPT_SUFFIX
                raw = provider(prompt)
                graph = parse_llm_json(raw)
                if code_kind is not None:
                    kind_lower = (code_kind or "").lower()
                    for n in graph.get("nodes", []):
                        if (n.get("kind") or "").lower() == kind_lower:
                            n["code"] = code
                            n["file_path"] = rel
                else:
                    nodes = graph.get("nodes", [])
                    if nodes:
                        nodes[0]["code"] = code
                        nodes[0]["file_path"] = rel
                graphs.append(graph)
                processed_set.add(rel)
                save_checkpoint_if_needed()
                print(f"    OK: {rel}", file=sys.stderr)
            except json.JSONDecodeError as e:
                print(f"    LLM_INVALID_JSON: {rel} — {e}", file=sys.stderr)
                next_retry.append((filepath, rel, build_prompt_fn, code_kind))
            except (ValueError, Exception) as e:
                print(f"    LLM_ERROR: {rel} — {e}", file=sys.stderr)
                next_retry.append((filepath, rel, build_prompt_fn, code_kind))
        to_retry = next_retry
    if to_retry:
        print(f"  ERROR: {len(to_retry)} archivo(s) fallaron tras {MAX_RETRIES} reintentos (revisa mensajes LLM_INVALID_JSON/LLM_ERROR arriba).", file=sys.stderr)
        for _fp, rel, _fn, _k in to_retry:
            print(f"  Descartado: {rel}", file=sys.stderr)

    if not graphs:
        print("No graphs extracted. Check errors above.", file=sys.stderr)
        sys.exit(1)

    merged = merge_graphs(graphs)
    _ensure_local_import_edges(merged)
    _filter_external_nodes(merged)
    _apply_inferred_kinds(merged)
    _filter_tables_to_schema_only(merged, schema)
    _mark_orphans(merged)
    _attach_route_controller_paths(merged)
    for n in merged.get("nodes", []):
        if (n.get("kind") or "").lower() == "table":
            raw_id = n.get("id") or ""
            table_name = raw_id.split(":", 1)[-1].strip() if ":" in raw_id else raw_id.strip()
            ddl = schema_to_ddl(schema, table_name)
            n["code"] = ddl if ddl else f"-- Table {table_name!r} not found in schema\nCREATE TABLE {table_name} ();"
    react_flow = to_react_flow(merged)
    out_json = json.dumps(react_flow, indent=2)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(out_json)
    print(f"Graph written to {out_path} ({len(react_flow['nodes'])} nodes, {len(react_flow['edges'])} edges)", file=sys.stderr)

if __name__ == "__main__":
    main()
