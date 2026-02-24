import { useCallback, useState } from 'react'
import toast from 'react-hot-toast'
import { FiArrowLeft, FiChevronRight, FiFolder, FiFolderPlus, FiGitBranch, FiPlus, FiX } from 'react-icons/fi'
import { Button, Text } from '../components/atoms'
import { createProject, fetchBrowse } from '../lib/api'

const SOURCE_LOCAL = 'local'
const SOURCE_GITHUB = 'github'

export default function NewProjectForm({ onCreated, onCancel }) {
  const [name, setName] = useState('')
  const [sourceMode, setSourceMode] = useState(SOURCE_LOCAL)
  const [codebasePath, setCodebasePath] = useState('')
  const [loading, setLoading] = useState(false)
  const [browseOpen, setBrowseOpen] = useState(false)
  const [browseCurrent, setBrowseCurrent] = useState('')
  const [browseParent, setBrowseParent] = useState(null)
  const [browseEntries, setBrowseEntries] = useState([])
  const [browseLoading, setBrowseLoading] = useState(false)
  const [browseError, setBrowseError] = useState(null)

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

  const handleBrowseFolder = () => {
    setBrowseOpen(true)
    setBrowseError(null)
    loadBrowse('')
  }

  const handleSelectFolder = (path) => {
    setCodebasePath(path)
    setBrowseOpen(false)
    toast.success('Path saved')
  }

  const canSubmit = name.trim() && (sourceMode === SOURCE_GITHUB || codebasePath.trim().length > 0)
  const handleSubmit = (e) => {
    e.preventDefault()
    if (!canSubmit) return
    setLoading(true)
    const payload = {
      name: name.trim(),
      codebase_path: sourceMode === SOURCE_LOCAL ? codebasePath.trim() : '',
      repo_url: sourceMode === SOURCE_GITHUB ? '' : '',
      repo_branch: 'main',
    }
    createProject(payload)
      .then((project) => {
        toast.success('Project created')
        onCreated(project.id)
      })
      .catch((e) => {
        toast.error(e.message || 'Failed to create project')
        setLoading(false)
      })
  }

  return (
    <div className="max-w-xl mx-auto p-6">
      <div className="flex items-center gap-4 mb-6">
        <Button variant="ghost" onClick={onCancel} className="inline-flex items-center gap-2"><FiArrowLeft className="w-4 h-4" /> Back</Button>
        <Text as="h1" variant="title">New project</Text>
      </div>
      <form onSubmit={handleSubmit} className="rounded-lg border border-zinc-600 bg-zinc-800/50 p-6 space-y-4">
        <div>
          <label className="block text-sm font-medium text-zinc-300 mb-1">Name</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full px-3 py-2 rounded bg-zinc-900 border border-zinc-600 text-zinc-100 placeholder-zinc-500"
            placeholder="My awesome project"
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-zinc-300 mb-2">Code source</label>
          <div className="flex gap-2 mb-3">
            <button
              type="button"
              onClick={() => setSourceMode(SOURCE_LOCAL)}
              className={`px-3 py-1.5 rounded text-sm font-medium inline-flex items-center gap-1.5 ${sourceMode === SOURCE_LOCAL ? 'bg-zinc-600 text-zinc-100' : 'bg-zinc-800 text-zinc-400 hover:text-zinc-200'}`}
            >
              <FiFolder className="w-4 h-4" /> Local path
            </button>
            <button
              type="button"
              onClick={() => setSourceMode(SOURCE_GITHUB)}
              className={`px-3 py-1.5 rounded text-sm font-medium inline-flex items-center gap-1.5 ${sourceMode === SOURCE_GITHUB ? 'bg-zinc-600 text-zinc-100' : 'bg-zinc-800 text-zinc-400 hover:text-zinc-200'}`}
            >
              <FiGitBranch className="w-4 h-4" /> GitHub repo
            </button>
          </div>
          {sourceMode === SOURCE_LOCAL && (
            <>
              <label className="block text-sm text-zinc-400 mb-1">Project path (on server)</label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={codebasePath}
                  onChange={(e) => setCodebasePath(e.target.value)}
                  className="flex-1 px-3 py-2 rounded bg-zinc-900 border border-zinc-600 text-zinc-100 placeholder-zinc-500"
                  placeholder="e.g. C:\www\my-project or D:\project\ProjectAnatomy"
                />
               {/* <Button type="button" variant="secondary" onClick={handleBrowseFolder} className="inline-flex items-center gap-2 flex-shrink-0" title="Browse server folders">
                  <FiFolder className="w-4 h-4" /> Browse
                </Button>*/}
              </div>
              <Text variant="muted" className="text-xs mt-1">Use Browse to pick a folder on the server or type the absolute path.</Text>
            </>
          )}
          {sourceMode === SOURCE_GITHUB && (
            <Text variant="muted" className="text-sm">
              After creating the project, open it and in Step 1 click &quot;Connect GitHub account&quot;. Then choose a repository and branch from the list — no need to type the URL.
            </Text>
          )}
        </div>

        {/* Browse server folders modal */}
        {browseOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60" role="dialog" aria-modal="true" aria-labelledby="browse-title">
            <div className="bg-zinc-800 border border-zinc-600 rounded-lg shadow-xl max-w-lg w-full max-h-[80vh] flex flex-col">
              <div className="p-4 border-b border-zinc-600 flex items-center justify-between">
                <Text as="h2" id="browse-title" variant="strong" className="flex items-center gap-2">
                  <FiFolder className="w-5 h-5" /> Choose project folder
                </Text>
                <Button variant="ghost" onClick={() => setBrowseOpen(false)} className="text-zinc-400 hover:text-zinc-200"><FiX className="w-5 h-5" /></Button>
              </div>
              <div className="p-4 border-b border-zinc-600 bg-zinc-900/50 min-h-0">
                <p className="text-xs text-zinc-500 truncate mb-2" title={browseCurrent}>{browseCurrent || '…'}</p>
                {browseError && <Text variant="danger" className="text-sm mb-2">{browseError}</Text>}
                {browseLoading ? (
                  <Text variant="muted">Loading…</Text>
                ) : (
                  <div className="space-y-1 max-h-64 overflow-y-auto">
                    {browseParent !== null && (
                      <button
                        type="button"
                        onClick={() => loadBrowse(browseParent)}
                        className="w-full flex items-center gap-2 px-3 py-2 rounded text-left text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200"
                      >
                        <FiFolder className="w-4 h-4" /> ..
                      </button>
                    )}
                    {browseEntries.map((entry) => (
                      <button
                        key={entry.path}
                        type="button"
                        onClick={() => loadBrowse(entry.path)}
                        className="w-full flex items-center gap-2 px-3 py-2 rounded text-left text-zinc-200 hover:bg-zinc-700"
                      >
                        <FiChevronRight className="w-4 h-4 text-zinc-500" /> <FiFolder className="w-4 h-4" /> {entry.name}
                      </button>
                    ))}
                    {!browseLoading && browseEntries.length === 0 && browseParent === null && <Text variant="muted">No folders.</Text>}
                  </div>
                )}
              </div>
              <div className="p-4 flex justify-end gap-2">
                <Button variant="secondary" onClick={() => setBrowseOpen(false)}>Cancel</Button>
                <Button variant="primary" onClick={() => handleSelectFolder(browseCurrent)} className="inline-flex items-center gap-2" disabled={browseLoading}>
                  <FiFolderPlus className="w-4 h-4" /> Use this folder
                </Button>
              </div>
            </div>
          </div>
        )}
        <div className="flex gap-3">
          <Button type="submit" variant="primary" disabled={loading || !canSubmit} className="inline-flex items-center gap-2">
            <FiPlus className="w-4 h-4" /> {loading ? 'Creating…' : 'Create project'}
          </Button>
          <Button type="button" variant="secondary" onClick={onCancel} className="inline-flex items-center gap-2"><FiX className="w-4 h-4" /> Cancel</Button>
        </div>
      </form>
    </div>
  )
}
