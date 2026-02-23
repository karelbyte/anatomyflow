"""
Backend: API para proyectos, esquema (WSS agente), análisis asíncrono y grafo.
Persistencia en Postgres (anatomydb) y opcionalmente Neo4j.
"""

import asyncio
import json
import os
import re
import subprocess
import tempfile
import threading
import shutil

try:
    from dotenv import load_dotenv, dotenv_values
    _env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    load_dotenv(_env_path)
except ImportError:
    dotenv_values = None
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field

import db

# Colas SSE por proyecto: al recibir schema las notificamos para actualizar el front en vivo
_sse_queues: dict[str, list[asyncio.Queue]] = {}
_sse_lock = threading.Lock()

# Procesos del analizador en ejecución: job_id -> subprocess.Popen (para poder cancelar)
_running_analyzer_procs: dict[str, subprocess.Popen] = {}
_analyzer_procs_lock = threading.Lock()
# Directorio de checkpoint por job (para leer checkpoint al cancelar)
_job_checkpoint_dirs: dict[str, str] = {}


def _notify_schema_received(project_id: str) -> None:
    """Avisa a los clientes SSE de este proyecto que se recibió el schema."""
    with _sse_lock:
        queues = _sse_queues.get(project_id, [])[:]
    msg = json.dumps({"event": "schema_received"})
    for q in queues:
        try:
            q.put_nowait(msg)
        except Exception:
            pass

# Estado en memoria (schema y fallback si no hay Neo4j)
_store: dict[str, Any] = {"schema": None, "graph": None}

# Driver Neo4j (sync); None si no está configurado
_neo4j_driver = None


def _get_neo4j_driver():
    global _neo4j_driver
    if _neo4j_driver is not None:
        return _neo4j_driver
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "")
    if not password and uri != "bolt://localhost:7687":
        return None
    try:
        from neo4j import GraphDatabase

        _neo4j_driver = GraphDatabase.driver(uri, auth=(user, password))
        _neo4j_driver.verify_connectivity()
        return _neo4j_driver
    except Exception:
        return None


def _neo4j_database() -> str:
    """Base de datos Neo4j a usar (env NEO4J_DATABASE; por defecto 'neo4j')."""
    return os.environ.get("NEO4J_DATABASE", "neo4j").strip() or "neo4j"


def _neo4j_available() -> bool:
    return _get_neo4j_driver() is not None


def _clear_neo4j_graph(driver):
    """Borra todos los nodos AnatomyNode y sus relaciones."""
    with driver.session(database=_neo4j_database()) as session:
        session.run("MATCH (n:AnatomyNode) DETACH DELETE n")


def _write_graph_to_neo4j(driver, graph: dict) -> None:
    """Persiste el grafo React Flow en Neo4j. Solo nodos 'reales' (no clusterBg)."""
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []

    with driver.session(database=_neo4j_database()) as session:
        for n in nodes:
            nid = n.get("id") or ""
            if nid.startswith("cluster-bg-"):
                continue
            data = n.get("data") or {}
            pos = n.get("position") or {}
            session.run(
                """
                MERGE (n:AnatomyNode {id: $id})
                SET n.label = $label, n.kind = $kind,
                    n.code = $code, n.orphan = $orphan,
                    n.pos_x = $pos_x, n.pos_y = $pos_y
                """,
                id=nid,
                label=data.get("label", nid),
                kind=data.get("kind", "node"),
                code=data.get("code"),
                orphan=bool(data.get("orphan")),
                pos_x=pos.get("x"),
                pos_y=pos.get("y"),
            )
        for e in edges:
            src = e.get("source")
            tgt = e.get("target")
            if not src or not tgt:
                continue
            rel = (e.get("data") or {}).get("relation", "uses")
            session.run(
                """
                MATCH (a:AnatomyNode {id: $from_id}), (b:AnatomyNode {id: $to_id})
                MERGE (a)-[r:RELATES_TO {relation: $relation}]->(b)
                """,
                from_id=src,
                to_id=tgt,
                relation=rel,
            )


