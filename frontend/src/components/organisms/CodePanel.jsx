import { useEffect, useMemo, useState } from 'react'
import { FiCopy, FiPlus, FiTrash2 } from 'react-icons/fi'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import Text from '../atoms/Text'
import { Button } from '../atoms'

const CODE_NODE_KINDS = ['table', 'model', 'view', 'controller', 'route', 'page', 'api_route', 'component']
const TAB_CODE = 'code'
const TAB_NOTES = 'notes'

/** Finds the line range (1-based) of a method/function in source code. Works for PHP and JS/TS. */
function findMethodRange(source, methodName) {
  if (!source || !methodName || typeof methodName !== 'string') return null

  // Normalizamos nombres como:
  // - App\Http\Controllers\UserController@index
  // - UserController::index
  // - $this->index
  // - index()
  let name = methodName.trim()
  if (!name) return null

  // Nos quedamos con la última parte después de separadores típicos
  // Ej: App\Http\Controllers\UserController@index -> index
  //     UserService.findByEmail -> findByEmail
  //     UserService findByEmail -> findByEmail
  ;['@', '::', '->', '.', ' '].forEach((sep) => {
    if (name.includes(sep)) {
      name = name.split(sep).pop()
    }
  })
  // Quitamos paréntesis si vienen en el nombre (index(), handle(...), etc.)
  name = name.replace(/\(.*$/, '').trim()
  if (!name) return null

  const lines = source.split('\n')
  const nameEsc = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  // PHP: function name( or public/private/protected function name(
  const phpRe = new RegExp(`\\bfunction\\s+${nameEsc}\\s*\\(`, 'i')
  // JS/TS: name( or name = ( or name:
  const jsRe = new RegExp(`\\b${nameEsc}\\s*(?:\\(|=\\s*\\(|:)`, 'i')
  let startLine = -1
  for (let i = 0; i < lines.length; i++) {
    if (phpRe.test(lines[i]) || jsRe.test(lines[i])) {
      startLine = i + 1
      break
    }
  }
  if (startLine === -1) return null
  let depth = 0
  let endLine = startLine
  for (let i = startLine - 1; i < lines.length; i++) {
    const line = lines[i]
    for (const c of line) {
      if (c === '{') depth++
      else if (c === '}') depth--
    }
    endLine = i + 1
    if (depth === 0) break
  }
  return { startLine, endLine }
}

export default function CodePanel({
  code,
  label,
  filePath = null,
  language = 'php',
  nodeKind = '',
  loading = false,
  error = null,
  notes = [],
  onSaveNotes,
  metrics = null,
  relatedNodes = [],
  onJumpToNode,
  methodName = null,
  modelAndTableNames = [],
  codeSummary = null,
  codeSummaryLoading = false,
}) {
  const [newNote, setNewNote] = useState('')
  const [activeTab, setActiveTab] = useState(TAB_CODE)
  const [wrapLines, setWrapLines] = useState(false)
  const [search, setSearch] = useState('')
  const [showFullFile, setShowFullFile] = useState(true)
  const isCodeNode = CODE_NODE_KINDS.includes((nodeKind || '').toLowerCase())
  const hasNotes = (notes || []).length > 0
  const showTabs = onSaveNotes != null

  const methodRange = useMemo(() => findMethodRange(code, methodName), [code, methodName])
  useEffect(() => {
    if (methodRange) setShowFullFile(false)
  }, [methodRange?.startLine, methodRange?.endLine])
  const displayedCode = useMemo(() => {
    if (!code) return ''
    if (showFullFile || !methodRange) return code
    const lines = code.split('\n')
    return lines.slice(methodRange.startLine - 1, methodRange.endLine).join('\n')
  }, [code, showFullFile, methodRange])
  const displayLineOffset = useMemo(() => {
    if (showFullFile || !methodRange) return 0
    return methodRange.startLine - 1
  }, [showFullFile, methodRange])

  const linesWithMatch = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q || !code) return new Set()
    const set = new Set()
    code.split('\n').forEach((line, idx) => {
      if (line.toLowerCase().includes(q)) set.add(idx + 1)
    })
    return set
  }, [search, code])

  const referencesInCode = useMemo(() => {
    const names = (modelAndTableNames || []).filter(Boolean)
    if (!names.length || !displayedCode) return { names: [], lineNumbers: new Set() }
    const found = new Set()
    const lineNumbers = new Set()
    const lines = displayedCode.split('\n')
    names.forEach((name) => {
      const wordRe = new RegExp(`\\b${name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`)
      lines.forEach((line, idx) => {
        if (wordRe.test(line)) {
          found.add(name)
          lineNumbers.add(displayLineOffset + idx + 1)
        }
      })
    })
    return { names: [...found], lineNumbers }
  }, [modelAndTableNames, displayedCode, displayLineOffset])

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
        <div className="flex-1 overflow-auto code-panel-scroll min-h-0 flex flex-col">
          {methodRange && (
            <div className="flex-shrink-0 px-3 py-1.5 bg-zinc-800/80 border-b border-zinc-700 flex items-center justify-between gap-2">
              <span className="text-xs text-zinc-400">
                {showFullFile ? 'Full file' : `Method: ${methodName} (lines ${methodRange.startLine}–${methodRange.endLine})`}
              </span>
              <button
                type="button"
                onClick={() => setShowFullFile((v) => !v)}
                className="text-xs text-sky-400 hover:text-sky-300"
              >
                {showFullFile ? 'Show method only' : 'Show full file'}
              </button>
            </div>
          )}
          <SyntaxHighlighter
            language={language}
            style={oneDark}
            customStyle={{
              margin: 0,
              padding: 16,
              background: '#1e1e1e',
              fontSize: 13,
              minHeight: '100%',
              whiteSpace: wrapLines ? 'pre-wrap' : 'pre',
              wordBreak: wrapLines ? 'break-word' : 'normal',
            }}
            showLineNumbers
            lineNumberStyle={{ minWidth: '2em', color: '#495057', userSelect: 'none' }}
            codeTagProps={{ style: { fontFamily: 'ui-monospace, monospace' } }}
            wrapLines={Boolean(search.trim())}
            lineProps={(lineNumber) => {
              const realLine = displayLineOffset + lineNumber
              const searchHighlight = linesWithMatch.has(realLine)
              const refHighlight = referencesInCode.lineNumbers.has(realLine)
              const bg = searchHighlight
                ? 'rgba(56, 189, 248, 0.14)'
                : refHighlight
                  ? 'rgba(250, 204, 21, 0.08)'
                  : 'transparent'
              return { style: { display: 'block', backgroundColor: bg } }
            }}
          >
            {displayedCode}
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
        <div className="px-4 py-2.5 bg-surface border-b border-surface-border flex-shrink-0 flex items-start justify-between gap-3">
          <div className="space-y-0.5 min-w-0">
            {label && (
              <Text as="div" variant="strong" className="text-sm truncate">
                {label}
              </Text>
            )}
            {filePath && (
              <Text as="div" variant="muted" className="text-xs font-mono truncate" title={filePath}>
                {filePath}
              </Text>
            )}
            {(metrics || relatedNodes?.length) && (
              <div className="flex flex-wrap items-center gap-1 mt-1 text-[10px]">
                {metrics?.isEntry && (
                  <span className="px-1.5 py-0.5 rounded-full bg-emerald-900/70 text-emerald-300 border border-emerald-700/80">
                    Entry
                  </span>
                )}
                {metrics?.isLeaf && (
                  <span className="px-1.5 py-0.5 rounded-full bg-indigo-900/60 text-indigo-200 border border-indigo-700/80">
                    Leaf
                  </span>
                )}
                {metrics?.isCritical && (
                  <span className="px-1.5 py-0.5 rounded-full bg-amber-900/80 text-amber-300 border border-amber-600/80">
                    Critical
                  </span>
                )}
                {(metrics?.fanIn != null || metrics?.fanOut != null) && (
                  <span className="text-zinc-500">
                    Used by {metrics.fanIn ?? 0} · Uses {metrics.fanOut ?? 0}
                  </span>
                )}
              </div>
            )}
            {referencesInCode.names.length > 0 && (
              <div className="mt-1 text-[11px] text-zinc-400 flex flex-wrap gap-1 items-center">
                <span className="font-medium text-zinc-300">Refs in code:</span>
                {referencesInCode.names.map((name) => (
                  <span key={name} className="px-1.5 py-0.5 rounded bg-amber-900/40 text-amber-200 border border-amber-700/60">
                    {name}
                  </span>
                ))}
              </div>
            )}
            {codeSummaryLoading && (
              <div className="mt-1 text-xs text-zinc-500">Summarizing…</div>
            )}
            {!codeSummaryLoading && codeSummary && (
              <div className="mt-1 text-xs text-zinc-300 bg-zinc-800/60 rounded px-2 py-1 border border-zinc-700">
                <span className="font-medium text-zinc-400">Summary: </span>
                {codeSummary}
              </div>
            )}
            {relatedNodes?.length > 0 && (
              <div className="mt-1 text-[11px] text-zinc-400 flex flex-wrap gap-1">
                <span className="font-medium text-zinc-300">Related nodes:</span>
                {relatedNodes.slice(0, 6).map((rn) => (
                  <button
                    key={rn.id}
                    type="button"
                    onClick={() => onJumpToNode && onJumpToNode(rn.id)}
                    className="px-1.5 py-0.5 rounded bg-zinc-800/80 hover:bg-zinc-700 text-xs text-zinc-100 border border-zinc-700"
                    title={rn.label}
                  >
                    {rn.label}
                  </button>
                ))}
                {relatedNodes.length > 6 && (
                  <span className="text-xs text-zinc-500">+{relatedNodes.length - 6} more</span>
                )}
              </div>
            )}
          </div>
          <div className="flex flex-col items-end gap-1 flex-shrink-0">
            <div className="flex items-center gap-1">
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search in code…"
                className="w-40 px-2 py-1 rounded bg-zinc-900 border border-zinc-600 text-xs text-zinc-100 placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
              />
              <Button
                variant="ghost"
                onClick={() => setWrapLines((v) => !v)}
                className="text-[11px] px-2 py-1"
              >
                {wrapLines ? 'No wrap' : 'Wrap'}
              </Button>
            </div>
            <div className="flex items-center gap-1">
              {filePath && (
                <Button
                  variant="ghost"
                  onClick={() => navigator.clipboard?.writeText(filePath).catch(() => {})}
                  className="inline-flex items-center gap-1 text-xs"
                >
                  <FiCopy className="w-3 h-3" /> Path
                </Button>
              )}
              {code && (
                <Button
                  variant="ghost"
                  onClick={() => navigator.clipboard?.writeText(code).catch(() => {})}
                  className="inline-flex items-center gap-1 text-xs"
                >
                  <FiCopy className="w-3 h-3" /> Code
                </Button>
              )}
            </div>
          </div>
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
