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
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
import time

import db

# API key opcional: si BACKEND_API_KEY está definido, todas las rutas /api/* (salvo health y auth/github) lo exigen
_BACKEND_API_KEY = os.environ.get("BACKEND_API_KEY", "").strip() or None
# CORS: si FRONTEND_URL está definido, solo ese origen (más localhost); si no, "*"
_FRONTEND_URL = os.environ.get("FRONTEND_URL", "").strip() or None
_RATE_LIMIT_PER_MIN = int(os.environ.get("RATE_LIMIT_PER_MIN", "100"))
_RATE_LIMIT_ANALYZE_PER_MIN = int(os.environ.get("RATE_LIMIT_ANALYZE_PER_MIN", "5"))
_rate_limit_store: dict[str, list[float]] = {}
_rate_limit_lock = threading.Lock()
_RATE_WINDOW = 60.0  # segundos

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


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Si BACKEND_API_KEY está definido, exige X-API-Key en /api/* salvo health y auth/github.
    Para GET /api/projects/{id}/events (SSE), también se acepta api_key por query (EventSource no permite headers)."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path == "/api/health" or path.startswith("/api/auth/github") or path == "/api/webhooks/github":
            return await call_next(request)
        if not _BACKEND_API_KEY:
            return await call_next(request)
        key = request.headers.get("X-API-Key", "").strip()
        if not key and request.method == "GET" and "/events" in path and path.startswith("/api/projects/") and path.endswith("/events"):
            key = (request.query_params.get("api_key") or "").strip()
        if key != _BACKEND_API_KEY:
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing X-API-Key"})
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Límite de peticiones por IP: general y más estricto para POST .../analyze."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        client = request.client.host if request.client else "unknown"
        if request.headers.get("x-forwarded-for"):
            client = request.headers["x-forwarded-for"].split(",")[0].strip()
        now = time.time()
        is_analyze = path.endswith("/analyze") or path.endswith("/analyze/resume")
        limit = _RATE_LIMIT_ANALYZE_PER_MIN if (is_analyze and request.method == "POST") else _RATE_LIMIT_PER_MIN
        key = f"{client}:analyze" if is_analyze else f"{client}:general"
        with _rate_limit_lock:
            if key not in _rate_limit_store:
                _rate_limit_store[key] = []
            times = _rate_limit_store[key]
            times[:] = [t for t in times if now - t < _RATE_WINDOW]
            if len(times) >= limit:
                return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded. Try again later."})
            times.append(now)
        return await call_next(request)


_origins = ["*"]
if _FRONTEND_URL:
    _origins = [
        o.strip() for o in _FRONTEND_URL.split(",") if o.strip()
    ] or [_FRONTEND_URL]
    if "http://localhost:5173" not in _origins and "http://127.0.0.1:5173" not in _origins:
        _origins.extend(["http://localhost:5173", "http://127.0.0.1:5173"])

app.add_middleware(APIKeyMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
def http_exception_handler(_request: Request, exc: HTTPException):
    """Respuesta de error consistente: code + message (y detail para compatibilidad FastAPI)."""
    detail = exc.detail
    if isinstance(detail, list) and detail and isinstance(detail[0], dict):
        message = detail[0].get("msg", str(detail[0]))
    elif isinstance(detail, list) and detail:
        message = str(detail[0])
    else:
        message = str(detail) if detail else "Error"
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": True, "code": exc.status_code, "message": message, "detail": detail},
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
    listen_updates: bool | None = None
    project_type: str | None = None


# Tipos de proyecto para el selector (mismo orden que el analizador; id = name del tipo o '' = auto)
PROJECT_TYPE_CHOICES = [
    {"id": "", "label": "Auto-detect"},
    {"id": "laravel", "label": "Laravel (PHP)"},
    {"id": "nextjs", "label": "Next.js"},
    {"id": "nestjs", "label": "NestJS"},
    {"id": "express", "label": "Express (Node.js)"},
    {"id": "generic_node", "label": "Node/TypeScript (generic)"},
]


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
        listen_updates=payload.listen_updates,
        project_type=payload.project_type,
    )
    return db.project_get(project_id)


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str):
    proj = db.project_get(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    db.project_delete(project_id)
    _delete_repo_folder(project_id)
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


@app.post("/api/projects/{project_id}/github/pull")
def github_pull(project_id: str):
    """
    Actualiza el repositorio clonado desde GitHub (git fetch + checkout).
    Si aún no está clonado, hace el clone. Útil para traer los últimos cambios del remoto.
    """
    proj = db.project_get(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    repo_url = (proj.get("repo_url") or "").strip()
    if not repo_url:
        raise HTTPException(400, "This project has no GitHub repo. Set a repository in Step 1.")
    try:
        _resolve_codebase_path(proj, "")
        return {"ok": True, "message": "Repository updated"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


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


# --- Webhook GitHub: escuchar actualizaciones (push) y re-ejecutar análisis ---
_WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "").strip() or None


def _trigger_analyze_after_webhook(project_id: str) -> None:
    """Ejecuta pull + análisis en segundo plano (mismo flujo que start_analyze)."""
    try:
        proj = db.project_get(project_id)
        if not proj or not (proj.get("repo_url") or "").strip():
            return
        schema = db.schema_get_latest(project_id) or {}
        excluded_paths = proj.get("excluded_paths") or []
        db.graph_delete_all(project_id)
        db.checkpoint_clear(project_id)
        job_id = db.job_create(project_id)
        try:
            codebase_path = _resolve_codebase_path(proj, job_id)
        except Exception as e:
            db.job_set_failed(job_id, str(e))
            return
        checkpoint_dir = tempfile.mkdtemp(prefix="anatomy_webhook_")
        pt = (proj.get("project_type") or "").strip() or None
        thread = threading.Thread(
            target=_run_analyzer,
            args=(job_id, project_id, codebase_path, schema),
            kwargs={"excluded_paths": excluded_paths or None, "checkpoint_dir": checkpoint_dir, "resume": False, "project_type": pt},
        )
        thread.daemon = True
        thread.start()
    except Exception:
        pass


@app.post("/api/webhooks/github")
async def github_webhook(request: Request):
    """
    Webhook que recibe GitHub en cada push. Si el proyecto tiene "Escuchar actualizaciones"
    y el repo/rama coinciden, hace pull y vuelve a ejecutar el análisis (mantiene notas por node_id).
    Configura en GitHub: Settings → Webhooks → Add webhook.
    URL: https://tu-backend/api/webhooks/github
    Secret: el valor de GITHUB_WEBHOOK_SECRET en el .env del backend.
    """
    try:
        raw = await request.body()
        body = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        payload = json.loads(body) if isinstance(body, str) else body
    except Exception:
        raise HTTPException(400, "Invalid JSON body")
    if _WEBHOOK_SECRET:
        sig = request.headers.get("X-Hub-Signature-256", "").strip()
        if not sig or not sig.startswith("sha256="):
            raise HTTPException(401, "Missing or invalid X-Hub-Signature-256")
        import hmac
        import hashlib
        expected = "sha256=" + hmac.new(_WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            raise HTTPException(401, "Invalid webhook signature")
    repo = payload.get("repository") or {}
    full_name = (repo.get("full_name") or "").strip()
    ref = (payload.get("ref") or "").strip()
    if not full_name:
        return {"ok": True, "message": "Ignored (no repository)"}
    branch = ref.replace("refs/heads/", "") if ref.startswith("refs/heads/") else ref
    project_ids = db.project_find_by_repo_branch(full_name, branch)
    for pid in project_ids:
        threading.Thread(target=_trigger_analyze_after_webhook, args=(pid,), daemon=True).start()
    return {"ok": True, "triggered": len(project_ids), "repo": full_name, "branch": branch}


@app.get("/api/projects/{project_id}/webhook-info")
def project_webhook_info(project_id: str, request: Request):
    """Devuelve la URL y el secret (si está configurado) para configurar el webhook en GitHub."""
    proj = db.project_get(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    base = os.environ.get("BACKEND_PUBLIC_URL", "").strip() or str(request.base_url).rstrip("/")
    return {
        "webhook_url": f"{base}/api/webhooks/github",
        "secret_env_var": "GITHUB_WEBHOOK_SECRET",
        "has_secret": bool(_WEBHOOK_SECRET),
        "secret": _WEBHOOK_SECRET if _WEBHOOK_SECRET else None,
    }


# Directorio donde se clonan repos de GitHub (env REPOS_DIR; por defecto ./repos junto al backend)
def _repos_dir() -> str:
    d = os.environ.get("REPOS_DIR", "").strip()
    if not d:
        d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "repos")
    os.makedirs(d, exist_ok=True)
    return d


def _repo_clone_path(project_id: str) -> str:
    """Ruta donde se clona el repo de un proyecto (para borrarla al eliminar el proyecto)."""
    base = _repos_dir()
    clone_name = re.sub(r"[^\w.-]", "_", project_id) or "repo"
    return os.path.join(base, clone_name)


def _delete_repo_folder(project_id: str) -> None:
    """Elimina la carpeta del repo clonado si existe y está dentro de _repos_dir (seguridad)."""
    if not (project_id or "").strip():
        return
    base = os.path.normpath(os.path.abspath(_repos_dir()))
    base_prefix = base.rstrip(os.sep) + os.sep

    def _safe_remove(path: str) -> bool:
        path = os.path.normpath(os.path.abspath(path))
        if not (path == base or path.startswith(base_prefix)):
            return False
        if not os.path.isdir(path):
            return False
        try:
            shutil.rmtree(path)
            return True
        except OSError:
            return False

    # Ruta estándar: _repo_clone_path(project_id) (project_id con caracteres no permitidos → _)
    clone_path = _repo_clone_path(project_id)
    if _safe_remove(clone_path):
        return
    # Fallback: carpeta con el project_id literal (p. ej. UUID con guiones)
    alt_path = os.path.join(base, project_id.strip())
    _safe_remove(alt_path)


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
    clone_path = _repo_clone_path(project_id)
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


def _save_checkpoint_from_disk_if_exists(
    project_id: str, job_id: str, checkpoint_dir: str | None
) -> None:
    """Si el análisis falló o se interrumpió, guarda en BD el último checkpoint escrito en disco."""
    if not checkpoint_dir or not os.path.isdir(checkpoint_dir):
        return
    ck_path = os.path.join(checkpoint_dir, "checkpoint.json")
    if not os.path.isfile(ck_path):
        return
    try:
        with open(ck_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        db.checkpoint_save(project_id, job_id, data)
        db.job_append_log(job_id, "Progreso guardado. Puedes reanudar más tarde.")
    except (OSError, json.JSONDecodeError):
        pass


def _run_analyzer(
    job_id: str,
    project_id: str,
    codebase_path: str,
    schema: dict,
    excluded_paths: list | None = None,
    checkpoint_dir: str | None = None,
    resume: bool = False,
    project_type: str | None = None,
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
        if project_type and (project_type or "").strip():
            cmd.extend(["--project-type", (project_type or "").strip()])
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
            db.job_set_failed(job_id, "Analysis failed. Check the job log.")
            _save_checkpoint_from_disk_if_exists(project_id, job_id, checkpoint_dir)
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
            db.job_set_failed(job_id, "Timeout: el analizador tardó demasiado. Prueba con menos archivos o reanuda más tarde.")
            _save_checkpoint_from_disk_if_exists(project_id, job_id, checkpoint_dir)
    except Exception as e:
            db.job_append_log(job_id, f"ERROR: {e}")
            db.job_set_failed(job_id, f"Error: {e}. Check the log for details.")
            _save_checkpoint_from_disk_if_exists(project_id, job_id, checkpoint_dir)
    finally:
        with _analyzer_procs_lock:
            _job_checkpoint_dirs.pop(job_id, None)
        # Si el análisis no terminó bien, intentar rescatar el checkpoint del disco (crash, kill, etc.)
        job_after = db.job_get(job_id)
        if job_after and job_after.get("status") != "completed":
            _save_checkpoint_from_disk_if_exists(project_id, job_id, checkpoint_dir)
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
        schema = {}  # Opcional: analizar solo código sin agente/schema
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
        kwargs={"excluded_paths": excluded_paths or None, "checkpoint_dir": checkpoint_dir, "resume": False, "project_type": (proj.get("project_type") or "").strip() or None},
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
        schema = {}  # Opcional: reanudar sin schema (solo código)
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
        kwargs={"excluded_paths": excluded_paths or None, "checkpoint_dir": checkpoint_dir, "resume": True, "project_type": (proj.get("project_type") or "").strip() or None},
    )
    thread.daemon = True
    thread.start()
    return {"job_id": job_id, "status": "pending"}


@app.get("/api/project-types")
def list_project_types():
    """Lista de tipos de proyecto para el selector (Auto-detect + Laravel, Next.js, etc.)."""
    return PROJECT_TYPE_CHOICES


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


def _resolve_node_to_file_path(node_id: str, path_prefix: str) -> tuple[str | None, str | None]:
    """
    Resuelve cualquier node_id del grafo a ruta de archivo (Laravel). Genérico para todos los recursos.
    - model:Nombre -> app/Models/Nombre.php
    - controller:NombreController -> app/Http/Controllers/NombreController.php
    - view:carpeta.vista -> resources/views/carpeta/vista.blade.php
    - route:recurso.accion -> app/Http/Controllers/RecursoController.php + método 'accion'
    Retorna (relative_path, method_name); method_name solo para route (para extraer el método).
    """
    if not node_id or ":" not in node_id:
        return None, None
    kind, rest = node_id.split(":", 1)
    rest = (rest or "").strip()
    if not rest:
        return None, None
    kind = kind.lower()
    if kind == "table":
        return None, None  # DDL from schema, not file
    if kind == "model":
        return f"app/Models/{rest}.php", None
    if kind == "controller":
        return f"app/Http/Controllers/{rest}.php", None
    if kind == "view":
        # view:users.index -> resources/views/users/index.blade.php
        view_path = rest.replace(".", "/") + ".blade.php"
        return f"resources/views/{view_path}", None
    if kind == "route":
        # route:recurso.accion (ej. clients.index, orders.show) -> RecursoController + método
        if "." in rest:
            controller_part, method_name = rest.split(".", 1)
            controller_part = (controller_part or "").strip()
            method_name = (method_name or "").strip()
            if controller_part and method_name:
                # PascalCase + Controller (cualquier recurso: clients, orders, products, ...)
                name = controller_part[0].upper() + controller_part[1:] if controller_part else ""
                if not name.endswith("Controller"):
                    name += "Controller"
                return f"app/Http/Controllers/{name}.php", method_name
        return None, None
    return None, None


def _route_controller_candidates(rel_path: str) -> list[str]:
    """
    Para cualquier controlador: devuelve [path_original, path_alternativo] para probar
    singular/plural (OrdersController vs OrderController, ProductsController vs ProductController, etc.).
    """
    if "Controller.php" not in rel_path or "Controllers/" not in rel_path:
        return [rel_path]
    base = "app/Http/Controllers/"
    name = rel_path[len(base):-len(".php")]  # ej. OrdersController, ProductController
    if not name.endswith("Controller"):
        return [rel_path]
    stem = name[:-len("Controller")]  # Orders, Product, ...
    candidates = [rel_path]
    if stem.endswith("s") and len(stem) > 1:
        alt_stem = stem[:-1]  # Orders -> Order, Products -> Product
        candidates.append(f"{base}{alt_stem}Controller.php")
    else:
        candidates.append(f"{base}{stem}sController.php")  # Order -> Orders, Product -> Products
    return candidates


def _extract_php_method(content: str, method_name: str) -> str | None:
    """Extrae el cuerpo de un método PHP por nombre (public function methodName...)."""
    import re
    # Buscar public/protected/private function methodName(...) { ... } (con llaves balanceadas)
    pattern = rf"(?:(?:public|protected|private)\s+)?function\s+{re.escape(method_name)}\s*\([^)]*\)\s*(?::\s*[\w\|\\\\]+)?\s*\{{"
    match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    start = match.start()
    brace_start = content.index("{", start)
    depth = 1
    i = brace_start + 1
    while i < len(content) and depth > 0:
        if content[i] == "{":
            depth += 1
        elif content[i] == "}":
            depth -= 1
        i += 1
    return content[start:i].strip() if depth == 0 else None


def _get_node_path_from_graph(graph: dict | None, node_id: str) -> tuple[str | None, str | None]:
    """
    Si el grafo tiene el nodo con file_path o (para route) controller_path + method_name,
    devuelve (relative_path, method_name). Si no, (None, None).
    """
    if not graph or not node_id:
        return None, None
    for n in graph.get("nodes", []):
        if n.get("id") != node_id:
            continue
        data = n.get("data") or {}
        if data.get("file_path"):
            method = (data.get("method_name") or "").strip() or None
            return data["file_path"], method
        if data.get("controller_path"):
            method = (data.get("method_name") or "").strip()
            if not method and ":" in node_id:
                rest = node_id.split(":", 1)[-1]
                method = (rest.split(".", 1)[-1] if "." in rest else "").strip() or None
            return data["controller_path"], method
        break
    return None, None


@app.get("/api/projects/{project_id}/node-code")
def get_node_code(project_id: str, node_id: str):
    """
    Devuelve el código asociado a cualquier nodo del grafo leyendo del codebase.
    Usa file_path/controller_path guardados en el grafo (del análisis) si existen; si no, infiere por convención.
    """
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
        raise HTTPException(400, "Codebase path is not a directory")
    graph = db.graph_get_latest(project_id)
    rel_path, method_name = _get_node_path_from_graph(graph, node_id)
    if not rel_path:
        rel_path, method_name = _resolve_node_to_file_path(node_id, codebase_path)
    if not rel_path:
        raise HTTPException(404, f"Cannot resolve node to file: {node_id}")
    codebase_abs = os.path.abspath(os.path.normpath(codebase_path))
    candidates = _route_controller_candidates(rel_path) if method_name else [rel_path]
    full_path = None
    for candidate in candidates:
        fp = os.path.abspath(os.path.normpath(os.path.join(codebase_path, candidate)))
        if not fp.startswith(codebase_abs + os.sep) and fp != codebase_abs:
            continue
        if os.path.isfile(fp):
            full_path = fp
            rel_path = candidate
            break
    if not full_path:
        raise HTTPException(404, f"File not found: {rel_path}")
    try:
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError as e:
        raise HTTPException(500, str(e))
    label = (node_id.split(":", 1)[-1] if ":" in node_id else node_id).strip()
    if method_name:
        code = _extract_php_method(content, method_name)
        if not code:
            code = content
        language = "php"
    else:
        code = content
        language = "sql" if node_id.lower().startswith("table:") else "php"
    if rel_path.endswith(".blade.php"):
        language = "blade"
    return {"code": code, "language": language, "label": label, "file_path": rel_path}


def _fetch_code_summary_from_llm(code: str, language: str) -> str | None:
    """One-sentence summary via OpenAI. Returns None if no key or error."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        import urllib.request
        import urllib.error
        body = json.dumps({
            "model": "gpt-4o-mini",
            "messages": [
                {
                    "role": "system",
                    "content": "You answer with a single short sentence in the same language as the user. No markdown."
                },
                {
                    "role": "user",
                    "content": f"Summarize this {language} code in one sentence:\n\n{code[:6000]}"
                }
            ],
            "max_tokens": 120,
        })
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=body.encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        choice = (data.get("choices") or [None])[0]
        if not choice:
            return None
        text = (choice.get("message") or {}).get("content") or ""
        return text.strip() or None
    except Exception:
        return None


@app.get("/api/projects/{project_id}/nodes/{node_id}/code-summary")
def get_node_code_summary(project_id: str, node_id: str):
    """Resumen en una frase del código del nodo (requiere OPENAI_API_KEY)."""
    proj = db.project_get(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    graph = db.graph_get_latest(project_id)
    if not graph:
        raise HTTPException(404, "No graph")
    nodes = graph.get("nodes") or []
    node = next((n for n in nodes if (n.get("id") or n.get("data", {}).get("id")) == node_id), None)
    if not node:
        raise HTTPException(404, "Node not found")
    data = node.get("data") or node
    code = data.get("code") or ""
    if not code or not code.strip():
        return {"summary": None}
    language = "php"
    if (data.get("kind") or "").lower() == "table":
        language = "sql"
    summary = _fetch_code_summary_from_llm(code, language)
    return {"summary": summary}


@app.get("/api/projects/{project_id}/graph")
def get_project_graph(project_id: str):
    proj = db.project_get(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    graph = db.graph_get_latest(project_id)
    if not graph:
        raise HTTPException(404, "No graph yet. Run analysis first.")
    return graph


class ProjectGraphPayload(BaseModel):
    nodes: list = Field(default_factory=list)
    edges: list = Field(default_factory=list)


@app.put("/api/projects/{project_id}/graph")
def put_project_graph(project_id: str, payload: ProjectGraphPayload):
    """Importar grafo: reemplaza el grafo del proyecto con nodes/edges enviados (export/import)."""
    proj = db.project_get(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    if not payload.nodes and not payload.edges:
        raise HTTPException(400, "Graph must have at least nodes or edges.")
    graph = {"nodes": payload.nodes, "edges": payload.edges}
    db.graph_save(project_id, graph)
    return {"ok": True, "message": "Graph imported."}


@app.delete("/api/projects/{project_id}/graph")
def delete_project_graph(project_id: str):
    """Elimina todo el grafo y los checkpoints del proyecto. Para iniciar un análisis de cero."""
    proj = db.project_get(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    db.graph_delete_all(project_id)
    db.checkpoint_clear(project_id)
    return {"ok": True}


@app.get("/api/projects/{project_id}/graph-ui-state")
def get_project_graph_ui_state(project_id: str):
    """Estado persistido de la UI del grafo: nodo seleccionado, path bloqueado, layout, posiciones de nodos."""
    proj = db.project_get(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    return db.graph_ui_state_get(project_id)


class GraphUIStatePayload(BaseModel):
    selected_node_id: str | None = None
    path_locked: bool | None = None
    layout_mode: str | None = None  # "stored" | "cascade"
    node_positions: dict[str, dict[str, float]] | None = None  # { nodeId: { x, y } }


@app.patch("/api/projects/{project_id}/graph-ui-state")
def patch_project_graph_ui_state(project_id: str, payload: GraphUIStatePayload):
    """Actualiza (merge) el estado de la UI del grafo. Campos omitidos no se borran."""
    proj = db.project_get(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    state = {}
    if payload.selected_node_id is not None:
        state["selected_node_id"] = payload.selected_node_id
    if payload.path_locked is not None:
        state["path_locked"] = payload.path_locked
    if payload.layout_mode is not None:
        state["layout_mode"] = payload.layout_mode
    if payload.node_positions is not None:
        state["node_positions"] = payload.node_positions
    if state:
        db.graph_ui_state_save(project_id, state)
    return {"ok": True, "state": db.graph_ui_state_get(project_id)}


@app.get("/api/projects/{project_id}/node-notes")
def get_project_node_notes(project_id: str):
    """Devuelve { node_id: [note1, note2, ...], ... }."""
    proj = db.project_get(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    return {"notes": db.node_notes_get(project_id)}


class NodeNotesPayload(BaseModel):
    node_id: str
    notes: list[str] = Field(default_factory=list)


@app.patch("/api/projects/{project_id}/node-notes")
def patch_project_node_notes(project_id: str, payload: NodeNotesPayload):
    """Actualiza las notas de un nodo. Reemplaza la lista de notas de ese nodo."""
    proj = db.project_get(project_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    all_notes = db.node_notes_get(project_id)
    if payload.notes:
        all_notes[payload.node_id] = payload.notes
    else:
        all_notes.pop(payload.node_id, None)
    db.node_notes_set(project_id, all_notes)
    return {"ok": True, "notes": payload.notes}


def _graph_impact_from_json(graph: dict, node_id: str) -> tuple[list[str], list[str]]:
    """Calcula upstream y downstream desde el grafo JSON (nodes + edges). No usa Neo4j."""
    edges = graph.get("edges") or []
    incoming: dict[str, list[str]] = {}
    outgoing: dict[str, list[str]] = {}
    for e in edges:
        src, tgt = e.get("source"), e.get("target")
        if not src or not tgt:
            continue
        if tgt not in incoming:
            incoming[tgt] = []
        incoming[tgt].append(src)
        if src not in outgoing:
            outgoing[src] = []
        outgoing[src].append(tgt)
    upstream: list[str] = []
    queue = [node_id]
    seen = {node_id}
    while queue:
        cur = queue.pop()
        for prev in incoming.get(cur, []):
            if prev not in seen:
                seen.add(prev)
                upstream.append(prev)
                queue.append(prev)
    downstream: list[str] = []
    queue = [node_id]
    seen = {node_id}
    while queue:
        cur = queue.pop()
        for nxt in outgoing.get(cur, []):
            if nxt not in seen:
                seen.add(nxt)
                downstream.append(nxt)
                queue.append(nxt)
    return upstream, downstream


def _graph_orphans_from_json(graph: dict) -> list[str]:
    """Nodos sin ninguna arista (ni entrante ni saliente). Excluye clusterBg."""
    node_ids = {n["id"] for n in (graph.get("nodes") or []) if not (n.get("id") or "").startswith("cluster-bg-")}
    edges = graph.get("edges") or []
    connected = set()
    for e in edges:
        if e.get("source"):
            connected.add(e["source"])
        if e.get("target"):
            connected.add(e["target"])
    return [nid for nid in node_ids if nid not in connected]


@app.get("/api/projects/{project_id}/impact")
def get_project_impact(project_id: str, node_id: str):
    """Impacto de un nodo: upstream (de los que depende) y downstream (los que lo usan). Usa el grafo guardado en BD, no Neo4j."""
    if db.project_get(project_id) is None:
        raise HTTPException(404, "Project not found")
    graph = db.graph_get_latest(project_id)
    if not graph:
        raise HTTPException(404, "No graph yet. Run analysis first.")
    upstream, downstream = _graph_impact_from_json(graph, node_id)
    return {"node_id": node_id, "upstream": upstream, "downstream": downstream}


@app.get("/api/projects/{project_id}/orphans")
def get_project_orphans(project_id: str):
    """Nodos huérfanos (sin conexiones) del grafo del proyecto. Usa el grafo en BD, no Neo4j."""
    if db.project_get(project_id) is None:
        raise HTTPException(404, "Project not found")
    graph = db.graph_get_latest(project_id)
    if not graph:
        raise HTTPException(404, "No graph yet. Run analysis first.")
    orphan_ids = _graph_orphans_from_json(graph)
    return {"orphan_ids": orphan_ids}


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
