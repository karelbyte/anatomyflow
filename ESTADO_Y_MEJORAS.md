# ProjectAnatomy: estado actual y mejoras con impacto

## Progreso de mejoras (actualizado)

| # | Mejora | Estado | Notas |
|---|--------|--------|--------|
| 1 | **Tests** | En curso | Backend: `backend/tests/` con pytest, `uv run pytest tests/ -v`. Falta: tests del analyzer (merge, file_path). |
| 2 | Auth y seguridad | Hecho | BACKEND_API_KEY + X-API-Key, CORS desde FRONTEND_URL, rate limit por IP (RATE_LIMIT_*). Frontend: getApiHeaders() con VITE_API_KEY. |
| 3 | Segundo tipo de proyecto (Next.js) | Hecho | project_types/nextjs.py: pages, api_routes, components; frontend kinds + CODE_NODE_KINDS. |
| 4 | Impacto/huérfanos sin Neo4j | Hecho | GET /api/projects/{id}/impact?node_id=, GET /api/projects/{id}/orphans; cálculo en memoria desde grafo en BD. |
| 5 | Mejor feedback de errores | Hecho | Analyzer: LLM_INVALID_JSON/LLM_ERROR en stderr; backend: mensajes claros y exception_handler con code+message; frontend: getApiErrorMessage, tips en paso 4, mensajes en panel de código. |
| 6 | Export/import y URLs | Hecho | React Router: /, /projects/new, /projects/:id, /projects/:id?step=, /projects/:id/graph, /graph. Export grafo JSON; Import desde archivo; PUT /api/projects/:id/graph para importar grafo. |
| 7 | UX (onboarding, filtros, búsqueda) | Hecho | Onboarding: card desplegable en lista (localStorage para no volver a mostrar). Filtros: clic en leyenda para mostrar/ocultar por tipo. Búsqueda: input por label o file_path, dropdown de resultados e ir al nodo + fitView. |

---

## Lo que ya tenemos hecho (vs. ideas.md y MVP)

### Agente (Go)
- ✅ Binario que se conecta a MySQL/Postgres y extrae el schema desde `information_schema`.
- ✅ Escribe `{database}.json` y opcionalmente envía el schema por WebSocket al backend con `backend_ws_url` + `backend_api_key`.
- ✅ Config por YAML/JSON (driver, connection_string, backend opcional).

### Backend (FastAPI)
- ✅ Proyectos: CRUD, `codebase_path` local o GitHub (repo + rama).
- ✅ GitHub OAuth por proyecto (conectar cuenta, listar repos/ramas, pull para actualizar código).
- ✅ Schema por proyecto (recibido vía WebSocket); notificación en vivo por SSE (`schema_received`).
- ✅ Análisis asíncrono: jobs con log en vivo, reanudar, cancelar; checkpoints en BD.
- ✅ Grafo por proyecto (guardado en BD como JSON; Neo4j opcional para impact/orphans).
- ✅ **Código en tiempo real**: `GET /node-code?node_id=...` usa `file_path` guardado en el grafo o convención Laravel; soporta subcarpetas (ej. `Api/ClientController.php`).
- ✅ Árbol del proyecto y exclusión de rutas (`excluded_paths`).
- ✅ Browse de carpetas del servidor (limitado por `BROWSER_ROOT`).

### Analizador (Python + LLM)
- ✅ Detección de tipo Laravel (composer, Controllers/Models/routes); clasificación controllers/models/routes/views.
- ✅ Prompts por variante (controller, model, routes, views); merge de grafos por `node id`.
- ✅ Múltiples proveedores de IA (Groq, OpenAI, Anthropic, Gemini, DeepSeek, OpenRouter).
- ✅ **Paths reales**: guarda `file_path` en cada nodo (model/controller/view) y `controller_path` + `method_name` en rutas; fallback singular/plural para controladores.
- ✅ Checkpoints cada N archivos y reintentos para fallos; tabla DDL desde schema.

### Frontend (React + Vite + React Flow)
- ✅ Lista de proyectos, crear (local o GitHub), editar, eliminar; “Analysis” y “View graph”.
- ✅ Wizard de 4 pasos: Codebase (local o GitHub + selector repo/rama) → Agent/Schema → Tree (excluir paths) → Run analysis.
- ✅ Grafo con React Flow (nodos por tipo, clusters, mini-mapa, controles).
- ✅ Panel de código lateral: al hacer clic en un nodo se pide el código al backend (path guardado o inferido); se muestra label + **ruta del archivo** + sintaxis resaltada.
- ✅ Highlight de dependencias (upstream/downstream) al seleccionar nodo.
- ✅ Toasts, estados de carga y mensajes de error en flujos críticos.

### Documentación y entorno
- ✅ README por componente (backend, frontend, analyzer, agent, project_types); `ideas.md` con visión y stack.
- ✅ `.env.example` / ejemplos de config; `.gitignore` completo.

---

## Lo que falta o está a medias (actualizado)

