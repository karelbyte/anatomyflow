const getBaseUrl = () => import.meta.env.VITE_API_URL || 'http://localhost:8000'

/** Headers para todas las peticiones (incluye X-API-Key si VITE_API_KEY está definido). */
function getApiHeaders(overrides = {}) {
  const h = { ...overrides }
  const key = import.meta.env.VITE_API_KEY
  if (key) h['X-API-Key'] = key
  return h
}

export async function fetchProjects() {
  const res = await fetch(`${getBaseUrl()}/api/projects`, { headers: getApiHeaders() })
  if (!res.ok) throw new Error('Failed to fetch projects')
  return res.json()
}

export async function createProject({ name, codebase_path, repo_url, repo_branch }) {
  const res = await fetch(`${getBaseUrl()}/api/projects`, {
    method: 'POST',
    headers: getApiHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      name,
      codebase_path: codebase_path || '',
      repo_url: (repo_url || '').trim(),
      repo_branch: (repo_branch || 'main').trim() || 'main',
    }),
  })
  if (!res.ok) {
    const t = await res.text()
    throw new Error(t || 'Failed to create project')
  }
  return res.json()
}

export async function fetchProject(id) {
  const res = await fetch(`${getBaseUrl()}/api/projects/${id}`, { headers: getApiHeaders() })
  if (!res.ok) throw new Error('Project not found')
  return res.json()
}

export async function updateProject(id, { name, codebase_path, excluded_paths, repo_url, repo_branch }) {
  const body = {}
  if (name !== undefined) body.name = name
  if (codebase_path !== undefined) body.codebase_path = codebase_path
  if (excluded_paths !== undefined) body.excluded_paths = excluded_paths
  if (repo_url !== undefined) body.repo_url = repo_url
  if (repo_branch !== undefined) body.repo_branch = repo_branch
  const res = await fetch(`${getBaseUrl()}/api/projects/${id}`, {
    method: 'PATCH',
    headers: getApiHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error('Failed to update project')
  return res.json()
}

export async function deleteProject(id) {
  const res = await fetch(`${getBaseUrl()}/api/projects/${id}`, { method: 'DELETE', headers: getApiHeaders() })
  if (!res.ok) throw new Error('Failed to delete project')
  return res.json()
}

export async function startAnalyze(projectId) {
  const res = await fetch(`${getBaseUrl()}/api/projects/${projectId}/analyze`, {
    method: 'POST',
    headers: getApiHeaders(),
  })
  if (!res.ok) {
    const t = await res.text()
    throw new Error(t || 'Failed to start analysis')
  }
  return res.json()
}

export async function resumeAnalyze(projectId) {
  const res = await fetch(`${getBaseUrl()}/api/projects/${projectId}/analyze/resume`, {
    method: 'POST',
    headers: getApiHeaders(),
  })
  if (!res.ok) {
    const t = await res.text()
    throw new Error(t || 'Failed to resume analysis')
  }
  return res.json()
}

export async function fetchJob(jobId) {
  const res = await fetch(`${getBaseUrl()}/api/jobs/${jobId}`, { headers: getApiHeaders() })
  if (!res.ok) throw new Error('Job not found')
  return res.json()
}

export async function cancelJob(jobId) {
  const res = await fetch(`${getBaseUrl()}/api/jobs/${jobId}/cancel`, { method: 'POST', headers: getApiHeaders() })
  if (!res.ok) {
    const t = await res.text()
    throw new Error(t || 'Failed to stop analysis')
  }
  return res.json()
}

export async function deleteProjectGraph(projectId) {
  const res = await fetch(`${getBaseUrl()}/api/projects/${projectId}/graph`, { method: 'DELETE', headers: getApiHeaders() })
  if (!res.ok) throw new Error('Failed to clear analysis')
  return res.json()
}

export async function fetchProjectGraph(projectId) {
  const res = await fetch(`${getBaseUrl()}/api/projects/${projectId}/graph`, { headers: getApiHeaders() })
  if (!res.ok) throw new Error('No graph yet')
  return res.json()
}

/** Importar grafo en un proyecto (reemplaza el grafo existente). */
export async function importProjectGraph(projectId, graph) {
  const res = await fetch(`${getBaseUrl()}/api/projects/${projectId}/graph`, {
    method: 'PUT',
    headers: getApiHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ nodes: graph.nodes || [], edges: graph.edges || [] }),
  })
  if (!res.ok) {
    const msg = await getApiErrorMessage(res)
    throw new Error(msg)
  }
  return res.json()
}

