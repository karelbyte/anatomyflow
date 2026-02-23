import { useCallback, useEffect, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import { FiArrowLeft, FiCheck, FiChevronLeft, FiChevronRight, FiCopy, FiEdit2, FiEye, FiFolder, FiFolderPlus, FiGitBranch, FiPlay, FiPlayCircle, FiRefreshCw, FiSave, FiStopCircle, FiTrash2, FiX } from 'react-icons/fi'
import { Button, Text } from '../components/atoms'
import {
  fetchProject,
  startAnalyze,
  resumeAnalyze,
  fetchJob,
  fetchProjectGraph,
  fetchProjectTree,
  updateProject,
  getWsAgentUrl,
  getProjectEventsUrl,
  getGitHubAuthorizeUrl,
  disconnectProjectGitHub,
  fetchProjectGitHubRepos,
  fetchProjectGitHubBranches,
  fetchBrowse,
  cancelJob,
  deleteProjectGraph,
} from '../lib/api'

const POLL_MS = 2500
const STEPS = [
  { id: 1, label: 'Codebase' },
  { id: 2, label: 'Agent / Schema' },
  { id: 3, label: 'Project tree' },
  { id: 4, label: 'Analysis' },
]

function TreeNode({ node, excludedPaths, onToggle, basePath, isRoot, expandedPaths, onToggleExpand }) {
  const path = node.path === '.' ? null : (basePath ? basePath + '/' + node.path : node.path)
  const expandKey = isRoot ? '.' : (path ?? '.')
  const isDir = node.type === 'dir'
  const hasChildren = node.children && node.children.length > 0
  const isExpanded = expandedPaths.has(expandKey)
  const isExcluded = path != null && excludedPaths.some((ex) => path === ex || path.startsWith(ex + '/'))
  const isChecked = path == null || !isExcluded

  const handleChange = () => {
    if (path == null) return
    onToggle(path, isChecked)
  }

  const handleExpandClick = (e) => {
    e.preventDefault()
    e.stopPropagation()
    if (isDir) onToggleExpand(expandKey)
  }

  return (
    <div className={isRoot ? '' : 'pl-4 border-l border-zinc-600 ml-1'}>
      <div className="flex items-center gap-1 py-0.5 rounded px-1 -ml-1 group">
        {isDir && hasChildren ? (
          <button
            type="button"
            onClick={handleExpandClick}
            className="flex-shrink-0 w-4 h-4 flex items-center justify-center rounded hover:bg-zinc-700 text-zinc-400 hover:text-zinc-200 transition-transform"
            aria-expanded={isExpanded}
            title={isExpanded ? 'Collapse' : 'Expand'}
          >
            <FiChevronRight className={`w-4 h-4 transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
          </button>
        ) : (
          <span className="w-4 inline-block flex-shrink-0" />
        )}
        <label className={`flex items-center gap-2 flex-1 min-w-0 ${path != null ? 'cursor-pointer hover:bg-zinc-800/50' : ''}`}>
          {path != null ? (
            <input
              type="checkbox"
              checked={isChecked}
              onChange={handleChange}
              className="rounded border-zinc-500 bg-zinc-800 text-sky-500 flex-shrink-0"
            />
          ) : (
            <span className="w-4 inline-block flex-shrink-0" />
          )}
          <span className="text-zinc-400 select-none flex-shrink-0">{isDir ? '📁' : '📄'}</span>
          <Text variant="body" className="font-mono text-sm truncate">
            {node.name}
          </Text>
        </label>
      </div>
      {hasChildren && isExpanded &&
        node.children.map((child) => (
          <TreeNode
            key={child.path}
            node={child}
            excludedPaths={excludedPaths}
            onToggle={onToggle}
            basePath={path ?? ''}
            isRoot={false}
            expandedPaths={expandedPaths}
            onToggleExpand={onToggleExpand}
          />
        ))}
    </div>
  )
}

export default function ProjectDetail({ projectId, onBack, onOpenGraph }) {
  const [project, setProject] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [step, setStep] = useState(1)
  const [tree, setTree] = useState(null)
  const [treeLoading, setTreeLoading] = useState(false)
  const [treeError, setTreeError] = useState(null)
  const [excludedPaths, setExcludedPaths] = useState([])
  const [expandedPaths, setExpandedPaths] = useState(() => new Set(['.']))
  const [savingPaths, setSavingPaths] = useState(false)
  const [step3Saved, setStep3Saved] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const [analyzeError, setAnalyzeError] = useState(null)
  const [jobId, setJobId] = useState(null)
  const [jobLog, setJobLog] = useState('')
  const eventSourceRef = useRef(null)
  const [editOpen, setEditOpen] = useState(false)
  const [editName, setEditName] = useState('')
  const [editCodebasePath, setEditCodebasePath] = useState('')
  const [editRepoUrl, setEditRepoUrl] = useState('')
  const [editRepoBranch, setEditRepoBranch] = useState('main')
  const [editSaving, setEditSaving] = useState(false)
  const [browseOpen, setBrowseOpen] = useState(false)
  const [browseCurrent, setBrowseCurrent] = useState('')
  const [browseParent, setBrowseParent] = useState(null)
  const [browseEntries, setBrowseEntries] = useState([])
  const [browseLoading, setBrowseLoading] = useState(false)
  const [browseError, setBrowseError] = useState(null)
  const [clearGraphConfirm, setClearGraphConfirm] = useState(false)
  const [clearingGraph, setClearingGraph] = useState(false)
  const [cancellingJob, setCancellingJob] = useState(false)
  const [githubRepos, setGithubRepos] = useState([])
  const [githubBranches, setGithubBranches] = useState([])
  const [loadingRepos, setLoadingRepos] = useState(false)
  const [loadingBranches, setLoadingBranches] = useState(false)
  const [selectRepoFullName, setSelectRepoFullName] = useState('')
  const [selectBranchName, setSelectBranchName] = useState('')
  const [savingRepoSelection, setSavingRepoSelection] = useState(false)
  const [showRepoSelector, setShowRepoSelector] = useState(false)

  const load = useCallback(() => {
    if (!projectId) return
    setLoading(true)
    fetchProject(projectId)
      .then((p) => {
        setProject(p)
        setExcludedPaths(p.excluded_paths || [])
      })
      .catch((e) => {
        setError(e.message)
        toast.error(e.message || 'Failed to load project')
      })
      .finally(() => setLoading(false))
  }, [projectId])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (!projectId || !project) return
    const url = getProjectEventsUrl(projectId)
    const es = new EventSource(url)
    eventSourceRef.current = es
    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data)
        if (data.event === 'schema_received') load()
      } catch {}
    }
    es.onerror = () => {
      es.close()
      eventSourceRef.current = null
    }
    return () => {
      es.close()
      eventSourceRef.current = null
    }
  }, [projectId, project?.id, load])

  useEffect(() => {
    if (!projectId || project?.has_schema) return
    const t = setInterval(load, POLL_MS)
    return () => clearInterval(t)
  }, [projectId, project?.has_schema, load])

  useEffect(() => {
    if (!jobId) return
    const tick = async () => {
      try {
        const job = await fetchJob(jobId)
        setJobLog(job.log || '')
        if (job.status === 'completed') {
          setJobId(null)
          setAnalyzing(false)
          toast.success('Analysis completed')
          const graph = await fetchProjectGraph(projectId)
          onOpenGraph(graph)
        } else if (job.status === 'failed') {
          setJobId(null)
          setAnalyzing(false)
          const msg = job.error_message || 'Analysis failed'
          setAnalyzeError(msg)
          toast.error(msg)
        } else if (job.status === 'cancelled') {
          setJobId(null)
          setAnalyzing(false)
          load()
          toast('Analysis stopped. You can resume later.', { icon: '⏹' })
        }
      } catch {}
    }
    tick()
    const t = setInterval(tick, 2000)
    return () => clearInterval(t)
  }, [jobId, projectId, onOpenGraph, load])

  const loadTree = useCallback(() => {
    if (!projectId) return
    setTreeLoading(true)
    setTreeError(null)
    fetchProjectTree(projectId)
      .then((data) => {
        setTree(data.root)
        setExcludedPaths(data.excluded_paths || [])
        setExpandedPaths(new Set(['.']))
      })
      .catch((e) => {
        setTreeError(e.message)
        toast.error(e.message || 'Failed to load tree')
      })
      .finally(() => setTreeLoading(false))
  }, [projectId])

  const handleToggleExpand = useCallback((expandKey) => {
    setExpandedPaths((prev) => {
      const next = new Set(prev)
      if (next.has(expandKey)) next.delete(expandKey)
      else next.add(expandKey)
      return next
    })
  }, [])

  useEffect(() => {
    if (step === 3 && (project?.codebase_path || project?.repo_url) && !tree && !treeLoading) loadTree()
  }, [step, project?.codebase_path, project?.repo_url, tree, treeLoading, loadTree])

  const needRepoSelector = step === 1 && project?.has_github_connected && (!project.repo_url || showRepoSelector)
  useEffect(() => {
    if (!needRepoSelector || !projectId) return
    setLoadingRepos(true)
    fetchProjectGitHubRepos(projectId)
      .then((list) => setGithubRepos(list || []))
      .catch((e) => {
        toast.error(e.message || 'Failed to load repositories')
        setGithubRepos([])
      })
      .finally(() => setLoadingRepos(false))
  }, [needRepoSelector, projectId])

  useEffect(() => {
    if (!selectRepoFullName || !projectId) {
      setGithubBranches([])
      return
    }
    const [owner, repo] = selectRepoFullName.split('/')
    if (!owner || !repo) return
    setLoadingBranches(true)
    fetchProjectGitHubBranches(projectId, owner, repo)
      .then((list) => {
        setGithubBranches(list || [])
        setSelectBranchName((prev) => {
          const current = project?.repo_url === selectRepoFullName ? (project.repo_branch || 'main') : null
          if (current && list?.some((b) => b.name === current)) return current
          if (list?.length && (!prev || !list.some((b) => b.name === prev))) return list[0].name
          return prev
        })
      })
      .catch((e) => {
        toast.error(e.message || 'Failed to load branches')
        setGithubBranches([])
      })
      .finally(() => setLoadingBranches(false))
  }, [selectRepoFullName, projectId, project?.repo_url, project?.repo_branch])

  const handleTogglePath = useCallback((path, exclude) => {
    setExcludedPaths((prev) => {
      if (exclude) return prev.includes(path) ? prev : [...prev, path]
      return prev.filter((p) => p !== path && !p.startsWith(path + '/'))
    })
  }, [])

  const handleSaveExcluded = useCallback(() => {
    if (!projectId) return
    setSavingPaths(true)
    updateProject(projectId, { excluded_paths: excludedPaths })
      .then((p) => {
        setProject(p)
        setExcludedPaths(p.excluded_paths || [])
        setStep3Saved(true)
        toast.success('Selection saved')
      })
      .catch(() => {
        setTreeError('Failed to save')
        toast.error('Failed to save selection')
      })
      .finally(() => setSavingPaths(false))
  }, [projectId, excludedPaths])

  const handleRunAnalysis = useCallback(() => {
    setAnalyzeError(null)
    setJobLog('')
    setAnalyzing(true)
    toast.loading('Starting analysis…', { id: 'analyze' })
    startAnalyze(projectId)
      .then(({ job_id }) => {
        setJobId(job_id)
        toast.success('Analysis started', { id: 'analyze' })
      })
      .catch((e) => {
        setAnalyzing(false)
        setAnalyzeError(e.message)
        toast.error(e.message || 'Failed to start analysis', { id: 'analyze' })
      })
  }, [projectId])

  const handleResumeAnalysis = useCallback(() => {
    setAnalyzeError(null)
    setJobLog('')
    setAnalyzing(true)
    toast.loading('Resuming analysis…', { id: 'analyze-resume' })
    resumeAnalyze(projectId)
      .then(({ job_id }) => {
        setJobId(job_id)
        toast.success('Analysis resumed', { id: 'analyze-resume' })
      })
      .catch((e) => {
        setAnalyzing(false)
        setAnalyzeError(e.message)
        toast.error(e.message || 'No se pudo reanudar', { id: 'analyze-resume' })
      })
  }, [projectId])

  const handleCopy = useCallback((text) => {
    navigator.clipboard.writeText(text).then(() => toast.success('Copied to clipboard')).catch(() => toast.error('Copy failed'))
  }, [])

  const loadBrowse = useCallback(async (path) => {
    setBrowseLoading(true)
    setBrowseError(null)
    try {
      const data = await fetchBrowse(path)
      setBrowseCurrent(data.current)
      setBrowseParent(data.parent ?? null)
      setBrowseEntries(data.entries ?? [])
    } catch (e) {
      setBrowseError(e.message || 'Error al listar')
      setBrowseEntries([])
    } finally {
      setBrowseLoading(false)
    }
  }, [])

  const openEdit = useCallback(() => {
    setEditName(project?.name ?? '')
    setEditCodebasePath(project?.codebase_path ?? '')
    setEditRepoUrl(project?.repo_url ?? '')
    setEditRepoBranch(project?.repo_branch ?? 'main')
    setEditOpen(true)
  }, [project])

  const openBrowseFromEdit = useCallback(() => {
    setBrowseOpen(true)
    setBrowseError(null)
    loadBrowse('')
  }, [loadBrowse])

  const handleSelectFolderInEdit = useCallback((path) => {
    setEditCodebasePath(path)
    setBrowseOpen(false)
  }, [])

  const handleSaveEdit = useCallback(() => {
    if (!projectId) return
    setEditSaving(true)
    updateProject(projectId, {
      name: editName.trim(),
      codebase_path: editCodebasePath.trim(),
      repo_url: editRepoUrl.trim(),
      repo_branch: (editRepoBranch || 'main').trim() || 'main',
    })
      .then((p) => {
        setProject(p)
        setEditOpen(false)
        toast.success('Project updated')
      })
      .catch((e) => {
        toast.error(e.message || 'Failed to save')
      })
      .finally(() => setEditSaving(false))
  }, [projectId, editName, editCodebasePath, editRepoUrl, editRepoBranch])

  const handleCancelAnalysis = useCallback(() => {
    if (!jobId) return
    setCancellingJob(true)
    cancelJob(jobId)
      .then(() => {
        setJobId(null)
        setAnalyzing(false)
        toast.success('Analysis stopped')
      })
      .catch((e) => {
        toast.error(e.message || 'Failed to stop')
      })
      .finally(() => setCancellingJob(false))
  }, [jobId])

  const handleClearGraph = useCallback(() => {
    if (!projectId) return
    setClearingGraph(true)
    deleteProjectGraph(projectId)
      .then(() => {
        setClearGraphConfirm(false)
        load()
        toast.success('Analysis cleared. You can run a new one.')
      })
      .catch((e) => {
        toast.error(e.message || 'Failed to clear')
      })
      .finally(() => setClearingGraph(false))
  }, [projectId, load])

  const step1Done = !!(project?.codebase_path?.trim() || project?.repo_url?.trim())
  const step2Done = !!project?.has_schema
  const step3Done = !!step3Saved

  const canGoToStep = useCallback((stepId) => {
    if (stepId === 1) return true
    if (stepId === 2) return step1Done
    if (stepId === 3) return step2Done
    if (stepId === 4) return step3Done
    return false
  }, [step1Done, step2Done, step3Done])

  const goToStep = useCallback((next) => {
    if (next < 1 || next > 4) return
    if (next > step && !canGoToStep(next)) return
    setStep(next)
  }, [step, canGoToStep])

  if (loading && !project) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <Text variant="muted">Loading…</Text>
      </div>
    )
  }
  if (error || !project) {
    return (
      <div className="max-w-2xl mx-auto p-6">
        <Text variant="danger">{error || 'Project not found'}</Text>
        <Button variant="secondary" className="mt-4 inline-flex items-center gap-2" onClick={onBack}><FiArrowLeft className="w-4 h-4" /> Back</Button>
      </div>
    )
  }

  return (
    <div className="max-w-3xl mx-auto p-6">
      <div className="flex items-center gap-4 mb-6 flex-wrap">
        <Button variant="ghost" onClick={onBack} className="inline-flex items-center gap-2"><FiArrowLeft className="w-4 h-4" /> Back</Button>
        <Text as="h1" variant="title" className="flex-1 min-w-0 truncate">{project.name}</Text>
        <Button variant="secondary" onClick={openEdit} className="inline-flex items-center gap-2" title="Edit name and path"><FiEdit2 className="w-4 h-4" /> Edit</Button>
      </div>

      {/* Edit project modal */}
      {editOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60" role="dialog" aria-modal="true" aria-labelledby="edit-title">
          <div className="bg-zinc-800 border border-zinc-600 rounded-lg shadow-xl max-w-lg w-full">
            <div className="p-4 border-b border-zinc-600 flex items-center justify-between">
              <Text as="h2" id="edit-title" variant="strong">Edit project</Text>
              <Button variant="ghost" onClick={() => setEditOpen(false)} className="text-zinc-400"><FiX className="w-5 h-5" /></Button>
            </div>
            <div className="p-4 space-y-4">
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">Name</label>
                <input
                  type="text"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="w-full px-3 py-2 rounded bg-zinc-900 border border-zinc-600 text-zinc-100"
                  placeholder="Project name"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">Local path (server)</label>
                <input
                  type="text"
                  value={editCodebasePath}
                  onChange={(e) => setEditCodebasePath(e.target.value)}
                  className="w-full px-3 py-2 rounded bg-zinc-900 border border-zinc-600 text-zinc-100"
                  placeholder="C:\www\mi-proyecto or leave empty if using GitHub"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">GitHub repo (optional)</label>
                <input
                  type="text"
                  value={editRepoUrl}
                  onChange={(e) => setEditRepoUrl(e.target.value)}
                  className="w-full px-3 py-2 rounded bg-zinc-900 border border-zinc-600 text-zinc-100 mb-2"
                  placeholder="https://github.com/user/repo or user/repo"
                />
                <label className="block text-xs text-zinc-500 mb-1">Branch</label>
                <input
                  type="text"
                  value={editRepoBranch}
                  onChange={(e) => setEditRepoBranch(e.target.value)}
                  className="w-full max-w-[12rem] px-3 py-2 rounded bg-zinc-900 border border-zinc-600 text-zinc-100"
                  placeholder="main"
                />
              </div>
            </div>
            <div className="p-4 border-t border-zinc-600 flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setEditOpen(false)}>Cancel</Button>
              <Button variant="primary" onClick={handleSaveEdit} disabled={editSaving || !editName.trim()} className="inline-flex items-center gap-2">{editSaving ? 'Saving…' : 'Save'}</Button>
            </div>
          </div>
        </div>
      )}

      {/* Browse folder modal (from Edit) */}
      {browseOpen && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/60" role="dialog" aria-modal="true" aria-labelledby="browse-title">
          <div className="bg-zinc-800 border border-zinc-600 rounded-lg shadow-xl max-w-lg w-full max-h-[80vh] flex flex-col">
            <div className="p-4 border-b border-zinc-600 flex items-center justify-between">
              <Text as="h2" id="browse-title" variant="strong" className="flex items-center gap-2"><FiFolder className="w-5 h-5" /> Choose folder</Text>
              <Button variant="ghost" onClick={() => setBrowseOpen(false)} className="text-zinc-400"><FiX className="w-5 h-5" /></Button>
            </div>
            <div className="p-4 border-b border-zinc-600 bg-zinc-900/50 min-h-0">
              <p className="text-xs text-zinc-500 truncate mb-2" title={browseCurrent}>{browseCurrent || '…'}</p>
              {browseError && <Text variant="danger" className="text-sm mb-2">{browseError}</Text>}
              {browseLoading ? (
                <Text variant="muted">Loading…</Text>
              ) : (
                <div className="space-y-1 max-h-64 overflow-y-auto">
                  {browseParent !== null && (
                    <button type="button" onClick={() => loadBrowse(browseParent)} className="w-full flex items-center gap-2 px-3 py-2 rounded text-left text-zinc-400 hover:bg-zinc-700">
                      <FiFolder className="w-4 h-4" /> ..
                    </button>
                  )}
                  {browseEntries.map((entry) => (
                    <button key={entry.path} type="button" onClick={() => loadBrowse(entry.path)} className="w-full flex items-center gap-2 px-3 py-2 rounded text-left text-zinc-200 hover:bg-zinc-700">
                      <FiChevronRight className="w-4 h-4 text-zinc-500" /> <FiFolder className="w-4 h-4" /> {entry.name}
                    </button>
                  ))}
                  {!browseLoading && browseEntries.length === 0 && browseParent === null && <Text variant="muted">No folders.</Text>}
                </div>
              )}
            </div>
            <div className="p-4 flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setBrowseOpen(false)}>Cancel</Button>
              <Button variant="primary" onClick={() => handleSelectFolderInEdit(browseCurrent)} disabled={browseLoading} className="inline-flex items-center gap-2"><FiFolderPlus className="w-4 h-4" /> Use this folder</Button>
            </div>
          </div>
        </div>
      )}

      {/* Stepper – only allow navigation to steps that are unlocked */}
      <nav className="flex items-center gap-1 mb-8 p-2 rounded-lg bg-zinc-800/50 border border-zinc-600">
        {STEPS.map((s, i) => (
          <div key={s.id} className="flex items-center flex-1 min-w-0">
            <button
              type="button"
              onClick={() => canGoToStep(s.id) && setStep(s.id)}
              disabled={!canGoToStep(s.id)}
              className={`flex items-center gap-2 rounded px-2 py-1.5 text-xs font-medium transition-colors ${
                !canGoToStep(s.id) ? 'cursor-not-allowed opacity-50 text-zinc-500' : 'cursor-pointer'
              } ${step === s.id ? 'bg-sky-600/30 text-sky-300' : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-700/50'}`}
            >
              <span className="flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center bg-zinc-700 text-zinc-300 text-xs">
                {s.id}
              </span>
              <span className="truncate">{s.label}</span>
            </button>
            {i < STEPS.length - 1 && <span className="text-zinc-600 mx-0.5">›</span>}
          </div>
        ))}
      </nav>

      {/* Step 1 – Codebase */}
      {step === 1 && (
        <section className="rounded-lg border border-zinc-600 bg-zinc-800/50 p-4">
          <Text as="h2" variant="strong" className="block mb-2">Step 1 – Codebase</Text>
          <Text variant="muted" className="block mb-1">Code source</Text>

          {project.has_github_connected && (!project.repo_url || showRepoSelector) ? (
            <div className="space-y-3">
              <p className="flex items-center gap-2 text-sm text-emerald-400">
                <FiCheck className="w-4 h-4 flex-shrink-0" /> GitHub account connected
              </p>
              <div>
                <label className="block text-xs text-zinc-500 mb-1">Repository</label>
                {loadingRepos ? (
                  <Text variant="muted" className="text-sm">Loading repositories…</Text>
                ) : (
                  <select
                    value={selectRepoFullName}
                    onChange={(e) => setSelectRepoFullName(e.target.value)}
                    className="w-full px-3 py-2 rounded bg-zinc-900 border border-zinc-600 text-zinc-100 text-sm"
                  >
                    <option value="">Select a repository</option>
                    {(githubRepos || []).map((r) => (
                      <option key={r.full_name} value={r.full_name}>{r.full_name}{r.private ? ' (private)' : ''}</option>
                    ))}
                  </select>
                )}
              </div>
              {selectRepoFullName && (
                <div>
                  <label className="block text-xs text-zinc-500 mb-1">Branch</label>
                  {loadingBranches ? (
                    <Text variant="muted" className="text-sm">Loading branches…</Text>
                  ) : (
                    <select
                      value={selectBranchName}
                      onChange={(e) => setSelectBranchName(e.target.value)}
                      className="w-full px-3 py-2 rounded bg-zinc-900 border border-zinc-600 text-zinc-100 text-sm"
                    >
                      {(githubBranches || []).map((b) => (
                        <option key={b.name} value={b.name}>{b.name}</option>
                      ))}
                    </select>
                  )}
                </div>
              )}
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  variant="secondary"
                  disabled={!selectRepoFullName || !selectBranchName || savingRepoSelection}
                  onClick={() => {
                    if (!projectId || !selectRepoFullName || !selectBranchName) return
                    setSavingRepoSelection(true)
                    updateProject(projectId, { repo_url: selectRepoFullName, repo_branch: selectBranchName })
                      .then((p) => {
                        setProject(p)
                        setShowRepoSelector(false)
                        toast.success('Repository and branch saved')
                      })
                      .catch((e) => toast.error(e.message || 'Failed to save'))
                      .finally(() => setSavingRepoSelection(false))
                  }}
                  className="inline-flex items-center gap-2"
                >
                  {savingRepoSelection ? 'Saving…' : <><FiSave className="w-4 h-4" /> Save</>}
                </Button>
                {showRepoSelector && (
                  <button
                    type="button"
                    onClick={() => { setShowRepoSelector(false); setSelectRepoFullName(''); setSelectBranchName(''); setGithubBranches([]); }}
                    className="text-sm text-zinc-500 hover:text-zinc-300 underline"
                  >
                    Cancel
                  </button>
                )}
              </div>
            </div>
          ) : project.repo_url ? (
            <div className="space-y-2">
              <code className="block px-3 py-2 rounded bg-zinc-900 text-sm text-sky-400 break-all">{project.repo_url}</code>
              <span className="text-xs text-zinc-500">Branch: {project.repo_branch || 'main'}</span>
              {project.has_github_connected ? (
                <div className="flex flex-wrap items-center gap-2">
                  <p className="flex items-center gap-2 text-sm text-emerald-400">
                    <FiCheck className="w-4 h-4 flex-shrink-0" /> GitHub account connected
                  </p>
                  <button
                    type="button"
                    onClick={() => { setShowRepoSelector(true); setSelectRepoFullName(project.repo_url); setSelectBranchName(project.repo_branch || 'main'); }}
                    className="text-xs text-zinc-500 hover:text-zinc-300 underline"
                  >
                    Change repository
                  </button>
                  <button
                    type="button"
                    onClick={() => disconnectProjectGitHub(projectId).then(() => fetchProject(projectId).then(setProject)).then(() => toast.success('GitHub disconnected')).catch((e) => toast.error(e.message))}
                    className="text-xs text-zinc-500 hover:text-zinc-300 underline"
                  >
                    Disconnect
                  </button>
                </div>
              ) : (
                <div>
                  <p className="text-sm text-amber-400 mb-2">Connect your GitHub account to clone private repos or to use this project in a multi-user setup.</p>
                  <Button
                    variant="secondary"
                    onClick={() => { window.location.href = getGitHubAuthorizeUrl(projectId); }}
                    className="inline-flex items-center gap-2"
                  >
                    <FiGitBranch className="w-4 h-4" /> Connect GitHub account
                  </Button>
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-2">
              <code className="block px-3 py-2 rounded bg-zinc-900 text-sm text-zinc-300 break-all">{project.codebase_path || '(empty)'}</code>
              {!project.has_github_connected && (
                <div>
                  <p className="text-sm text-amber-400 mb-2">Connect your GitHub account to choose a repository and branch from your account.</p>
                  <Button
                    variant="secondary"
                    onClick={() => { window.location.href = getGitHubAuthorizeUrl(projectId); }}
                    className="inline-flex items-center gap-2"
                  >
                    <FiGitBranch className="w-4 h-4" /> Connect GitHub account
                  </Button>
                </div>
              )}
            </div>
          )}

          <div className="flex justify-between mt-4">
            <Button variant="ghost" onClick={onBack} className="inline-flex items-center gap-2"><FiChevronLeft className="w-4 h-4" /> Previous</Button>
            <Button variant="secondary" onClick={() => goToStep(2)} disabled={!step1Done} className="inline-flex items-center gap-2">Next <FiChevronRight className="w-4 h-4" /></Button>
          </div>
        </section>
      )}

      {/* Step 2 – Agent / Schema */}
      {step === 2 && (
        <section className="rounded-lg border border-zinc-600 bg-zinc-800/50 p-4">
          <Text as="h2" variant="strong" className="block mb-2">Step 2 – Agent configuration</Text>
          <Text variant="muted" className="block mb-2">
            Add to the agent config (config.yaml) and run the agent. When it sends the schema, this page will update automatically.
          </Text>
          <div className="space-y-2">
            <div>
              <Text variant="muted" className="text-xs">backend_ws_url</Text>
              <div className="flex gap-2 items-center">
                <code className="flex-1 px-3 py-2 rounded bg-zinc-900 text-xs text-sky-400 break-all">{getWsAgentUrl()}</code>
                <Button variant="secondary" onClick={() => handleCopy(getWsAgentUrl())} className="inline-flex items-center gap-2"><FiCopy className="w-4 h-4" /> Copy</Button>
              </div>
            </div>
            <div>
              <Text variant="muted" className="text-xs">backend_api_key</Text>
              <div className="flex gap-2 items-center">
                <code className="flex-1 px-3 py-2 rounded bg-zinc-900 text-xs text-sky-400 break-all font-mono">{project.agent_api_key}</code>
                <Button variant="secondary" onClick={() => handleCopy(project.agent_api_key)} className="inline-flex items-center gap-2"><FiCopy className="w-4 h-4" /> Copy</Button>
              </div>
            </div>
          </div>
          <div className="mt-3 flex items-center gap-2">
            <span className={`inline-block w-2 h-2 rounded-full ${project.has_schema ? 'bg-green-500' : 'bg-amber-500'}`} />
            <Text variant="muted">
              {project.has_schema ? 'Schema received' : 'Waiting for the agent to send the schema…'}
            </Text>
          </div>
          <div className="flex justify-between mt-4">
            <Button variant="ghost" onClick={() => goToStep(1)} className="inline-flex items-center gap-2"><FiChevronLeft className="w-4 h-4" /> Previous</Button>
            <Button variant="secondary" onClick={() => goToStep(3)} disabled={!step2Done} className="inline-flex items-center gap-2">Next <FiChevronRight className="w-4 h-4" /></Button>
          </div>
        </section>
      )}

      {/* Step 3 – Project tree */}
      {step === 3 && (
        <section className="rounded-lg border border-zinc-600 bg-zinc-800/50 p-4">
          <Text as="h2" variant="strong" className="block mb-2">Step 3 – Project tree</Text>
          <Text variant="muted" className="block mb-3">
            Uncheck folders or files to exclude from analysis. By default everything is included. Save your selection before going to the next step.
          </Text>
          {treeError && <Text variant="danger" className="block mb-2">{treeError}</Text>}
          {treeLoading && <Text variant="muted">Loading tree…</Text>}
          {!treeLoading && tree && (
            <div className="min-h-[420px] max-h-[32rem] overflow-y-auto rounded bg-zinc-900 border border-zinc-600 p-3 mb-3 text-sm">
              <TreeNode
                node={tree}
                excludedPaths={excludedPaths}
                onToggle={handleTogglePath}
                basePath=""
                isRoot
                expandedPaths={expandedPaths}
                onToggleExpand={handleToggleExpand}
              />
            </div>
          )}
          {!treeLoading && tree && (
            <div className="flex gap-2">
              <Button variant="primary" onClick={handleSaveExcluded} disabled={savingPaths} className="inline-flex items-center gap-2">
                <FiSave className="w-4 h-4" /> {savingPaths ? 'Saving…' : 'Save selection'}
              </Button>
              <Button variant="secondary" onClick={loadTree} className="inline-flex items-center gap-2"><FiRefreshCw className="w-4 h-4" /> Reload tree</Button>
            </div>
          )}
          <div className="flex justify-between mt-4">
            <Button variant="ghost" onClick={() => goToStep(2)} className="inline-flex items-center gap-2"><FiChevronLeft className="w-4 h-4" /> Previous</Button>
            <Button variant="secondary" onClick={() => goToStep(4)} disabled={!step3Done} className="inline-flex items-center gap-2">Next <FiChevronRight className="w-4 h-4" /></Button>
          </div>
        </section>
      )}

      {/* Step 4 – Analysis */}
      {step === 4 && (
        <section className="rounded-lg border border-zinc-600 bg-zinc-800/50 p-4">
          <Text as="h2" variant="strong" className="block mb-2">Step 4 – Run analysis</Text>
          {analyzeError && <Text variant="danger" className="block mb-3">{analyzeError}</Text>}
          <div className="flex flex-wrap gap-3 mb-3">
            <Button
              variant="primary"
              onClick={handleRunAnalysis}
              disabled={analyzing || !project.has_schema || (!(project?.codebase_path?.trim()) && !(project?.repo_url?.trim()))}
              className="inline-flex items-center gap-2"
            >
              <FiPlay className="w-4 h-4" /> {analyzing ? 'Analyzing…' : 'Run analysis'}
            </Button>
            {analyzing && (
              <Button variant="secondary" onClick={handleCancelAnalysis} disabled={cancellingJob} className="inline-flex items-center gap-2">
                <FiStopCircle className="w-4 h-4" /> {cancellingJob ? 'Stopping…' : 'Stop analysis'}
              </Button>
            )}
            {!analyzing && project.has_checkpoint && (
              <Button variant="primary" onClick={handleResumeAnalysis} className="inline-flex items-center gap-2" title="Resume from last checkpoint">
                <FiPlayCircle className="w-4 h-4" /> Resume analysis
              </Button>
            )}
            {!analyzing && (
              <Button variant="secondary" onClick={() => fetchProjectGraph(projectId).then(onOpenGraph).then(() => toast.success('Graph loaded')).catch(() => { setAnalyzeError('No graph yet. Run analysis first.'); toast.error('No graph yet. Run analysis first.') })} className="inline-flex items-center gap-2">
                <FiEye className="w-4 h-4" /> View graph
              </Button>
            )}
            {!analyzing && project.has_graph && (
              <Button variant="secondary" onClick={() => setClearGraphConfirm(true)} className="inline-flex items-center gap-2 text-amber-400 hover:text-amber-300">
                <FiTrash2 className="w-4 h-4" /> Clear analysis / Start from scratch
              </Button>
            )}
          </div>
          {clearGraphConfirm && (
            <div className="mb-3 p-3 rounded bg-zinc-900 border border-amber-600/50">
              <Text variant="body" className="block mb-2">Clear all analysis for this project? You can run a new analysis from scratch.</Text>
              <div className="flex gap-2">
                <Button variant="secondary" onClick={() => setClearGraphConfirm(false)}>No, cancel</Button>
                <Button variant="primary" onClick={handleClearGraph} disabled={clearingGraph} className="inline-flex items-center gap-2 bg-amber-600 hover:bg-amber-500">
                  <FiTrash2 className="w-4 h-4" /> {clearingGraph ? 'Clearing…' : 'Yes, clear analysis'}
                </Button>
              </div>
            </div>
          )}
          {analyzing && jobLog && (
            <div className="mt-3 rounded bg-zinc-900 border border-zinc-600 p-3">
              <Text variant="muted" className="text-xs block mb-2">Analysis log:</Text>
              <pre className="text-xs text-zinc-300 whitespace-pre-wrap font-mono max-h-48 overflow-y-auto">
                {jobLog}
              </pre>
            </div>
          )}
          <div className="flex justify-between mt-4">
            <Button variant="ghost" onClick={() => goToStep(3)} className="inline-flex items-center gap-2"><FiChevronLeft className="w-4 h-4" /> Previous</Button>
            <span />
          </div>
        </section>
      )}
    </div>
  )
}
