import { useState, useMemo } from 'react'
import Text from '../atoms/Text'

export default function PathPanel({
  cycleDisplay = null,
  fanInFanOut = null,
  pathDistances = null,
  pathEdgeReasons = null,
  pathNodesWithCode = [],
}) {
  const [searchInPathQuery, setSearchInPathQuery] = useState('')

  const searchInPathResults = useMemo(() => {
    const q = searchInPathQuery.trim().toLowerCase()
    if (!q || !pathNodesWithCode.length) return []
    const results = []
    for (const { id, label, code: nodeCode } of pathNodesWithCode) {
      const lines = (nodeCode || '').split('\n')
      lines.forEach((line, idx) => {
        if (line.toLowerCase().includes(q)) results.push({ nodeId: id, nodeLabel: label, lineNumber: idx + 1, line })
      })
    }
    return results
  }, [searchInPathQuery, pathNodesWithCode])

  const hasContent = cycleDisplay || fanInFanOut != null ||
    (pathDistances && (pathDistances.upstream.length > 0 || pathDistances.downstream.length > 0)) ||
    (pathEdgeReasons && pathEdgeReasons.length > 0) ||
    pathNodesWithCode.length > 0

  if (!hasContent) {
    return (
      <div className="flex flex-col h-full overflow-hidden bg-panel border-l border-surface-border">
        <div className="px-4 py-3 border-b border-surface-border flex-shrink-0">
          <Text as="div" variant="strong" className="text-sm">Path</Text>
        </div>
        <div className="flex-1 flex items-center justify-center p-6 text-center">
          <Text variant="muted" className="text-sm">Select a node to see impact path</Text>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full overflow-hidden bg-panel border-l border-surface-border">
      <div className="px-4 py-3 border-b border-surface-border flex-shrink-0">
        <Text as="div" variant="strong" className="text-sm">Path</Text>
      </div>
      <div className="flex flex-col flex-1 min-h-0 overflow-auto code-panel-scroll">
        {cycleDisplay && (
          <div className="flex-shrink-0 px-3 py-2 bg-amber-500/15 border-b border-amber-500/40 text-amber-200 text-sm">
            <span className="font-medium">Cycle detected:</span> {cycleDisplay}
          </div>
        )}
        {fanInFanOut != null && (
          <div className="flex-shrink-0 px-3 py-1.5 border-b border-zinc-700 text-xs text-zinc-400">
            <span className="text-zinc-500">Selected node:</span> Fan-in {fanInFanOut.fanIn} · Fan-out {fanInFanOut.fanOut}
          </div>
        )}
        {pathDistances && (pathDistances.upstream.length > 0 || pathDistances.downstream.length > 0) && (
          <div className="flex-shrink-0 px-3 py-2 bg-zinc-800/60 border-b border-zinc-700 text-xs text-zinc-300 space-y-1">
            {pathDistances.upstream.length > 0 && (
              <div>
                <span className="text-zinc-500 font-medium">Upstream:</span>{' '}
                {pathDistances.upstream.map(({ label: l, distance }) => `${l} (${distance} step${distance !== 1 ? 's' : ''})`).join(', ')}
              </div>
            )}
            {pathDistances.downstream.length > 0 && (
              <div>
                <span className="text-zinc-500 font-medium">Downstream:</span>{' '}
                {pathDistances.downstream.map(({ label: l, distance }) => `${l} (${distance} step${distance !== 1 ? 's' : ''})`).join(', ')}
              </div>
            )}
          </div>
        )}
        {pathEdgeReasons && pathEdgeReasons.length > 0 && (
          <div className="flex-shrink-0 px-3 py-2 bg-zinc-800/40 border-b border-zinc-700 text-xs text-zinc-400">
            <span className="text-zinc-500 font-medium block mb-1">Why in path:</span>
            <ul className="list-none space-y-0.5">
              {pathEdgeReasons.map((r, i) => (
                <li key={i}>{r.from} → {r.to} <span className="text-zinc-500">({r.relation})</span></li>
              ))}
            </ul>
          </div>
        )}
        {pathNodesWithCode.length > 0 && (
          <div className="flex-shrink-0 px-3 py-2 bg-zinc-800/50 border-b border-zinc-700 text-xs">
            <input
              type="text"
              value={searchInPathQuery}
              onChange={(e) => setSearchInPathQuery(e.target.value)}
              placeholder="Search in path code…"
              className="w-full rounded bg-zinc-900 border border-zinc-600 px-2 py-1.5 text-zinc-200 placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
            />
            {searchInPathResults.length > 0 && (
              <ul className="mt-1.5 space-y-0.5 text-zinc-400 max-h-32 overflow-y-auto">
                {searchInPathResults.slice(0, 15).map((r, i) => (
                  <li key={i} className="truncate" title={r.line}>
                    <span className="text-zinc-300 font-medium">{r.nodeLabel}</span> (line {r.lineNumber}): {r.line.trim().slice(0, 60)}{r.line.length > 60 ? '…' : ''}
                  </li>
                ))}
                {searchInPathResults.length > 15 && <li className="text-zinc-500">+{searchInPathResults.length - 15} more</li>}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