def _read_graph_from_neo4j(driver) -> dict | None:
    """Lee el grafo desde Neo4j y lo devuelve en formato React Flow."""
    with driver.session(database=_neo4j_database()) as session:
        nodes_result = session.run(
            "MATCH (n:AnatomyNode) RETURN n.id AS id, n.label AS label, n.kind AS kind, n.code AS code, n.orphan AS orphan, n.pos_x AS pos_x, n.pos_y AS pos_y"
        )
        nodes = []
        for rec in nodes_result:
            nodes.append({
                "id": rec["id"],
                "type": "default",
                "position": {"x": rec["pos_x"] or 0, "y": rec["pos_y"] or 0},
                "data": {
                    "label": rec["label"] or rec["id"],
                    "kind": rec["kind"] or "node",
                    **({"code": rec["code"]} if rec.get("code") else {}),
                    **({"orphan": bool(rec["orphan"])} if rec.get("orphan") is not None else {}),
                },
            })
        if not nodes:
            return None
        edges_result = session.run(
            """
            MATCH (a:AnatomyNode)-[r:RELATES_TO]->(b:AnatomyNode)
            RETURN a.id AS source, b.id AS target, r.relation AS relation
            """
        )
        edges = []
        for i, rec in enumerate(edges_result):
            edges.append({
                "id": f"{rec['source']}->{rec['target']}",
                "source": rec["source"],
                "target": rec["target"],
                "data": {"relation": rec["relation"] or "uses"},
            })
        return {"nodes": nodes, "edges": edges}


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    _get_neo4j_driver()
    yield
    global _neo4j_driver
    if _neo4j_driver:
        _neo4j_driver.close()
        _neo4j_driver = None
    _store["schema"] = None
    _store["graph"] = None


