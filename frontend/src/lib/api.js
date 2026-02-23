const getBaseUrl = () => import.meta.env.VITE_API_URL || 'http://localhost:8000'

export async function fetchProjects() {
  const res = await fetch(`${getBaseUrl()}/api/projects`)
  if (!res.ok) throw new Error('Failed to fetch projects')
  return res.json()
}

export async function createProject({ name, codebase_path, repo_url, repo_branch }) {
  const res = await fetch(`${getBaseUrl()}/api/projects`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
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
  const res = await fetch(`${getBaseUrl()}/api/projects/${id}`)
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
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error('Failed to update project')
  return res.json()
}

export async function deleteProject(id) {
  const res = await fetch(`${getBaseUrl()}/api/projects/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error('Failed to delete project')
  return res.json()
}

export async function startAnalyze(projectId) {
  const res = await fetch(`${getBaseUrl()}/api/projects/${projectId}/analyze`, {
    method: 'POST',
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
  })
  if (!res.ok) {
    const t = await res.text()
    throw new Error(t || 'Failed to resume analysis')
  }
  return res.json()
}

export async function fetchJob(jobId) {
  const res = await fetch(`${getBaseUrl()}/api/jobs/${jobId}`)
  if (!res.ok) throw new Error('Job not found')
  return res.json()
}

export async function cancelJob(jobId) {
  const res = await fetch(`${getBaseUrl()}/api/jobs/${jobId}/cancel`, { method: 'POST' })
  if (!res.ok) {
    const t = await res.text()
    throw new Error(t || 'Failed to stop analysis')
  }
  return res.json()
}

export async function deleteProjectGraph(projectId) {
  const res = await fetch(`${getBaseUrl()}/api/projects/${projectId}/graph`, { method: 'DELETE' })
  if (!res.ok) throw new Error('Failed to clear analysis')
  return res.json()
}

export async function fetchProjectGraph(projectId) {
  const res = await fetch(`${getBaseUrl()}/api/projects/${projectId}/graph`)
  if (!res.ok) throw new Error('No graph yet')
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
  const res = await fetch(url)
  if (!res.ok) {
    const t = await res.text()
    throw new Error(t || 'Failed to list folder')
  }
  return res.json()
}

/** Project file/folder tree (for selection step) */
export async function fetchProjectTree(projectId) {
  const res = await fetch(`${getBaseUrl()}/api/projects/${projectId}/tree`)
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
  const res = await fetch(`${getBaseUrl()}/api/projects/${projectId}/github`, { method: 'DELETE' })
  if (!res.ok) throw new Error('Failed to disconnect GitHub')
  return res.json()
}

/** List repos for the project's connected GitHub account */
export async function fetchProjectGitHubRepos(projectId) {
  const res = await fetch(`${getBaseUrl()}/api/projects/${projectId}/github/repos`)
  if (!res.ok) {
    const t = await res.text()
    throw new Error(t || 'Failed to load repos')
  }
  return res.json()
}

/** List branches for a repo (owner/repo) */
export async function fetchProjectGitHubBranches(projectId, owner, repo) {
  const res = await fetch(`${getBaseUrl()}/api/projects/${projectId}/github/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/branches`)
  if (!res.ok) {
    const t = await res.text()
    throw new Error(t || 'Failed to load branches')
  }
  return res.json()
}
