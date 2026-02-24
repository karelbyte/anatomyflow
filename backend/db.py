"""
Capa de acceso a PostgreSQL (anatomydb).
Conexión desde env: DATABASE_URL o POSTGRES_*.
"""

import json
import os
import uuid
from contextlib import contextmanager
from datetime import datetime

try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    load_dotenv(_env_path)
except ImportError:
    pass

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL and all(os.environ.get(k) for k in ("POSTGRES_HOST", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")):
    DATABASE_URL = "postgresql://{user}:{password}@{host}:{port}/{db}".format(
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
        db=os.environ.get("POSTGRES_DB", "anatomydb"),
    )

def _is_sqlite():
    return not DATABASE_URL or "sqlite" in DATABASE_URL

def get_engine():
    from sqlalchemy import create_engine
    url = DATABASE_URL or "sqlite:///./anatomydb.sqlite"
    return create_engine(url, connect_args={"check_same_thread": False} if "sqlite" in url else {})

_engine = None

def get_db_engine():
    global _engine
    if _engine is None:
        _engine = get_engine()
    return _engine

@contextmanager
def session_scope():
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=get_db_engine(), autocommit=False, autoflush=False)
    session = Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def init_db():
    """Crea las tablas si no existen."""
    from sqlalchemy import text
    engine = get_db_engine()
    if _is_sqlite():
        # SQLite para desarrollo sin Postgres
        with engine.connect() as c:
            c.execute(text("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    codebase_path TEXT NOT NULL DEFAULT '',
                    agent_api_key TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """))
            c.execute(text("""
                CREATE TABLE IF NOT EXISTS project_schemas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    schema TEXT NOT NULL,
                    received_at TEXT NOT NULL
                )
            """))
            c.execute(text("""
                CREATE TABLE IF NOT EXISTS analysis_jobs (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    error_message TEXT,
                    log TEXT DEFAULT ''
                )
            """))
            try:
                c.execute(text("ALTER TABLE analysis_jobs ADD COLUMN log TEXT DEFAULT ''"))
            except Exception:
                pass
            c.commit()
            c.execute(text("""
                CREATE TABLE IF NOT EXISTS graphs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    graph TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """))
            c.execute(text("""
                CREATE TABLE IF NOT EXISTS project_checkpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    job_id TEXT NOT NULL,
                    checkpoint TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """))
            c.execute(text("""
                CREATE TABLE IF NOT EXISTS project_node_notes (
                    project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
                    notes TEXT NOT NULL DEFAULT '{}'
                )
            """))
            c.commit()
            try:
                c.execute(text("ALTER TABLE projects ADD COLUMN excluded_paths TEXT DEFAULT '[]'"))
                c.commit()
            except Exception:
                pass
            for col, default in (("repo_url", "''"), ("repo_branch", "'main'")):
                try:
                    c.execute(text(f"ALTER TABLE projects ADD COLUMN {col} TEXT DEFAULT {default}"))
                    c.commit()
                except Exception:
                    pass
            try:
                c.execute(text("ALTER TABLE projects ADD COLUMN github_access_token TEXT"))
                c.commit()
            except Exception:
                pass
        return
    # Postgres
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS projects (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(255) NOT NULL,
                codebase_path TEXT NOT NULL DEFAULT '',
                agent_api_key VARCHAR(255) NOT NULL UNIQUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS project_schemas (
                id SERIAL PRIMARY KEY,
                project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                schema JSONB NOT NULL,
                received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS analysis_jobs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                status VARCHAR(32) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                started_at TIMESTAMPTZ,
                finished_at TIMESTAMPTZ,
                error_message TEXT,
                log TEXT DEFAULT ''
            )
        """))
        try:
            conn.execute(text("ALTER TABLE analysis_jobs ADD COLUMN IF NOT EXISTS log TEXT DEFAULT ''"))
        except Exception:
            pass
        for col, default in (("repo_url", "''"), ("repo_branch", "'main'")):
            try:
                conn.execute(text(f"ALTER TABLE projects ADD COLUMN IF NOT EXISTS {col} TEXT DEFAULT {default}"))
            except Exception:
                pass
        try:
            conn.execute(text("ALTER TABLE projects ADD COLUMN IF NOT EXISTS github_access_token TEXT"))
        except Exception:
            pass
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS graphs (
                id SERIAL PRIMARY KEY,
                project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                graph JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS project_checkpoints (
                id SERIAL PRIMARY KEY,
                project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                job_id UUID NOT NULL,
                checkpoint JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS project_node_notes (
                project_id UUID PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
                notes JSONB NOT NULL DEFAULT '{}'
            )
        """))
        try:
            conn.execute(text("ALTER TABLE projects ADD COLUMN IF NOT EXISTS excluded_paths JSONB DEFAULT '[]'"))
            conn.commit()
        except Exception:
            pass
        conn.commit()


def project_create(name: str, codebase_path: str = "", repo_url: str = "", repo_branch: str = "main") -> dict:
    """Crea un proyecto y devuelve el dict con id, agent_api_key, etc."""
    import secrets
    pid = str(uuid.uuid4())
    api_key = secrets.token_urlsafe(32)
    now = datetime.utcnow().isoformat() + "Z"
    with session_scope() as s:
        from sqlalchemy import text
        if _is_sqlite():
            try:
                s.execute(text(
                    "INSERT INTO projects (id, name, codebase_path, agent_api_key, created_at, updated_at, repo_url, repo_branch) VALUES (:id, :name, :path, :key, :now, :now, :repo_url, :repo_branch)"
                ), {"id": pid, "name": name, "path": codebase_path or "", "key": api_key, "now": now, "repo_url": repo_url or "", "repo_branch": repo_branch or "main"})
            except Exception:
                s.execute(text(
                    "INSERT INTO projects (id, name, codebase_path, agent_api_key, created_at, updated_at) VALUES (:id, :name, :path, :key, :now, :now)"
                ), {"id": pid, "name": name, "path": codebase_path or "", "key": api_key, "now": now})
        else:
            s.execute(text(
                "INSERT INTO projects (id, name, codebase_path, agent_api_key, created_at, updated_at, repo_url, repo_branch) VALUES (CAST(:id AS uuid), :name, :path, :key, CAST(:now AS timestamptz), CAST(:now AS timestamptz), :repo_url, :repo_branch)"
            ), {"id": pid, "name": name, "path": codebase_path or "", "key": api_key, "now": now, "repo_url": repo_url or "", "repo_branch": repo_branch or "main"})
    return {"id": pid, "name": name, "codebase_path": codebase_path or "", "agent_api_key": api_key, "created_at": now, "updated_at": now, "repo_url": repo_url or "", "repo_branch": repo_branch or "main"}


def _parse_excluded_paths(val) -> list:
    if val is None:
        return []
    if isinstance(val, list):
        return val
    try:
        import json
        return json.loads(val) if isinstance(val, str) else []
    except Exception:
        return []


def project_list() -> list:
    with session_scope() as s:
        from sqlalchemy import text
        try:
            r = s.execute(text("SELECT id, name, codebase_path, agent_api_key, created_at, updated_at, excluded_paths, repo_url, repo_branch FROM projects ORDER BY created_at DESC"))
            has_repo_cols = True
        except Exception:
            try:
                r = s.execute(text("SELECT id, name, codebase_path, agent_api_key, created_at, updated_at, excluded_paths FROM projects ORDER BY created_at DESC"))
            except Exception:
                r = s.execute(text("SELECT id, name, codebase_path, agent_api_key, created_at, updated_at FROM projects ORDER BY created_at DESC"))
            has_repo_cols = False
        rows = r.fetchall()
        r2 = s.execute(text("SELECT DISTINCT project_id FROM graphs"))
        ids_with_graph = {str(row[0]) for row in r2.fetchall()}
    if not rows:
        return []
    out = []
    for r in rows:
        row_list = list(r)
        if len(row_list) < 7:
            row_list.extend([[]] * (7 - len(row_list)))
        excluded = _parse_excluded_paths(row_list[6])
        proj_id = str(row_list[0])
        keys = ["id", "name", "codebase_path", "agent_api_key", "created_at", "updated_at"]
        d = dict(zip(keys, (proj_id, row_list[1], row_list[2], row_list[3], row_list[4].isoformat() if hasattr(row_list[4], "isoformat") else row_list[4], row_list[5].isoformat() if hasattr(row_list[5], "isoformat") else row_list[5])))
        d["excluded_paths"] = excluded
        d["has_graph"] = proj_id in ids_with_graph
        if has_repo_cols and len(row_list) >= 9:
            d["repo_url"] = row_list[7] or ""
            d["repo_branch"] = row_list[8] or "main"
        else:
            d["repo_url"] = ""
            d["repo_branch"] = "main"
        out.append(d)
    return out


def project_get(project_id: str) -> dict | None:
    with session_scope() as s:
        from sqlalchemy import text
        try:
            if _is_sqlite():
                r = s.execute(text("SELECT id, name, codebase_path, agent_api_key, created_at, updated_at, excluded_paths, repo_url, repo_branch FROM projects WHERE id = :id"), {"id": project_id})
            else:
                r = s.execute(text("SELECT id, name, codebase_path, agent_api_key, created_at, updated_at, excluded_paths, repo_url, repo_branch FROM projects WHERE id = CAST(:id AS uuid)"), {"id": project_id})
            row = r.fetchone()
            has_repo_cols = True
        except Exception:
            try:
                if _is_sqlite():
                    r = s.execute(text("SELECT id, name, codebase_path, agent_api_key, created_at, updated_at, excluded_paths FROM projects WHERE id = :id"), {"id": project_id})
                else:
                    r = s.execute(text("SELECT id, name, codebase_path, agent_api_key, created_at, updated_at, excluded_paths FROM projects WHERE id = CAST(:id AS uuid)"), {"id": project_id})
            except Exception:
                if _is_sqlite():
                    r = s.execute(text("SELECT id, name, codebase_path, agent_api_key, created_at, updated_at FROM projects WHERE id = :id"), {"id": project_id})
                else:
                    r = s.execute(text("SELECT id, name, codebase_path, agent_api_key, created_at, updated_at FROM projects WHERE id = CAST(:id AS uuid)"), {"id": project_id})
            row = r.fetchone()
            has_repo_cols = False
    if not row:
        return None
    keys = ["id", "name", "codebase_path", "agent_api_key", "created_at", "updated_at"]
    d = dict(zip(keys, (str(row[0]), row[1], row[2], row[3], row[4].isoformat() if hasattr(row[4], "isoformat") else row[4], row[5].isoformat() if hasattr(row[5], "isoformat") else row[5])))
    d["excluded_paths"] = _parse_excluded_paths(row[6]) if len(row) > 6 else []
    d["repo_url"] = (row[7] or "") if has_repo_cols and len(row) > 8 else ""
    d["repo_branch"] = (row[8] or "main") if has_repo_cols and len(row) > 8 else "main"
    with session_scope() as s:
        from sqlalchemy import text
        if _is_sqlite():
            r = s.execute(text("SELECT 1 FROM project_schemas WHERE project_id = :id ORDER BY received_at DESC LIMIT 1"), {"id": project_id})
        else:
            r = s.execute(text("SELECT 1 FROM project_schemas WHERE project_id = CAST(:id AS uuid) ORDER BY received_at DESC LIMIT 1"), {"id": project_id})
        d["has_schema"] = r.fetchone() is not None
        if _is_sqlite():
            r = s.execute(text("SELECT 1 FROM graphs WHERE project_id = :id LIMIT 1"), {"id": project_id})
        else:
            r = s.execute(text("SELECT 1 FROM graphs WHERE project_id = CAST(:id AS uuid) LIMIT 1"), {"id": project_id})
        d["has_graph"] = r.fetchone() is not None
        if _is_sqlite():
            r = s.execute(text("SELECT 1 FROM project_checkpoints WHERE project_id = :id LIMIT 1"), {"id": project_id})
        else:
            r = s.execute(text("SELECT 1 FROM project_checkpoints WHERE project_id = CAST(:id AS uuid) LIMIT 1"), {"id": project_id})
        d["has_checkpoint"] = r.fetchone() is not None
    d["has_github_connected"] = project_has_github_connected(project_id)
    return d


def project_update(project_id: str, name: str | None = None, codebase_path: str | None = None, excluded_paths: list | None = None, repo_url: str | None = None, repo_branch: str | None = None) -> bool:
    import json
    from sqlalchemy import text
    updates = []
    params = {"id": project_id}
    if name is not None:
        updates.append("name = :name")
        params["name"] = name
    if codebase_path is not None:
        updates.append("codebase_path = :path")
        params["path"] = codebase_path
    if excluded_paths is not None:
        params["excluded"] = json.dumps(excluded_paths)
        updates.append("excluded_paths = :excluded" if _is_sqlite() else "excluded_paths = CAST(:excluded AS jsonb)")
    if repo_url is not None:
        updates.append("repo_url = :repo_url")
        params["repo_url"] = repo_url
    if repo_branch is not None:
        updates.append("repo_branch = :repo_branch")
        params["repo_branch"] = repo_branch
    if not updates:
        return True
    updates.append("updated_at = :now")
    params["now"] = datetime.utcnow().isoformat() + "Z" if _is_sqlite() else datetime.utcnow()
    with session_scope() as s:
        try:
            if _is_sqlite():
                s.execute(text(f"UPDATE projects SET {', '.join(updates)} WHERE id = :id"), params)
            else:
                s.execute(text(f"UPDATE projects SET {', '.join(updates)} WHERE id = CAST(:id AS uuid)"), params)
        except Exception:
            # Si excluded_paths no existe como columna, actualizar sin ella
            if "excluded_paths" in str(updates):
                updates = [u for u in updates if "excluded_paths" not in u]
                params.pop("excluded", None)
                if len(updates) > 1:
                    if _is_sqlite():
                        s.execute(text(f"UPDATE projects SET {', '.join(updates)} WHERE id = :id"), params)
                    else:
                        s.execute(text(f"UPDATE projects SET {', '.join(updates)} WHERE id = CAST(:id AS uuid)"), params)
            else:
                raise
    return True


def project_delete(project_id: str) -> bool:
    with session_scope() as s:
        from sqlalchemy import text
        if _is_sqlite():
            s.execute(text("DELETE FROM projects WHERE id = :id"), {"id": project_id})
        else:
            s.execute(text("DELETE FROM projects WHERE id = CAST(:id AS uuid)"), {"id": project_id})
    return True


def project_set_github_token(project_id: str, token: str | None) -> bool:
    """Guarda el token OAuth de GitHub del proyecto. token=None para desconectar."""
    with session_scope() as s:
        from sqlalchemy import text
        tok = (token or "").strip() or None
        if _is_sqlite():
            s.execute(text("UPDATE projects SET github_access_token = :tok WHERE id = :id"), {"id": project_id, "tok": tok})
        else:
            s.execute(text("UPDATE projects SET github_access_token = :tok WHERE id = CAST(:id AS uuid)"), {"id": project_id, "tok": tok})
    return True


def project_get_github_token(project_id: str) -> str | None:
    """Devuelve el token de GitHub del proyecto (solo uso interno, nunca exponer en API)."""
    with session_scope() as s:
        from sqlalchemy import text
        try:
            if _is_sqlite():
                r = s.execute(text("SELECT github_access_token FROM projects WHERE id = :id"), {"id": project_id})
            else:
                r = s.execute(text("SELECT github_access_token FROM projects WHERE id = CAST(:id AS uuid)"), {"id": project_id})
            row = r.fetchone()
        except Exception:
            return None
    if not row or not row[0] or not str(row[0]).strip():
        return None
    return str(row[0]).strip()


def project_has_github_connected(project_id: str) -> bool:
    """True si el proyecto tiene un token de GitHub guardado."""
    return project_get_github_token(project_id) is not None


def project_by_api_key(api_key: str) -> dict | None:
    with session_scope() as s:
        from sqlalchemy import text
        r = s.execute(text("SELECT id, name, codebase_path, agent_api_key, created_at, updated_at FROM projects WHERE agent_api_key = :key"), {"key": api_key})
        row = r.fetchone()
    if not row:
        return None
    keys = ["id", "name", "codebase_path", "agent_api_key", "created_at", "updated_at"]
    return dict(zip(keys, (str(row[0]), row[1], row[2], row[3], row[4].isoformat() if hasattr(row[4], "isoformat") else row[4], row[5].isoformat() if hasattr(row[5], "isoformat") else row[5])))


def schema_save(project_id: str, schema: dict) -> None:
    import json
    now = datetime.utcnow().isoformat() + "Z" if _is_sqlite() else datetime.utcnow()
    with session_scope() as s:
        from sqlalchemy import text
        if _is_sqlite():
            s.execute(text("INSERT INTO project_schemas (project_id, schema, received_at) VALUES (:pid, :schema, :now)"), {"pid": project_id, "schema": json.dumps(schema), "now": now})
        else:
            s.execute(text("INSERT INTO project_schemas (project_id, schema, received_at) VALUES (CAST(:pid AS uuid), CAST(:schema AS jsonb), :now)"), {"pid": project_id, "schema": json.dumps(schema), "now": now})


def schema_get_latest(project_id: str) -> dict | None:
    import json
    with session_scope() as s:
        from sqlalchemy import text
        if _is_sqlite():
            r = s.execute(text("SELECT schema FROM project_schemas WHERE project_id = :id ORDER BY received_at DESC LIMIT 1"), {"id": project_id})
        else:
            r = s.execute(text("SELECT schema FROM project_schemas WHERE project_id = CAST(:id AS uuid) ORDER BY received_at DESC LIMIT 1"), {"id": project_id})
        row = r.fetchone()
    if not row:
        return None
    raw = row[0]
    return raw if isinstance(raw, dict) else json.loads(raw)


def job_create(project_id: str) -> str:
    jid = str(uuid.uuid4())
    now = datetime.utcnow().isoformat() + "Z" if _is_sqlite() else datetime.utcnow()
    with session_scope() as s:
        from sqlalchemy import text
        if _is_sqlite():
            s.execute(text("INSERT INTO analysis_jobs (id, project_id, status, created_at) VALUES (:id, :pid, 'pending', :now)"), {"id": jid, "pid": project_id, "now": now})
        else:
            s.execute(text("INSERT INTO analysis_jobs (id, project_id, status, created_at) VALUES (CAST(:id AS uuid), CAST(:pid AS uuid), 'pending', :now)"), {"id": jid, "pid": project_id, "now": now})
    return jid


def job_get(job_id: str) -> dict | None:
    with session_scope() as s:
        from sqlalchemy import text
        if _is_sqlite():
            r = s.execute(text("SELECT id, project_id, status, created_at, started_at, finished_at, error_message, log FROM analysis_jobs WHERE id = :id"), {"id": job_id})
        else:
            r = s.execute(text("SELECT id, project_id, status, created_at, started_at, finished_at, error_message, log FROM analysis_jobs WHERE id = CAST(:id AS uuid)"), {"id": job_id})
        row = r.fetchone()
    if not row:
        return None
    log_val = row[7] if len(row) > 7 else ""
    return {
        "id": str(row[0]),
        "project_id": str(row[1]),
        "status": row[2],
        "created_at": row[3].isoformat() if hasattr(row[3], "isoformat") else row[3],
        "started_at": row[4].isoformat() if row[4] and hasattr(row[4], "isoformat") else row[4],
        "finished_at": row[5].isoformat() if row[5] and hasattr(row[5], "isoformat") else row[5],
        "error_message": row[6],
        "log": log_val or "",
    }


def job_append_log(job_id: str, message: str) -> None:
    with session_scope() as s:
        from sqlalchemy import text
        if _is_sqlite():
            r = s.execute(text("SELECT log FROM analysis_jobs WHERE id = :id"), {"id": job_id})
        else:
            r = s.execute(text("SELECT log FROM analysis_jobs WHERE id = CAST(:id AS uuid)"), {"id": job_id})
        row = r.fetchone()
        current = (row[0] or "") if row else ""
        new_log = (current + "\n" + message).strip() if current else message
        if _is_sqlite():
            s.execute(text("UPDATE analysis_jobs SET log = :log WHERE id = :id"), {"id": job_id, "log": new_log})
        else:
            s.execute(text("UPDATE analysis_jobs SET log = :log WHERE id = CAST(:id AS uuid)"), {"id": job_id, "log": new_log})


def job_set_running(job_id: str) -> None:
    now = datetime.utcnow().isoformat() + "Z" if _is_sqlite() else datetime.utcnow()
    with session_scope() as s:
        from sqlalchemy import text
        if _is_sqlite():
            s.execute(text("UPDATE analysis_jobs SET status = 'running', started_at = :now WHERE id = :id"), {"id": job_id, "now": now})
        else:
            s.execute(text("UPDATE analysis_jobs SET status = 'running', started_at = :now WHERE id = CAST(:id AS uuid)"), {"id": job_id, "now": now})


def job_set_completed(job_id: str) -> None:
    now = datetime.utcnow().isoformat() + "Z" if _is_sqlite() else datetime.utcnow()
    with session_scope() as s:
        from sqlalchemy import text
        if _is_sqlite():
            s.execute(text("UPDATE analysis_jobs SET status = 'completed', finished_at = :now WHERE id = :id"), {"id": job_id, "now": now})
        else:
            s.execute(text("UPDATE analysis_jobs SET status = 'completed', finished_at = :now WHERE id = CAST(:id AS uuid)"), {"id": job_id, "now": now})


def job_set_failed(job_id: str, error_message: str) -> None:
    now = datetime.utcnow().isoformat() + "Z" if _is_sqlite() else datetime.utcnow()
    with session_scope() as s:
        from sqlalchemy import text
        if _is_sqlite():
            s.execute(text("UPDATE analysis_jobs SET status = 'failed', finished_at = :now, error_message = :err WHERE id = :id"), {"id": job_id, "now": now, "err": error_message})
        else:
            s.execute(text("UPDATE analysis_jobs SET status = 'failed', finished_at = :now, error_message = :err WHERE id = CAST(:id AS uuid)"), {"id": job_id, "now": now, "err": error_message})


def job_set_cancelled(job_id: str) -> None:
    now = datetime.utcnow().isoformat() + "Z" if _is_sqlite() else datetime.utcnow()
    with session_scope() as s:
        from sqlalchemy import text
        if _is_sqlite():
            s.execute(text("UPDATE analysis_jobs SET status = 'cancelled', finished_at = :now, error_message = :err WHERE id = :id"), {"id": job_id, "now": now, "err": "Cancelled by user"})
        else:
            s.execute(text("UPDATE analysis_jobs SET status = 'cancelled', finished_at = :now, error_message = :err WHERE id = CAST(:id AS uuid)"), {"id": job_id, "now": now, "err": "Cancelled by user"})


def graph_save(project_id: str, graph: dict) -> None:
    import json
    now = datetime.utcnow().isoformat() + "Z" if _is_sqlite() else datetime.utcnow()
    with session_scope() as s:
        from sqlalchemy import text
        if _is_sqlite():
            s.execute(text("INSERT INTO graphs (project_id, graph, created_at) VALUES (:pid, :graph, :now)"), {"pid": project_id, "graph": json.dumps(graph), "now": now})
        else:
            s.execute(text("INSERT INTO graphs (project_id, graph, created_at) VALUES (CAST(:pid AS uuid), CAST(:graph AS jsonb), :now)"), {"pid": project_id, "graph": json.dumps(graph), "now": now})


def graph_get_latest(project_id: str) -> dict | None:
    import json
    with session_scope() as s:
        from sqlalchemy import text
        if _is_sqlite():
            r = s.execute(text("SELECT graph FROM graphs WHERE project_id = :id ORDER BY created_at DESC LIMIT 1"), {"id": project_id})
        else:
            r = s.execute(text("SELECT graph FROM graphs WHERE project_id = CAST(:id AS uuid) ORDER BY created_at DESC LIMIT 1"), {"id": project_id})
        row = r.fetchone()
    if not row:
        return None
    raw = row[0]
    return raw if isinstance(raw, dict) else json.loads(raw)


def graph_delete_all(project_id: str) -> None:
    with session_scope() as s:
        from sqlalchemy import text
        if _is_sqlite():
            s.execute(text("DELETE FROM graphs WHERE project_id = :id"), {"id": project_id})
        else:
            s.execute(text("DELETE FROM graphs WHERE project_id = CAST(:id AS uuid)"), {"id": project_id})


def checkpoint_save(project_id: str, job_id: str, checkpoint: dict) -> None:
    import json
    now = datetime.utcnow().isoformat() + "Z" if _is_sqlite() else datetime.utcnow()
    with session_scope() as s:
        from sqlalchemy import text
        if _is_sqlite():
            s.execute(text(
                "INSERT INTO project_checkpoints (project_id, job_id, checkpoint, created_at) VALUES (:pid, :jid, :chk, :now)"
            ), {"pid": project_id, "jid": job_id, "chk": json.dumps(checkpoint), "now": now})
        else:
            s.execute(text(
                "INSERT INTO project_checkpoints (project_id, job_id, checkpoint, created_at) VALUES (CAST(:pid AS uuid), CAST(:jid AS uuid), CAST(:chk AS jsonb), :now)"
            ), {"pid": project_id, "jid": job_id, "chk": json.dumps(checkpoint), "now": now})


def checkpoint_get_latest(project_id: str):
    """Devuelve (job_id, checkpoint_dict) o (None, None) si no hay checkpoint."""
    import json
    with session_scope() as s:
        from sqlalchemy import text
        if _is_sqlite():
            r = s.execute(text(
                "SELECT job_id, checkpoint FROM project_checkpoints WHERE project_id = :id ORDER BY created_at DESC LIMIT 1"
            ), {"id": project_id})
        else:
            r = s.execute(text(
                "SELECT job_id, checkpoint FROM project_checkpoints WHERE project_id = CAST(:id AS uuid) ORDER BY created_at DESC LIMIT 1"
            ), {"id": project_id})
        row = r.fetchone()
    if not row:
        return None, None
    raw = row[1]
    chk = raw if isinstance(raw, dict) else json.loads(raw)
    return str(row[0]), chk


def checkpoint_clear(project_id: str) -> None:
    """Borra checkpoints del proyecto (al iniciar análisis de cero o al completar)."""
    with session_scope() as s:
        from sqlalchemy import text
        if _is_sqlite():
            s.execute(text("DELETE FROM project_checkpoints WHERE project_id = :id"), {"id": project_id})
        else:
            s.execute(text("DELETE FROM project_checkpoints WHERE project_id = CAST(:id AS uuid)"), {"id": project_id})


def node_notes_get(project_id: str) -> dict:
    """Devuelve { node_id: [note1, note2, ...], ... } para el proyecto."""
    with session_scope() as s:
        from sqlalchemy import text
        if _is_sqlite():
            r = s.execute(text("SELECT notes FROM project_node_notes WHERE project_id = :id"), {"id": project_id})
        else:
            r = s.execute(text("SELECT notes FROM project_node_notes WHERE project_id = CAST(:id AS uuid)"), {"id": project_id})
        row = r.fetchone()
    if not row:
        return {}
    raw = row[0]
    return raw if isinstance(raw, dict) else json.loads(raw or "{}")


def node_notes_set(project_id: str, notes: dict) -> None:
    """Reemplaza todas las notas del proyecto. notes = { node_id: [note1, ...], ... }."""
    with session_scope() as s:
        from sqlalchemy import text
        payload = json.dumps(notes)
        if _is_sqlite():
            s.execute(text("""
                INSERT INTO project_node_notes (project_id, notes) VALUES (:id, :notes)
                ON CONFLICT(project_id) DO UPDATE SET notes = :notes
            """), {"id": project_id, "notes": payload})
        else:
            s.execute(text("""
                INSERT INTO project_node_notes (project_id, notes) VALUES (CAST(:id AS uuid), CAST(:notes AS jsonb))
                ON CONFLICT(project_id) DO UPDATE SET notes = CAST(:notes AS jsonb)
            """), {"id": project_id, "notes": payload})