app = FastAPI(title="ProjectAnatomy API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GraphPayload(BaseModel):
    schema_data: dict | None = Field(None, alias="schema")
    graph: dict | None = None


class ProjectCreate(BaseModel):
    name: str
    codebase_path: str = ""
    repo_url: str = ""
    repo_branch: str = "main"


class ProjectUpdate(BaseModel):
    name: str | None = None
    codebase_path: str | None = None
    excluded_paths: list[str] | None = None
    repo_url: str | None = None
    repo_branch: str | None = None


@app.post("/api/graph")
def post_graph(payload: GraphPayload):
    """Recibe esquema y/o grafo (React Flow) y los guarda. Si Neo4j está configurado, persiste el grafo ahí."""
    if payload.schema_data is not None:
        _store["schema"] = payload.schema_data
    if payload.graph is not None:
        if not isinstance(payload.graph, dict) or "nodes" not in payload.graph:
            raise HTTPException(400, "graph must have 'nodes' (and optionally 'edges')")
        _store["graph"] = payload.graph
        driver = _get_neo4j_driver()
        if driver:
            try:
                _clear_neo4j_graph(driver)
                _write_graph_to_neo4j(driver, payload.graph)
            except Exception as e:
                raise HTTPException(502, f"Neo4j write failed: {e}")
    return {
        "ok": True,
        "has_schema": _store["schema"] is not None,
        "has_graph": _store["graph"] is not None,
        "neo4j": _neo4j_available(),
    }


@app.get("/api/graph")
def get_graph():
    """Devuelve esquema y grafo. Si Neo4j está configurado, el grafo se lee desde Neo4j."""
    graph = _store["graph"]
    driver = _get_neo4j_driver()
    if driver:
        try:
            from_neo4j = _read_graph_from_neo4j(driver)
            if from_neo4j is not None:
                graph = from_neo4j
        except Exception:
            pass
    return {
        "schema": _store["schema"],
        "graph": graph,
    }


@app.get("/api/health")
def health():
    neo4j_ok = False
    if _get_neo4j_driver():
        try:
            _get_neo4j_driver().verify_connectivity()
            neo4j_ok = True
        except Exception:
            pass
    return {"status": "ok", "neo4j": neo4j_ok}


# --- Proyectos (Postgres) ---

@app.get("/api/projects")
def list_projects():
    return db.project_list()


@app.post("/api/projects")
def create_project(payload: ProjectCreate):
    proj = db.project_create(
        name=payload.name,
        codebase_path=payload.codebase_path or "",
        repo_url=(payload.repo_url or "").strip(),
        repo_branch=(payload.repo_branch or "main").strip() or "main",
    )
    return proj


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    proj = db.project_get(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    return proj


@app.get("/api/projects/{project_id}/events")
async def project_events(project_id: str):
    """SSE: notifica en vivo cuando el agente envía el schema (schema_received)."""
    if db.project_get(project_id) is None:
        raise HTTPException(404, "Project not found")
    queue: asyncio.Queue = asyncio.Queue()
    with _sse_lock:
        _sse_queues.setdefault(project_id, []).append(queue)

    async def stream():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {event}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            with _sse_lock:
                if project_id in _sse_queues:
                    try:
                        _sse_queues[project_id].remove(queue)
                    except ValueError:
                        pass

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.patch("/api/projects/{project_id}")
def update_project(project_id: str, payload: ProjectUpdate):
    proj = db.project_get(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    db.project_update(
        project_id,
        name=payload.name,
        codebase_path=payload.codebase_path,
        excluded_paths=payload.excluded_paths,
        repo_url=payload.repo_url,
        repo_branch=payload.repo_branch,
    )
    return db.project_get(project_id)


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str):
    proj = db.project_get(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    db.project_delete(project_id)
    return {"ok": True}


# --- GitHub OAuth (por proyecto: cada proyecto vincula su cuenta GitHub) ---

def _github_oauth_config():
    client_id = os.environ.get("GITHUB_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GITHUB_CLIENT_SECRET", "").strip()
    redirect_uri = os.environ.get("GITHUB_REDIRECT_URI", "").strip()
    frontend_url = os.environ.get("FRONTEND_URL", "").strip() or "http://localhost:5173"
    return client_id, client_secret, redirect_uri, frontend_url


@app.get("/api/auth/github")
def github_authorize(project_id: str):
    """Redirige a GitHub para que el usuario autorice el acceso a sus repos (por proyecto)."""
    proj = db.project_get(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    client_id, _client_secret, redirect_uri, _fe = _github_oauth_config()
    if not client_id or not redirect_uri:
        raise HTTPException(
            503,
            "GitHub OAuth not configured. Set GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET and GITHUB_REDIRECT_URI in the backend .env. Create an OAuth App at https://github.com/settings/developers",
        )
    import urllib.parse
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": "repo",
        "state": project_id,
    }
    url = "https://github.com/login/oauth/authorize?" + urllib.parse.urlencode(params)
    return RedirectResponse(url=url, status_code=302)


@app.get("/api/auth/github/callback")
def github_callback(code: str | None = None, state: str | None = None, error: str | None = None):
    """GitHub redirige aquí tras autorizar. Intercambia code por access_token y lo guarda en el proyecto."""
    import urllib.parse
    _, _, _, frontend_url = _github_oauth_config()
    if error:
        return RedirectResponse(url=f"{frontend_url}?github_error={urllib.parse.quote(error)}", status_code=302)
    if not code or not state:
        return RedirectResponse(url=f"{frontend_url}?github_error=missing_code_or_state", status_code=302)
    project_id = state
    if db.project_get(project_id) is None:
        return RedirectResponse(url=f"{frontend_url}?github_error=project_not_found", status_code=302)
    client_id, client_secret, redirect_uri, _fe = _github_oauth_config()
    if not client_id or not client_secret or not redirect_uri:
        return RedirectResponse(url=f"{frontend_url}?github_error=oauth_not_configured", status_code=302)
    import urllib.request
    import urllib.parse
    data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
    }).encode()
    req = urllib.request.Request(
        "https://github.com/login/oauth/access_token",
        data=data,
        headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode())
    except Exception as e:
        return RedirectResponse(url=f"{frontend_url}?github_error=token_exchange_failed", status_code=302)
    access_token = body.get("access_token")
    if not access_token:
        err = body.get("error_description") or body.get("error") or "no token"
        return RedirectResponse(url=f"{frontend_url}?github_error={urllib.parse.quote(str(err))}", status_code=302)
    db.project_set_github_token(project_id, access_token)
    return RedirectResponse(url=f"{frontend_url.rstrip('/')}?github_connected=1&project_id={project_id}", status_code=302)


@app.delete("/api/projects/{project_id}/github")
def disconnect_github(project_id: str):
    """Quita la conexión GitHub del proyecto (borra el token guardado)."""
    if db.project_get(project_id) is None:
        raise HTTPException(404, "Project not found")
    db.project_set_github_token(project_id, None)
    return {"ok": True}


def _github_api_get(project_id: str, path: str) -> list | dict:
    """Llama a la API de GitHub con el token del proyecto. path sin barra inicial (ej. user/repos)."""
    token = db.project_get_github_token(project_id)
    if not token:
        raise HTTPException(400, "Connect GitHub first (no token for this project)")
    import urllib.request
    import urllib.error
    url = f"https://api.github.com/{path}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        try:
            err = json.loads(body)
            msg = err.get("message", body) or str(e)
        except Exception:
            msg = body or str(e)
        if e.code == 401:
            raise HTTPException(401, "GitHub token expired or revoked. Disconnect and connect again.")
        raise HTTPException(e.code, msg or "GitHub API error")
    except Exception as e:
        raise HTTPException(502, str(e))


@app.get("/api/projects/{project_id}/github/repos")
def github_list_repos(project_id: str):
    """Lista los repos del usuario conectado (requiere haber conectado GitHub en este proyecto)."""
    if db.project_get(project_id) is None:
        raise HTTPException(404, "Project not found")
    data = _github_api_get(project_id, "user/repos?per_page=100&sort=updated")
    if not isinstance(data, list):
        return []
    return [
        {"full_name": r.get("full_name"), "name": r.get("name"), "private": bool(r.get("private")), "default_branch": r.get("default_branch") or "main"}
        for r in data
        if r.get("full_name")
    ]


@app.get("/api/projects/{project_id}/github/repos/{owner}/{repo}/branches")
def github_list_branches(project_id: str, owner: str, repo: str):
    """Lista las ramas de un repo (owner/repo). Requiere GitHub conectado."""
    if db.project_get(project_id) is None:
        raise HTTPException(404, "Project not found")
    data = _github_api_get(project_id, f"repos/{owner}/{repo}/branches?per_page=100")
    if not isinstance(data, list):
        return []
    return [{"name": b.get("name")} for b in data if b.get("name")]


# Directorio donde se clonan repos de GitHub (env REPOS_DIR; por defecto ./repos junto al backend)
def _repos_dir() -> str:
    d = os.environ.get("REPOS_DIR", "").strip()
    if not d:
        d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "repos")
    os.makedirs(d, exist_ok=True)
    return d


