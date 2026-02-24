import json
import os
import signal
import sys

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

from project_types import get_project_types
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
    # Semilla de clusters: controller (Laravel/Nest), page (Next.js), express_route (Express)
    controller_ids = [nid for nid, n in nodes_by_id.items() if n.get("kind") == "controller"]
    page_ids = [nid for nid, n in nodes_by_id.items() if n.get("kind") == "page"]
    express_route_ids = [nid for nid, n in nodes_by_id.items() if n.get("kind") == "express_route"]
    seed_ids = controller_ids or page_ids or express_route_ids
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

    kind_order = {"table": 0, "model": 1, "controller": 2, "route": 3, "view": 4, "page": 2, "api_route": 3, "component": 4, "express_route": 2, "middleware": 3, "service": 1, "module": 0}
    kinds_layout = ["table", "model", "controller", "route", "view", "page", "api_route", "component", "express_route", "middleware", "service", "module"]
    col_width = 240
    row_height = 90
    cluster_gap = 80
    node_w = 200
    node_h = 85
    padding = 24
    clusters_per_row = 5
    # Tamaño de cada “celda” para un montón (ancho ≈ 4 columnas + hueco, alto para varias filas)
    slot_width = len(kinds_layout) * col_width + cluster_gap
    slot_height = 6 * row_height + cluster_gap
    positions = {}
    result = []

    for idx, cluster_ids in enumerate(clusters):
        by_kind = {k: [] for k in kinds_layout}
        for nid in cluster_ids:
            n = nodes_by_id.get(nid)
            if not n:
                continue
            k = n.get("kind") or "default"
            if k not in kind_order:
                k = "route"
            if k not in by_kind:
                by_kind[k] = []
            by_kind[k].append((nid, n.get("label", nid)))
        for k in by_kind:
            by_kind[k].sort(key=lambda x: x[1])

        max_rows = max(len(by_kind.get(k, [])) for k in kinds_layout) or 1
        row_slot = idx // clusters_per_row
        col_slot = idx % clusters_per_row
        offset_x = col_slot * slot_width
        offset_y = row_slot * slot_height
        cluster_min_x = offset_x
        cluster_min_y = offset_y
        for col, kind in enumerate(kinds_layout):
            for row, (nid, _) in enumerate(by_kind.get(kind, [])):
                positions[nid] = {
                    "x": offset_x + col * col_width,
                    "y": offset_y + row * row_height,
                }
        cluster_max_x = offset_x + len(kinds_layout) * col_width + node_w
        cluster_max_y = offset_y + (max_rows - 1) * row_height + node_h
        bg_id = f"cluster-bg-{idx}"
        result.append({
            "id": bg_id,
            "type": "clusterBg",
            "position": {"x": cluster_min_x - padding, "y": cluster_min_y - padding},
            "data": {
                "width": cluster_max_x - cluster_min_x + 2 * padding,
                "height": cluster_max_y - cluster_min_y + 2 * padding,
                "label": "",
            },
        })

    for n in graph.get("nodes", []):
        nid = n.get("id")
        pos = positions.get(nid, {"x": 0, "y": 0})
        data = {"label": n.get("label", nid), "kind": n.get("kind", "default"), "orphan": n.get("orphan", False)}
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


CHECKPOINT_EVERY = 5  # Escribir checkpoint cada N archivos procesados
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
    for pt in get_project_types():
        if pt["detect"](base):
            project_type = pt
            break

    # Siempre excluir vendor/node_modules/coverage; el tipo de proyecto puede añadir más
    default_exclude = ("vendor", "node_modules", "coverage")

    # Fallback 1: si hay package.json pero ningún tipo lo detectó (path/encoding en detect), elegir por dependencias
    if project_type is None and os.path.isfile(os.path.join(base, "package.json")):
        try:
            with open(os.path.join(base, "package.json"), "r", encoding="utf-8") as f:
                pkg = json.load(f)
            deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
            types_by_name = {pt["name"]: pt for pt in get_project_types()}
            if "next" in deps:
                project_type = types_by_name.get("nextjs")
            elif "@nestjs/core" in deps:
                project_type = types_by_name.get("nestjs")
            elif "express" in deps:
                project_type = types_by_name.get("express")
        except (OSError, json.JSONDecodeError):
            pass

    # Fallback 2: si sigue sin tipo pero hay archivos .js/.ts, usar Express (evita "no .php files" en repos Node)
    if project_type is None and _has_node_like_files(base, default_exclude):
        types_by_name = {pt["name"]: pt for pt in get_project_types()}
        project_type = types_by_name.get("express")

    if project_type:
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
                    prompt = build_prompt_fn(schema, code)
                    if not _schema_has_tables(schema):
                        prompt += NO_SCHEMA_PROMPT_SUFFIX
                    raw = provider(prompt)
                    graph = parse_llm_json(raw)
                    if code_kind:
                        kind_lower = (code_kind or "").lower()
                        for n in graph.get("nodes", []):
                            if (n.get("kind") or "").lower() == kind_lower:
                                n["code"] = code
                                n["file_path"] = rel
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
                prompt = build_prompt_fn(schema, code)
                if not _schema_has_tables(schema):
                    prompt += NO_SCHEMA_PROMPT_SUFFIX
                raw = provider(prompt)
                graph = parse_llm_json(raw)
                if code_kind:
                    kind_lower = (code_kind or "").lower()
                    for n in graph.get("nodes", []):
                        if (n.get("kind") or "").lower() == kind_lower:
                            n["code"] = code
                            n["file_path"] = rel
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
