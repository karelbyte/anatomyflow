import { useState } from 'react'
import { FiPlus, FiTrash2 } from 'react-icons/fi'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import Text from '../atoms/Text'
import { Button } from '../atoms'

const CODE_NODE_KINDS = ['table', 'model', 'view', 'controller', 'route', 'page', 'api_route', 'component']
const TAB_CODE = 'code'
const TAB_NOTES = 'notes'

export default function CodePanel({ code, label, filePath = null, language = 'php', nodeKind = '', loading = false, error = null, notes = [], onSaveNotes }) {
  const [newNote, setNewNote] = useState('')
  const [activeTab, setActiveTab] = useState(TAB_CODE)
  const isCodeNode = CODE_NODE_KINDS.includes((nodeKind || '').toLowerCase())
  const hasNotes = (notes || []).length > 0
  const showTabs = onSaveNotes != null

  const handleAddNote = () => {
    const t = newNote.trim()
    if (!t || !onSaveNotes) return
    onSaveNotes([...(notes || []), t])
    setNewNote('')
  }

  const handleRemoveNote = (index) => {
    if (!onSaveNotes) return
    const next = (notes || []).filter((_, i) => i !== index)
    onSaveNotes(next)
  }

  const tabBar = showTabs && (
    <div className="flex border-b border-surface-border bg-surface flex-shrink-0 gap-0">
      <button
        type="button"
        onClick={() => setActiveTab(TAB_CODE)}
        className={`px-3 py-2 text-sm font-medium transition-colors border-b-2 ${
          activeTab === TAB_CODE ? 'border-sky-500 text-sky-400' : 'border-transparent text-zinc-400 hover:text-zinc-200'
        }`}
      >
        Code
      </button>
      <button
        type="button"
        onClick={() => setActiveTab(TAB_NOTES)}
        className={`relative px-3 py-2 text-sm font-medium transition-colors border-b-2 flex items-center gap-1.5 ${
          activeTab === TAB_NOTES ? 'border-sky-500 text-sky-400' : 'border-transparent text-zinc-400 hover:text-zinc-200'
        }`}
      >
        Notes
        {hasNotes && (
          <span className="flex items-center justify-center min-w-[18px] h-[18px] rounded-full bg-sky-500/90 text-[10px] font-bold text-white" title={`${notes.length} note(s)`}>
            {notes.length}
          </span>
        )}
      </button>
    </div>
  )

  const codeContent = (
    <>
      {loading && (
        <div className="flex-1 flex items-center justify-center text-center p-6">
          <Text variant="muted">Loading code…</Text>
        </div>
      )}
      {!loading && error && (
        <div className="flex-1 flex items-center justify-center text-center p-6">
          <Text variant="danger" className="text-sm">{error}</Text>
        </div>
      )}
      {!loading && !error && code && (
        <div className="flex-1 overflow-auto code-panel-scroll min-h-0">
          <SyntaxHighlighter
            language={language}
            style={oneDark}
            customStyle={{
              margin: 0,
              padding: 16,
              background: '#1e1e1e',
              fontSize: 13,
              minHeight: '100%',
            }}
            showLineNumbers
            lineNumberStyle={{ minWidth: '2em', color: '#495057', userSelect: 'none' }}
            codeTagProps={{ style: { fontFamily: 'ui-monospace, monospace' } }}
          >
            {code}
          </SyntaxHighlighter>
        </div>
      )}
      {!loading && !error && !code && (
        <div className="flex-1 flex items-center justify-center p-6 text-center min-h-0">
          <Text variant="muted">
            {isCodeNode ? `No code for this ${nodeKind || 'node'}.` : 'No code.'}
          </Text>
        </div>
      )}
    </>
  )

  const notesContent = showTabs && (
    <div className="flex flex-col flex-1 min-h-0 p-3">
      <div className="space-y-2 overflow-y-auto code-panel-scroll flex-1 min-h-0">
        {(notes || []).map((note, i) => (
          <div key={i} className="flex items-start gap-2 rounded bg-zinc-800/80 px-2 py-1.5 text-sm text-zinc-200">
            <span className="flex-1 min-w-0 break-words">{note}</span>
            <button type="button" onClick={() => handleRemoveNote(i)} className="flex-shrink-0 p-0.5 text-zinc-500 hover:text-red-400" aria-label="Eliminar nota">
              <FiTrash2 className="w-4 h-4" />
            </button>
          </div>
        ))}
      </div>
      <div className="flex gap-2 pt-2 flex-shrink-0 border-t border-zinc-700 mt-2">
        <input
          type="text"
          value={newNote}
          onChange={(e) => setNewNote(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleAddNote()}
          placeholder="Add note…"
          className="flex-1 min-w-0 rounded bg-zinc-800 border border-zinc-600 px-2 py-1.5 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
        />
        <Button variant="secondary" onClick={handleAddNote} className="flex-shrink-0" disabled={!newNote.trim()}>
          <FiPlus className="w-4 h-4" />
        </Button>
      </div>
    </div>
  )

  if (!showTabs && !code) {
    return (
      <div className="flex flex-col h-full overflow-hidden">
        <div className="flex-1 flex items-center justify-center text-center p-6">
          <Text variant="muted">
            {isCodeNode
              ? `No code available for this ${nodeKind || 'node'}. Re-run analysis to generate it.`
              : 'Select a node with associated code'}
          </Text>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {(label || filePath) && (
        <div className="px-4 py-2.5 bg-surface border-b border-surface-border space-y-0.5 flex-shrink-0">
          {label && (
            <Text as="div" variant="strong" className="text-sm">
              {label}
            </Text>
          )}
          {filePath && (
            <Text as="div" variant="muted" className="text-xs font-mono truncate" title={filePath}>
              {filePath}
            </Text>
          )}
        </div>
      )}
      {tabBar}
      <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
        {activeTab === TAB_CODE && codeContent}
        {activeTab === TAB_NOTES && notesContent}
      </div>
    </div>
  )
}