def _inject_github_token(url: str, token: str | None = None) -> str:
    """Inyecta el token en la URL HTTPS para clonar (token del proyecto OAuth o GITHUB_TOKEN env como fallback)."""
    t = (token or "").strip() or os.environ.get("GITHUB_TOKEN", "").strip()
    if not t or not url.startswith("https://"):
        return url
    if "@" in url.split("//")[1].split("/")[0]:
        return url  # ya tiene credenciales
    return url.replace("https://", f"https://{t}@", 1)


def _clone_or_pull_repo(project_id: str, repo_url: str, branch: str, job_id: str) -> str:
    """Clona el repo (o hace pull si ya existe) y devuelve la ruta absoluta al directorio del repo.
    Escribe mensajes en el log del job si se pasa job_id.
    """
    def log(msg: str):
        if job_id:
            db.job_append_log(job_id, msg)

    repo_url = (repo_url or "").strip()
    branch = (branch or "main").strip() or "main"
    if not repo_url:
        raise ValueError("repo_url is required")
    # Normalizar URL (aceptar github.com/user/repo con o sin .git)
    if re.match(r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$", repo_url):
        repo_url = f"https://github.com/{repo_url}"
    if not repo_url.endswith(".git"):
        repo_url = repo_url.rstrip("/") + ".git"
    # Token del proyecto (OAuth por proyecto) o GITHUB_TOKEN env como fallback
    project_token = db.project_get_github_token(project_id)
    url_with_auth = _inject_github_token(repo_url, project_token)
    base = _repos_dir()
    # Usar un nombre de directorio seguro (project_id puede ser UUID)
    clone_name = re.sub(r"[^\w.-]", "_", project_id) or "repo"
    clone_path = os.path.join(base, clone_name)
    if os.path.isdir(os.path.join(clone_path, ".git")):
        log(f"      Actualizando repo en {clone_path}…")
        try:
            subprocess.run(
                ["git", "fetch", "origin", branch, "--depth=1"],
                cwd=clone_path,
                capture_output=True,
                text=True,
                timeout=120,
            )
            subprocess.run(
                ["git", "checkout", "-q", "origin/" + branch],
                cwd=clone_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except Exception as e:
            log(f"      git pull failed: {e}, usando copia existente.")
    else:
        log(f"      Clonando {repo_url} (rama {branch})…")
        if os.path.isdir(clone_path):
            try:
                shutil.rmtree(clone_path)
            except Exception:
                pass
        os.makedirs(base, exist_ok=True)
        result = subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", branch, url_with_auth, clone_path],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"git clone failed: {err}")
    if not os.path.isdir(clone_path):
        raise RuntimeError("Clone path does not exist after clone")
    return os.path.abspath(clone_path)


def _resolve_codebase_path(proj: dict, job_id: str = "") -> str:
    """Devuelve la ruta del código a analizar: o bien clona el repo (repo_url) o usa codebase_path local."""
    repo_url = (proj.get("repo_url") or "").strip()
    if repo_url:
        return _clone_or_pull_repo(
            proj["id"],
            repo_url,
            (proj.get("repo_branch") or "main").strip() or "main",
            job_id,
        )
    path = (proj.get("codebase_path") or "").strip()
    if not path or not os.path.isdir(path):
        raise HTTPException(400, "Invalid codebase_path. Set a valid directory path or connect a GitHub repo.")
    return path


# Carpetas ocultas en el selector (Browse) y en el árbol del paso 3. Edita aquí para añadir/quitar.
EXCLUDED_FOLDERS = frozenset({
    "node_modules",
    "dist",
    "vendor",
})


def _skip_folder(name: str) -> bool:
    """True si la carpeta no debe mostrarse (Browse y árbol del proyecto)."""
    if name.startswith("."):
        return True
    return name in EXCLUDED_FOLDERS


def _build_tree(path: str, base: str, relative: str, max_depth: int, max_nodes: list) -> dict | None:
    """Construye un nodo de árbol: { name, path, type, children? }. path en relativo con /."""
    if max_nodes[0] <= 0 or max_depth <= 0:
        return None
    try:
        names = sorted(os.listdir(path))
    except OSError:
        return None
    rel = relative.replace("\\", "/") or "."
    name = os.path.basename(path) if path != base else (rel if rel != "." else ".")
    if name == ".":
        name = os.path.basename(base.rstrip(os.sep)) or "root"
    node = {"name": name, "path": rel, "type": "dir", "children": []}
    for n in names:
        if _skip_folder(n):
            continue
        if max_nodes[0] <= 0:
            break
        full = os.path.join(path, n)
        try:
            is_dir = os.path.isdir(full)
        except OSError:
            continue
        child_rel = (rel + "/" + n) if rel != "." else n
        if is_dir:
            child = _build_tree(full, base, child_rel, max_depth - 1, max_nodes)
            if child:
                node["children"].append(child)
                max_nodes[0] -= 1
        else:
            max_nodes[0] -= 1
            node["children"].append({"name": n, "path": child_rel, "type": "file"})
    return node


def _browse_root() -> str:
    """Raíz permitida para el explorador de carpetas (seguridad)."""
    root = (os.environ.get("BROWSER_ROOT") or "").strip()
    if root:
        return os.path.abspath(os.path.normpath(root))
    return os.path.abspath(os.getcwd())


@app.get("/api/browse")
def browse_folders(path: str = ""):
    """Lista carpetas en el servidor para elegir codebase_path. path = ruta a listar (vacío = raíz)."""
    root = _browse_root()
    root = os.path.normpath(root)
    if not path or not path.strip():
        current = root
    else:
        current = os.path.normpath(os.path.abspath(path))
        if not current.startswith(root):
            raise HTTPException(400, "Path outside allowed root")
    if not os.path.isdir(current):
        raise HTTPException(400, "Not a directory or not accessible")
    entries = []
    try:
        for name in sorted(os.listdir(current)):
            if _skip_folder(name):
                continue
            full = os.path.join(current, name)
            try:
                if os.path.isdir(full):
                    entries.append({"name": name, "path": full})
            except OSError:
                continue
    except OSError as e:
        raise HTTPException(400, str(e))
    parent = None
    if current != root:
        parent = os.path.dirname(current)
        if not os.path.normpath(parent).startswith(root):
            parent = root
    return {"current": current, "parent": parent, "entries": entries, "root": root}


@app.get("/api/projects/{project_id}/tree")
def get_project_tree(project_id: str, max_depth: int = 12, max_nodes: int = 2500):
    """Devuelve el árbol de archivos/carpetas del proyecto (ruta local o repo clonado)."""
    proj = db.project_get(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    try:
        codebase_path = _resolve_codebase_path(proj, "")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, str(e))
    if not os.path.isdir(codebase_path):
        raise HTTPException(400, "codebase_path is not a directory or not accessible")
    root_name = os.path.basename(codebase_path.rstrip(os.sep)) or "root"
    counter = [max_nodes]
    root = _build_tree(codebase_path, codebase_path, ".", max_depth, counter)
    if not root:
        root = {"name": root_name, "path": ".", "type": "dir", "children": []}
    else:
        root["name"] = root_name
    return {"root": root, "excluded_paths": proj.get("excluded_paths") or []}


# --- WebSocket para el agente (envía schema) ---

@app.websocket("/ws/agent")
async def ws_agent(websocket: WebSocket):
    await websocket.accept()
    api_key = websocket.query_params.get("api_key")
    if not api_key:
        await websocket.close(code=4001)
        return
    project = db.project_by_api_key(api_key)
    if not project:
        await websocket.close(code=4002)
        return
    try:
        import json
        data = await websocket.receive_text()
        schema = json.loads(data)
        if isinstance(schema, dict) and "schema" in schema:
            schema = schema["schema"]
        db.schema_save(project["id"], schema)
        _notify_schema_received(project["id"])
        await websocket.close(1000)
    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await websocket.close(code=4000)
        except Exception:
            pass


# --- Análisis asíncrono ---

def _get_analyzer_python(analyzer_dir: str) -> str | None:
    """Devuelve el Python del venv del analizador si existe; si no, None."""
    if os.name == "nt":
        candidate = os.path.join(analyzer_dir, ".venv", "Scripts", "python.exe")
    else:
        candidate = os.path.join(analyzer_dir, ".venv", "bin", "python")
    return candidate if os.path.isfile(candidate) else None


def _build_analyzer_env(analyzer_dir: str) -> dict[str, str]:
    """Copia del entorno actual y variables del .env del analizador (IA_PROVIDER, API keys)."""
    env = dict(os.environ)
    if dotenv_values:
        env_path = os.path.join(analyzer_dir, ".env")
        if os.path.isfile(env_path):
            env.update(dotenv_values(env_path))
    return env


def _run_analyzer(
    job_id: str,
    project_id: str,
    codebase_path: str,
    schema: dict,
    excluded_paths: list | None = None,
    checkpoint_dir: str | None = None,
    resume: bool = False,
) -> None:
    """Ejecuta el analizador en subprocess y guarda el grafo. checkpoint_dir: carpeta para checkpoint (guardar/reanudar)."""
    db.job_set_running(job_id)
    db.job_append_log(job_id, "[1/4] Iniciando análisis…" if not resume else "[1/4] Reanudando análisis…")
    analyzer_path = os.environ.get("ANALYZER_SCRIPT")
    if not analyzer_path:
        base = os.path.dirname(os.path.abspath(__file__))
        analyzer_path = os.path.join(base, "..", "analyzer", "extract_deps.py")
    if not os.path.isfile(analyzer_path):
        db.job_append_log(job_id, f"ERROR: No se encuentra el script del analizador: {analyzer_path}")
        db.job_set_failed(job_id, "Analyzer script not found. Set ANALYZER_SCRIPT.")
        return
    db.job_append_log(job_id, f"[2/4] Analizador: {analyzer_path}")
    db.job_append_log(job_id, f"      Ruta del código: {codebase_path}")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(schema, f, indent=2)
        schema_path = f.name
    exclude_file = None
    if excluded_paths:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(excluded_paths, f)
            exclude_file = f.name
    out_path = None
    if checkpoint_dir:
        with _analyzer_procs_lock:
            _job_checkpoint_dirs[job_id] = checkpoint_dir
    try:
        out_path = tempfile.mktemp(suffix=".graph.json")
        db.job_append_log(job_id, "[3/4] Ejecutando analizador (esto puede tardar varios minutos)…")
        analyzer_dir = os.path.dirname(analyzer_path)
        python_exe = os.environ.get("PYTHON") or _get_analyzer_python(analyzer_dir) or "python"
        run_env = _build_analyzer_env(analyzer_dir)
        cmd = [python_exe, analyzer_path, schema_path, codebase_path, "--out", out_path]
        if exclude_file:
            cmd.extend(["--exclude-file", exclude_file])
        if checkpoint_dir:
            ck_path = os.path.join(checkpoint_dir, "checkpoint.json")
            cmd.extend(["--checkpoint-path", ck_path])
            if resume:
                cmd.append("--resume")
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=analyzer_dir,
            env=run_env,
        )
        with _analyzer_procs_lock:
            _running_analyzer_procs[job_id] = proc
        try:
            for line in iter(proc.stdout.readline, ""):
                line = line.rstrip()
                if line:
                    db.job_append_log(job_id, "      " + line)
        finally:
            with _analyzer_procs_lock:
                _running_analyzer_procs.pop(job_id, None)
                _job_checkpoint_dirs.pop(job_id, None)
            proc.wait()
        job = db.job_get(job_id)
        if job and job.get("status") == "cancelled":
            db.job_append_log(job_id, "Análisis detenido por el usuario.")
            return
        if proc.returncode != 0:
            db.job_append_log(job_id, f"ERROR: Analizador terminó con código {proc.returncode}")
            db.job_set_failed(job_id, "Analyzer failed. Revisa el log.")
            return
        db.job_append_log(job_id, "[4/4] Guardando grafo…")
        with open(out_path, "r", encoding="utf-8") as g:
            graph = json.load(g)
        db.graph_save(project_id, graph)
        db.checkpoint_clear(project_id)
        db.job_append_log(job_id, "Listo. Grafo guardado.")
        db.job_set_completed(job_id)
    except subprocess.TimeoutExpired:
        db.job_append_log(job_id, "ERROR: Timeout del analizador.")
        db.job_set_failed(job_id, "Analysis timeout")
    except Exception as e:
        db.job_append_log(job_id, f"ERROR: {e}")
        db.job_set_failed(job_id, str(e))
    finally:
        with _analyzer_procs_lock:
            _job_checkpoint_dirs.pop(job_id, None)
        try:
            os.unlink(schema_path)
        except Exception:
            pass
        if exclude_file and os.path.isfile(exclude_file):
            try:
                os.unlink(exclude_file)
            except Exception:
                pass
        if out_path and os.path.isfile(out_path):
            try:
                os.unlink(out_path)
            except Exception:
                pass


@app.post("/api/projects/{project_id}/analyze")
def start_analyze(project_id: str):
    """Inicia un análisis desde cero: borra grafo y checkpoints anteriores."""
    proj = db.project_get(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    schema = db.schema_get_latest(project_id)
    if not schema:
        raise HTTPException(400, "No schema received yet. Connect the agent and send the schema via WSS.")
    excluded_paths = proj.get("excluded_paths") or []
    db.graph_delete_all(project_id)
    db.checkpoint_clear(project_id)
    job_id = db.job_create(project_id)
    try:
        codebase_path = _resolve_codebase_path(proj, job_id)
    except HTTPException:
        raise
    except Exception as e:
        db.job_set_failed(job_id, str(e))
        raise HTTPException(400, str(e))
    checkpoint_dir = tempfile.mkdtemp(prefix="anatomy_job_")
    thread = threading.Thread(
        target=_run_analyzer,
        args=(job_id, project_id, codebase_path, schema),
        kwargs={"excluded_paths": excluded_paths or None, "checkpoint_dir": checkpoint_dir, "resume": False},
    )
    thread.daemon = True
    thread.start()
    return {"job_id": job_id, "status": "pending"}


@app.post("/api/projects/{project_id}/analyze/resume")
def resume_analyze(project_id: str):
    """Reanuda un análisis a partir del último checkpoint (tras haberlo detenido)."""
    proj = db.project_get(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    _, checkpoint = db.checkpoint_get_latest(project_id)
    if not checkpoint:
        raise HTTPException(400, "No checkpoint to resume. Run an analysis and stop it first.")
    schema = db.schema_get_latest(project_id)
    if not schema:
        raise HTTPException(400, "No schema. Connect the agent and send the schema via WSS.")
    excluded_paths = proj.get("excluded_paths") or []
    job_id = db.job_create(project_id)
    try:
        codebase_path = _resolve_codebase_path(proj, job_id)
    except HTTPException:
        raise
    except Exception as e:
        db.job_set_failed(job_id, str(e))
        raise HTTPException(400, str(e))
    checkpoint_dir = tempfile.mkdtemp(prefix="anatomy_job_")
    ck_path = os.path.join(checkpoint_dir, "checkpoint.json")
    try:
        with open(ck_path, "w", encoding="utf-8") as f:
            json.dump(checkpoint, f, indent=2)
    except OSError as e:
        raise HTTPException(500, f"Could not write checkpoint: {e}")
    thread = threading.Thread(
        target=_run_analyzer,
        args=(job_id, project_id, codebase_path, schema),
        kwargs={"excluded_paths": excluded_paths or None, "checkpoint_dir": checkpoint_dir, "resume": True},
    )
    thread.daemon = True
    thread.start()
    return {"job_id": job_id, "status": "pending"}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = db.job_get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    """Detiene el análisis en curso. Guarda checkpoint para poder reanudar después."""
    job = db.job_get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    with _analyzer_procs_lock:
        proc = _running_analyzer_procs.get(job_id)
        checkpoint_dir = _job_checkpoint_dirs.get(job_id)
    if not proc:
        raise HTTPException(400, "No analysis running for this job. It may have already finished.")
    try:
        proc.terminate()
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    except Exception:
        pass
    db.job_set_cancelled(job_id)
    if checkpoint_dir:
        ck_path = os.path.join(checkpoint_dir, "checkpoint.json")
        if os.path.isfile(ck_path):
            try:
                with open(ck_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                db.checkpoint_save(job["project_id"], job_id, data)
            except (OSError, json.JSONDecodeError):
                pass
    return {"ok": True, "status": "cancelled"}


@app.get("/api/projects/{project_id}/graph")
def get_project_graph(project_id: str):
    proj = db.project_get(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    graph = db.graph_get_latest(project_id)
    if not graph:
        raise HTTPException(404, "No graph yet. Run analysis first.")
    return graph


@app.delete("/api/projects/{project_id}/graph")
def delete_project_graph(project_id: str):
    """Elimina todo el grafo y los checkpoints del proyecto. Para iniciar un análisis de cero."""
    proj = db.project_get(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    db.graph_delete_all(project_id)
    db.checkpoint_clear(project_id)
    return {"ok": True}


@app.get("/api/graph/impact")
def get_impact(node_id: str):
    """Requiere Neo4j. Devuelve nodos que dependen del dado (downstream) y de los que depende (upstream)."""
    driver = _get_neo4j_driver()
    if not driver:
        raise HTTPException(503, "Neo4j not configured")
    try:
        with driver.session(database=_neo4j_database()) as session:
            # Downstream: nodos alcanzables siguiendo RELATES_TO hacia delante
            down = session.run(
                """
                MATCH (a:AnatomyNode {id: $id})-[:RELATES_TO*1..]->(b:AnatomyNode)
                RETURN DISTINCT b.id AS id
                """,
                id=node_id,
            )
            downstream = [r["id"] for r in down]
            # Upstream: nodos desde los que se llega al dado
            up = session.run(
                """
                MATCH (b:AnatomyNode)-[:RELATES_TO*1..]->(a:AnatomyNode {id: $id})
                RETURN DISTINCT b.id AS id
                """,
                id=node_id,
            )
            upstream = [r["id"] for r in up]
        return {"node_id": node_id, "upstream": upstream, "downstream": downstream}
    except Exception as e:
        raise HTTPException(502, str(e))


@app.get("/api/graph/orphans")
def get_orphans():
    """Requiere Neo4j. Devuelve ids de nodos sin ninguna relación (huérfanos)."""
    driver = _get_neo4j_driver()
    if not driver:
        raise HTTPException(503, "Neo4j not configured")
    try:
        with driver.session(database=_neo4j_database()) as session:
            result = session.run(
                """
                MATCH (n:AnatomyNode)
                WHERE NOT (n)-[:RELATES_TO]-()
                RETURN n.id AS id
                """
            )
            ids = [r["id"] for r in result]
        return {"orphans": ids}
    except Exception as e:
        raise HTTPException(502, str(e))
