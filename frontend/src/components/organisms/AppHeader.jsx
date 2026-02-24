import { useEffect, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import { FiArrowLeft, FiDownload, FiSearch, FiUpload, FiX } from 'react-icons/fi'
import { Button, Text } from '../atoms'
import { FileInputLabel, LegendItem } from '../molecules'
import { KIND_CONFIG } from '../../constants'

export default function AppHeader({
  onFileSelect,
  onExport,
  selectedNodeId,
  onClearPath,
  error,
  onBack,
  visibleKinds,
  setVisibleKinds,
  searchQuery,
  setSearchQuery,
  searchMatches,
  onSearchSelect,
}) {
  const [searchFocused, setSearchFocused] = useState(false)
  const searchRef = useRef(null)

  useEffect(() => {
    if (error) toast.error(error)
  }, [error])

  const toggleKind = (key) => {
    if (!setVisibleKinds) return
    setVisibleKinds((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  const showFilters = visibleKinds != null && setVisibleKinds != null
  const showSearch = setSearchQuery != null && onSearchSelect != null

  return (
    <header className="flex flex-col gap-2 px-4 py-3 bg-surface border-b border-surface-border">
      <div className="flex items-center gap-6 flex-wrap">
        {onBack && (
          <Button variant="ghost" onClick={onBack} className="inline-flex items-center gap-2"><FiArrowLeft className="w-4 h-4" /> Back to project</Button>
        )}
        {onFileSelect && (
          <FileInputLabel accept=".json" onChange={onFileSelect} className="inline-flex items-center gap-2">
            <FiUpload className="w-4 h-4" />
          </FileInputLabel>
        )}
        {onExport && (
          <Button variant="secondary" onClick={onExport} className="inline-flex items-center gap-2">
            <FiDownload className="w-4 h-4" />
          </Button>
        )}
        {showSearch && (
          <div className="relative" ref={searchRef}>
            <span className="absolute left-2 top-1/2 -translate-y-1/2 text-zinc-500">
              <FiSearch className="w-4 h-4" />
            </span>
            <input
              type="text"
              value={searchQuery || ''}
              onChange={(e) => setSearchQuery(e.target.value)}
              onFocus={() => setSearchFocused(true)}
              onBlur={() => setTimeout(() => setSearchFocused(false), 150)}
              placeholder="Search by label or path…"
              className="w-48 pl-8 pr-2 py-1.5 rounded-md bg-zinc-800 border border-zinc-600 text-zinc-200 text-sm placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
            />
            {searchFocused && searchMatches?.length > 0 && (
              <ul className="absolute left-0 top-full mt-1 w-72 max-h-60 overflow-y-auto overflow-x-hidden rounded-md bg-zinc-800 border border-zinc-600 shadow-lg z-50 py-1 code-panel-scroll">
                {searchMatches.slice(0, 20).map((n) => (
                  <li key={n.id}>
                    <button
                      type="button"
                      onClick={() => onSearchSelect(n.id, n)}
                      className="w-full text-left px-3 py-1.5 text-sm text-zinc-200 hover:bg-zinc-700 truncate"
                    >
                      <span className="font-medium block truncate">{n.data?.label || n.id}</span>
                      {n.data?.file_path && <span className="text-xs text-zinc-500 block truncate">{n.data.file_path}</span>}
                    </button>
                  </li>
                ))}
                {searchMatches.length > 20 && <li className="px-3 py-1 text-xs text-zinc-500">+{searchMatches.length - 20} more</li>}
              </ul>
            )}
          </div>
        )}
        {selectedNodeId != null ? (
          <Button variant="secondary" onClick={onClearPath} className="inline-flex items-center gap-2">
            <FiX className="w-4 h-4" /> Clear path
          </Button>
        ) : (
          <Text variant="muted" className="text-sm">Click a node to highlight its path</Text>
        )}
        <div className="flex items-center gap-4 text-xs ml-auto">
          {Object.entries(KIND_CONFIG).map(([key, { color, label }]) => (
            showFilters ? (
              <button
                key={key}
                type="button"
                onClick={() => toggleKind(key)}
                className={`flex items-center gap-1.5 rounded px-1.5 py-0.5 transition-opacity ${visibleKinds[key] !== false ? 'opacity-100' : 'opacity-40'}`}
                title={visibleKinds[key] === false ? 'Show' : 'Hide'}
              >
                <LegendItem color={color} label={label} />
              </button>
            ) : (
              <LegendItem key={key} color={color} label={label} />
            )
          ))}
        </div>
      </div>
    </header>
  )
}
