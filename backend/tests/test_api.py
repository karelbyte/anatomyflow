"""
Tests de la API del backend: health, proyectos (CRUD), grafo por proyecto.
"""
import pytest
from fastapi.testclient import TestClient

# Importar app después de que conftest haya fijado DATABASE_URL
from main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "neo4j" in data


def test_list_projects_empty():
    r = client.get("/api/projects")
    assert r.status_code == 200
    assert r.json() == []


def test_create_project():
    r = client.post(
        "/api/projects",
        json={"name": "Test Project", "codebase_path": "/tmp/code", "repo_url": "", "repo_branch": "main"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "Test Project"
    assert data["codebase_path"] == "/tmp/code"
    assert "id" in data
    assert "agent_api_key" in data
    assert len(data["agent_api_key"]) >= 32


def test_create_and_get_project():
    r = client.post("/api/projects", json={"name": "Get Me", "codebase_path": "", "repo_url": "", "repo_branch": "main"})
    assert r.status_code == 200
    pid = r.json()["id"]
    r2 = client.get(f"/api/projects/{pid}")
    assert r2.status_code == 200
    assert r2.json()["name"] == "Get Me"


def test_get_project_404():
    r = client.get("/api/projects/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_update_project():
    r = client.post("/api/projects", json={"name": "Original", "codebase_path": "", "repo_url": "", "repo_branch": "main"})
    pid = r.json()["id"]
    r2 = client.patch(f"/api/projects/{pid}", json={"name": "Updated"})
    assert r2.status_code == 200
    r3 = client.get(f"/api/projects/{pid}")
    assert r3.json()["name"] == "Updated"


def test_delete_project():
    r = client.post("/api/projects", json={"name": "To Delete", "codebase_path": "", "repo_url": "", "repo_branch": "main"})
    pid = r.json()["id"]
    r2 = client.delete(f"/api/projects/{pid}")
    assert r2.status_code == 200
    r3 = client.get(f"/api/projects/{pid}")
    assert r3.status_code == 404


def test_get_graph_404():
    r = client.post("/api/projects", json={"name": "No Graph", "codebase_path": "", "repo_url": "", "repo_branch": "main"})
    pid = r.json()["id"]
    r2 = client.get(f"/api/projects/{pid}/graph")
    assert r2.status_code == 404


def test_save_and_get_graph():
    r = client.post("/api/projects", json={"name": "With Graph", "codebase_path": "", "repo_url": "", "repo_branch": "main"})
    pid = r.json()["id"]
    graph = {"nodes": [{"id": "n1", "type": "default", "position": {"x": 0, "y": 0}, "data": {"label": "A", "kind": "model"}}], "edges": []}
    # El grafo se guarda vía el job de análisis en producción; aquí usamos db directamente para no ejecutar el analizador
    import db
    db.graph_save(pid, graph)
    r2 = client.get(f"/api/projects/{pid}/graph")
    assert r2.status_code == 200
    data = r2.json()
    assert "nodes" in data
    assert len(data["nodes"]) == 1
    assert data["nodes"][0]["id"] == "n1"
