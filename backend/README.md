# Backend ProjectAnatomy

API para recibir y servir el esquema de base de datos y el grafo (formato React Flow). Opcionalmente persiste el grafo en **Neo4j** para consultas (impacto, huérfanos) y persistencia.

## Uso

Con **uv** (recomendado):

```bash
cd backend
uv sync
uv run uvicorn main:app --reload --port 8000
```

Con pip:

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Variables de entorno

Copia `env.example` a **`.env`** en la carpeta **backend**. Toda la configuración (Postgres y Neo4j) se lee desde ese archivo.

**Postgres** (proyectos, schemas, jobs, grafos):

| Variable        | Descripción                    |
|-----------------|--------------------------------|
| `DATABASE_URL`  | URL de conexión, ej. `postgresql://user:pass@localhost:5432/anatomydb` |

**Neo4j** (opcional; si no se configura, el grafo solo se guarda en Postgres):

| Variable         | Descripción                    | Por defecto    |
|------------------|--------------------------------|----------------|
| `NEO4J_URI`      | URI del servidor Neo4j         | `bolt://localhost:7687` |
| `NEO4J_USER`     | Usuario Neo4j                  | `neo4j`        |
| `NEO4J_PASSWORD` | Contraseña Neo4j               | (requerido)    |
| `NEO4J_DATABASE` | Nombre de la base de datos Neo4j (4+) | `neo4j` |

**Comprobar conexión a Neo4j** (usa el `.env` del backend):

```bash
cd backend
python scripts/test_neo4j_connection.py
# o: uv run python scripts/test_neo4j_connection.py
```

Con Neo4j configurado: al hacer **POST /api/graph** el grafo se escribe en Neo4j (nodos `AnatomyNode`, relaciones `RELATES_TO`). **GET /api/graph** devuelve el grafo leyendo desde Neo4j.

## Endpoints

- **POST /api/graph** — Body: `{ "schema": {...}, "graph": { "nodes": [], "edges": [] } }`. Guarda en memoria y, si hay Neo4j, persiste ahí.
- **GET /api/graph** — Devuelve `{ "schema": ..., "graph": ... }`. Si hay Neo4j, el grafo sale de Neo4j.
- **GET /api/health** — Health check. Incluye `"neo4j": true/false` según conectividad.
- **GET /api/graph/impact?node_id=table:orders** — *(Requiere Neo4j)*. Devuelve `upstream` (de quién depende) y `downstream` (quién depende de él).
- **GET /api/graph/orphans** — *(Requiere Neo4j)*. Devuelve lista de ids de nodos sin relaciones.

## Enviar grafo desde el analizador

Tras generar `schema.graph.json` con el analizador:

```bash
curl -X POST http://localhost:8000/api/graph \
  -H "Content-Type: application/json" \
  -d "{\"graph\": $(cat ruta/al/schema.graph.json), \"schema\": $(cat ruta/al/schema.json)}"
```

El frontend puede cargar desde `http://localhost:8000/api/graph` (GET) y usar `response.graph` como grafo.

## Neo4j

1. Instala Neo4j (Desktop, Docker o Aura) y crea una base de datos.
2. Define `NEO4J_URI`, `NEO4J_USER` y `NEO4J_PASSWORD` en el entorno o en `.env`.
3. Al hacer POST del grafo, los nodos se guardan como `(:AnatomyNode {id, label, kind, code, orphan, pos_x, pos_y})` y las aristas como `(a)-[:RELATES_TO {relation}]->(b)`.
4. Puedes usar los endpoints `/api/graph/impact` y `/api/graph/orphans` para consultas sobre el grafo.

## WSS (futuro)

Para que el agente Go envíe el schema por WebSocket: añadir en este backend un endpoint `/ws` que acepte conexiones, reciba el JSON del schema y lo guarde; el agente Go tendría que abrir un cliente WebSocket y enviar el schema tras generarlo.
