import { useCallback, useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { FiEdit2, FiEye, FiInfo, FiPlus, FiPlay, FiTrash2, FiX } from 'react-icons/fi'
import { Button, Text } from '../components/atoms'
import { fetchProjects, deleteProject } from '../lib/api'

const ONBOARDING_KEY = 'projectanatomy_onboarding_dismissed'

export default function ProjectsList({ onNewProject, onOpenAnalysis, onViewGraph }) {
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [deleting, setDeleting] = useState(false)
  const [onboardingDismissed, setOnboardingDismissed] = useState(() => {
    try {
      return localStorage.getItem(ONBOARDING_KEY) === '1'
    } catch {
      return false
    }
  })

  const dismissOnboarding = useCallback(() => {
    try {
      localStorage.setItem(ONBOARDING_KEY, '1')
    } catch (_) {}
    setOnboardingDismissed(true)
  }, [])

  const load = useCallback(() => {
    setLoading(true)
    fetchProjects()
      .then(setProjects)
      .catch((e) => toast.error(e.message || 'Failed to load projects'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const handleDeleteClick = (e, project) => {
    e.stopPropagation()
    setDeleteTarget(project)
  }

  const handleConfirmDelete = () => {
    if (!deleteTarget) return
    setDeleting(true)
    deleteProject(deleteTarget.id)
      .then(() => {
        setDeleteTarget(null)
        load()
        toast.success('Project deleted')
      })
      .catch((e) => toast.error(e.message || 'Failed to delete'))
      .finally(() => setDeleting(false))
  }

  const handleCancelDelete = () => {
    if (!deleting) setDeleteTarget(null)
  }

  if (loading && projects.length === 0) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <Text variant="muted">Loading projects…</Text>
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto p-6">
      <Text as="h1" variant="title">Anatomy Flow</Text>
      <Text variant="muted">Dissecting code, visualizing connections.</Text>
      {!onboardingDismissed && (
        <div className="mt-4 rounded-lg border border-sky-600/50 bg-sky-900/20 p-4 flex items-start gap-3">
          <FiInfo className="w-5 h-5 text-sky-400 flex-shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <Text variant="strong" className="block mb-1">What does ProjectAnatomy do?</Text>
            <Text variant="body" className="text-zinc-300 text-sm">
              Connect a codebase (local or GitHub), optionally attach the schema via the agent, then run analysis to build a dependency graph: tables, models, controllers, views, routes (and for Next.js: pages, API routes, components). Click nodes to see code and highlight dependencies.
            </Text>
          </div>
          <Button variant="ghost" onClick={dismissOnboarding} className="flex-shrink-0" aria-label="Dismiss">
            <FiX className="w-4 h-4" />
          </Button>
        </div>
      )}
      {projects.length !== 0 ? <div className="flex items-center justify-end mb-6 mt-6">
        <Button variant="primary" onClick={onNewProject} className="inline-flex items-center gap-2">
          <FiPlus className="w-4 h-4" /> New project
        </Button>
      </div> : <div className='h-10'></div>}
      {projects.length === 0 ? (
        <div className="rounded-lg border border-zinc-600 bg-zinc-800/50 p-8 text-center">
          <Text variant="muted" className="block mb-4">No projects yet. Create one to connect a codebase and optionally the agent.</Text>
          <Button variant="primary" onClick={onNewProject} className="inline-flex items-center gap-2">
            <FiPlus className="w-4 h-4" /> Create project
          </Button>
        </div>
      ) : (
        <ul className="space-y-2">
          {projects.map((p) => (
            <li key={p.id}>
              <div className="rounded-lg border border-zinc-600 bg-zinc-800/50 px-4 py-3 flex items-center justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <span className="font-medium text-zinc-200 block truncate">{p.name}</span>
                  <span className="text-xs text-zinc-500 block truncate">{p.codebase_path || 'No path'}</span>
                </div>
                <div className="flex items-center gap-1.5 flex-shrink-0">
                  <Button
                    variant="secondary"
                    onClick={() => onOpenAnalysis(p.id)}
                    className="inline-flex items-center gap-1.5"
                    title="Open project and run analysis steps"
                  >
                    <FiPlay className="w-4 h-4" /> Analysis
                  </Button>
                  {p.has_graph && (
                    <Button
                      variant="secondary"
                      onClick={() => onViewGraph(p.id)}
                      className="inline-flex items-center gap-1.5"
                      title="View graph"
                    >
                      <FiEye className="w-4 h-4" /> View graph
                    </Button>
                  )}
                  <Button
                    variant="secondary"
                    onClick={() => onOpenAnalysis(p.id)}
                    className="inline-flex items-center gap-1.5"
                    title="Edit project"
                  >
                    <FiEdit2 className="w-4 h-4" /> Edit
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={(e) => handleDeleteClick(e, p)}
                    className="text-red-400 hover:text-red-300 hover:bg-red-900/20 inline-flex items-center gap-1.5"
                    title="Delete project"
                  >
                    <FiTrash2 className="w-4 h-4" /> Delete
                  </Button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      {/* Delete confirmation modal */}
      {deleteTarget && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60"
          onClick={handleCancelDelete}
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-modal-title"
        >
          <div
            className="rounded-lg border border-zinc-600 bg-zinc-800 p-6 shadow-xl max-w-md w-full"
            onClick={(e) => e.stopPropagation()}
          >
            <Text as="h2" id="delete-modal-title" variant="strong" className="block mb-2">
              Delete project
            </Text>
            <Text variant="body" className="block mb-4">
              Delete <strong className="text-zinc-200">{deleteTarget.name}</strong>? All its data (schema, analysis, graph, and tree selection) will be removed from the database.
            </Text>
            <div className="flex gap-2 justify-end">
              <Button variant="secondary" onClick={handleCancelDelete} disabled={deleting} className="inline-flex items-center gap-2">
                <FiX className="w-4 h-4" /> Cancel
              </Button>
              <Button
                variant="primary"
                onClick={handleConfirmDelete}
                disabled={deleting}
                className="bg-red-600 hover:bg-red-500 text-white border-red-500 inline-flex items-center gap-2"
              >
                <FiTrash2 className="w-4 h-4" /> {deleting ? 'Deleting…' : 'Delete'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