| Área | Estado | Impacto |
|------|--------|--------|
| **Tests** | Backend: hay tests en `backend/tests/`. Falta: más cobertura backend, tests del analyzer (merge, file_path, parseo LLM) y del frontend. | Alto: regresiones, refactors y confianza al desplegar. |
| **Auth en la API** | Solo el WebSocket del agente usa `api_key`. El resto de la API es abierta. | Alto si se comparte o se expone en red. |
| **Rate limiting** | No implementado. | Medio: evitar abuso en analyze y node-code. |
| **Impacto / huérfanos** | Dependen de Neo4j; no hay alternativa si no se usa Neo4j. | Medio: la idea de “qué se rompe” está en ideas.md pero no siempre disponible. |
| **Más tipos de proyecto** | Solo Laravel en el analyzer; el contrato para otros stacks está listo. | Alto para ampliar uso (Next.js, otro backend, etc.). |
| **Manejo de errores** | Mensajes genéricos en varios sitios; poco contexto en fallos de LLM o análisis. | Medio: mejor UX y debugging. |
| **i18n** | Textos en inglés y español mezclados. | Bajo a medio según audiencia. |
| **Accesibilidad** | Algo de ARIA en modales; sin revisión completa (focus, teclado, grafo). | Medio para uso profesional/inclusivo. |
| **Export/import** | Solo “Load graph JSON” en el grafo; no hay export/import de proyectos completos. | Medio para compartir o respaldar. |
| **Routing en frontend** | Navegación por estado (`view` + `selectedProjectId`); sin URLs por proyecto/paso. | Bajo: compartir enlace o bookmark. |

---

## Mejoras con más impacto (priorizadas)

### 1. Tests (máximo impacto a medio plazo)
- **Backend**: tests de API (proyectos, graph, analyze, node-code, GitHub pull) con cliente de test de FastAPI; fixtures de BD.
- **Analyzer**: tests unitarios de `merge_graphs`, `_resolve_node_to_file_path` (o equivalente), `to_react_flow`, y de parseo de respuesta del LLM (JSON).
- **Frontend**: tests de componentes clave (ProjectsList, ProjectDetail steps, CodePanel) y, si hay tiempo, un E2E mínimo (crear proyecto → ver grafo).

**Impacto:** Menos bugs, refactors seguros y mejor onboarding de quien toque el código.

### 2. Auth y seguridad básica
- Auth por API key por proyecto (header o query) para endpoints de proyecto/grafo/analyze, manteniendo el flujo actual del agente.
- Opcional: login simple (usuario/contraseña o OAuth) para multi-usuario.
- CORS restringido a `FRONTEND_URL` en producción; documentar y revisar `BROWSER_ROOT` y escape de paths.

**Impacto:** Poder desplegar en entornos compartidos o en internet sin dejar todo abierto.

### 3. Segundo tipo de proyecto en el analyzer
- Implementar un segundo `project_type` (por ejemplo **Next.js** o **API en Node/Express**): detección, clasificación de archivos y prompts que devuelvan nodos/edges con `file_path`.
- Reutilizar merge, layout y salida React Flow.

**Impacto:** El producto deja de ser “solo Laravel” y valida que el diseño escala a más stacks.

### 4. Impacto y huérfanos sin depender de Neo4j
- Calcular “impacto” (downstream) y “huérfanos” a partir del grafo en BD (JSON): recorrer nodos y aristas en memoria.
- Exponer endpoints o datos para el frontend (resaltar qué nodos se ven afectados al elegir uno; marcar huérfanos).
- Dejar Neo4j como opción de mejora futura, no como requisito.

**Impacto:** La idea de “qué se rompe si cambio esto” funciona para todos los que usen el grafo en BD.

### 5. Mejor feedback de errores
- En el analyzer: mensajes claros cuando falla el LLM (rate limit, JSON inválido, timeout) y en el log del job.
- En el frontend: mostrar en el paso 4 un resumen del último error del análisis; en el panel de código, mensajes específicos (archivo no encontrado, sin path, etc.).
- En la API: respuestas de error con código y mensaje consistentes (ej. 424 “Analysis failed” con detalle).

**Impacto:** Menos tiempo perdido intentando adivinar por qué falló un análisis o la carga de código.

### 6. Export/import y URLs
- Export: descargar grafo + metadata del proyecto (o solo grafo) como JSON.
- Import: crear proyecto desde ese JSON (o “clonar” configuración).
- Opcional: rutas con React Router (`/projects/:id`, `/projects/:id/step/:step`, `/graph`) para poder compartir enlaces.

**Impacto:** Respaldo, compartir con el equipo y mejor navegación.

### 7. Pequeñas mejoras de producto
- **Onboarding**: tooltip o paso 0 “Qué hace ProjectAnatomy” en la lista de proyectos o en el primer paso.
- **Filtros en el grafo**: por tipo de nodo (solo tablas, solo controladores, etc.) para proyectos grandes.
- **Búsqueda en el grafo**: por label o `file_path` para ir al nodo y abrir el código.
- **Documentar** en el README principal: “Requisitos (Agent + Backend + Analyzer + Frontend)”, “Flujo completo en 5 minutos” y enlace a este documento.

**Impacto:** Más adopción y uso en proyectos reales sin tocar la arquitectura.

---

## Resumen en una frase

**Hecho:** Pipeline completo Agent (schema) → Analyzer (Laravel + Next.js, LLM, paths reales) → Backend (proyectos, GitHub, análisis, node-code, auth, CORS, rate limit, impacto/huérfanos en memoria) → Frontend (wizard 4 pasos, grafo, código en tiempo real, React Router, export/import grafo, onboarding, filtros, búsqueda).  
**Falta:** Completar tests (analyzer, frontend, más backend), export/import de proyecto completo, opcionalmente i18n, accesibilidad y README raíz.  
**Próximo paso recomendado:** Tests del analyzer y del frontend; luego export/import de proyecto completo si hace falta.