/** Parsea el cuerpo de error de la API (message, detail o códigos conocidos). */
export async function getApiErrorMessage(res) {
  const text = await res.text()
  try {
    const data = JSON.parse(text)
    if (data.message) return data.message
    const d = data.detail
    if (typeof d === 'string') return d
    if (Array.isArray(d) && d[0]?.msg) return d[0].msg
    if (Array.isArray(d) && typeof d[0] === 'string') return d[0]
  } catch (_) {}
  if (res.status === 404) return 'Archivo o recurso no encontrado.'
  if (res.status === 401) return 'API key inválida o no configurada.'
  if (res.status === 403) return 'Acceso denegado.'
  if (res.status === 429) return 'Demasiadas peticiones. Espera un momento.'
  return text || 'Error de servidor.'
}

/** Notas por nodo del proyecto. Devuelve { notes: { nodeId: string[] } }. */
export async function fetchNodeNotes(projectId) {
  const res = await fetch(`${getBaseUrl()}/api/projects/${projectId}/node-notes`, { headers: getApiHeaders() })
  if (!res.ok) throw new Error('Failed to load notes')
  return res.json()
}

/** Actualiza las notas de un nodo. notes = array de strings. */
export async function updateNodeNotes(projectId, nodeId, notes) {
  const res = await fetch(`${getBaseUrl()}/api/projects/${projectId}/node-notes`, {
    method: 'PATCH',
    headers: getApiHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ node_id: nodeId, notes: Array.isArray(notes) ? notes : [] }),
  })
  if (!res.ok) {
    const msg = await getApiErrorMessage(res)
    throw new Error(msg)
  }
  return res.json()
}

/** Código en tiempo real del nodo (lee del codebase del proyecto). */
export async function fetchNodeCode(projectId, nodeId) {
  const res = await fetch(`${getBaseUrl()}/api/projects/${projectId}/node-code?node_id=${encodeURIComponent(nodeId)}`, { headers: getApiHeaders() })
  if (!res.ok) {
    const msg = await getApiErrorMessage(res)
    throw new Error(msg)
  }
  return res.json()
}

export function getWsAgentUrl() {
  const base = getBaseUrl()
  const ws = base.replace(/^http/, 'ws')
  return `${ws}/ws/agent`
}

/** SSE URL for live "schema_received" when the agent sends the schema */
export function getProjectEventsUrl(projectId) {
  return `${getBaseUrl()}/api/projects/${projectId}/events`
}
/** Browse server folders (empty path = root). Returns { current, parent, entries, root }. */
export async function fetchBrowse(path = '') {
  const url = path ? `${getBaseUrl()}/api/browse?path=${encodeURIComponent(path)}` : `${getBaseUrl()}/api/browse`
  const res = await fetch(url, { headers: getApiHeaders() })
  if (!res.ok) {
    const t = await res.text()
    throw new Error(t || 'Failed to list folder')
  }
  return res.json()
}

/** Project file/folder tree (for selection step) */
export async function fetchProjectTree(projectId) {
  const res = await fetch(`${getBaseUrl()}/api/projects/${projectId}/tree`, { headers: getApiHeaders() })
  if (!res.ok) throw new Error(res.status === 400 ? 'Invalid code path on server. Use an absolute path to an existing folder (e.g. C:\\www\\my-project).' : 'Failed to load tree')
  return res.json()
}

/** URL to start GitHub OAuth for this project (redirects to GitHub, then back to app with token saved) */
export function getGitHubAuthorizeUrl(projectId) {
  const base = getBaseUrl()
  return `${base}/api/auth/github?project_id=${encodeURIComponent(projectId)}`
}

/** Remove GitHub connection for this project */
export async function disconnectProjectGitHub(projectId) {
  const res = await fetch(`${getBaseUrl()}/api/projects/${projectId}/github`, { method: 'DELETE', headers: getApiHeaders() })
  if (!res.ok) throw new Error('Failed to disconnect GitHub')
  return res.json()
}

/** Update cloned repo from GitHub (git fetch + checkout). Use after changes on remote. */
export async function pullProjectFromGitHub(projectId) {
  const res = await fetch(`${getBaseUrl()}/api/projects/${projectId}/github/pull`, { method: 'POST', headers: getApiHeaders() })
  if (!res.ok) {
    const t = await res.text()
    throw new Error(t || 'Failed to update from GitHub')
  }
  return res.json()
}

/** List repos for the project's connected GitHub account */
export async function fetchProjectGitHubRepos(projectId) {
  const res = await fetch(`${getBaseUrl()}/api/projects/${projectId}/github/repos`, { headers: getApiHeaders() })
  if (!res.ok) {
    const t = await res.text()
    throw new Error(t || 'Failed to load repos')
  }
  return res.json()
}

/** List branches for a repo (owner/repo) */
export async function fetchProjectGitHubBranches(projectId, owner, repo) {
  const res = await fetch(`${getBaseUrl()}/api/projects/${projectId}/github/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/branches`, { headers: getApiHeaders() })
  if (!res.ok) {
    const t = await res.text()
    throw new Error(t || 'Failed to load branches')
  }
  return res.json()
}
