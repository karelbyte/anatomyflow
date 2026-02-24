import { memo } from 'react'
import { Handle, Position } from 'reactflow'
import { getKindConfig } from '../../constants'
import Badge from '../atoms/Badge'

function AnatomyNode({ id, data, selected, nodeNotes }) {
  const kind = data?.kind || 'node'
  const config = getKindConfig(kind)
  const label = data?.label ?? ''
  const dimmed = data?.dimmed === true
  const pathHighlight = data?.pathHighlight === true
  const orphan = data?.orphan === true
  const notesCount = (nodeNotes && id && nodeNotes[id]) ? nodeNotes[id].length : 0
  const hasNotes = notesCount > 0

  const borderColor = pathHighlight ? '#fff' : selected ? '#fff' : config.border
  const shadow = pathHighlight
    ? `0 0 0 3px ${config.border}, 0 0 20px ${config.color}80`
    : selected
      ? `0 0 0 2px ${config.border}`
      : '0 2px 8px rgba(0,0,0,0.2)'

  return (
    <div
      className="relative flex items-stretch min-w-[140px] max-w-[280px] rounded-lg transition-all duration-200"
      style={{
        background: config.bg,
        border: `2px solid ${borderColor}`,
        borderStyle: orphan ? 'dashed' : 'solid',
        boxShadow: shadow,
        opacity: dimmed ? 0.2 : 1,
      }}
    >
      {hasNotes && (
        <span
          className="absolute -top-1 -right-1 flex items-center justify-center min-w-[18px] h-[18px] rounded-full bg-sky-500 text-white text-[10px] font-bold shadow z-10 border-2 border-zinc-800"
          title={`${notesCount} nota(s)`}
        >
          {notesCount > 9 ? '9+' : notesCount}
        </span>
      )}
      <Handle type="target" position={Position.Left} style={{ background: config.border }} />
      <div
        className="anatomy-drag-handle w-5 min-w-[20px] cursor-grab flex items-center justify-center rounded-l-md border-r"
        style={{ background: 'rgba(0,0,0,0.15)', borderColor: config.border }}
        title="Arrastra para mover"
      >
        <span className="text-[10px] tracking-wider" style={{ color: config.border }}>
          ⋮⋮
        </span>
      </div>
      <div className="flex-1 px-3 py-2.5">
        <div className="flex items-center gap-1.5 mb-1">
          <span
            className="text-[10px] font-semibold uppercase tracking-wider"
            style={{ color: config.color }}
          >
            {config.label}
          </span>
          {orphan && (
            <Badge variant="danger" title="Node with no dependencies or dependents in the graph">
              Orphan
            </Badge>
          )}
        </div>
        <div className="text-sm font-medium text-zinc-200 break-words" title={label}>
          {label}
        </div>
      </div>
      <Handle type="source" position={Position.Right} style={{ background: config.border }} />
    </div>
  )
}

export default memo(AnatomyNode)
