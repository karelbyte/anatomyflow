import { memo } from 'react'
import { FiMove } from 'react-icons/fi'

function ClusterBg({ data }) {
  const w = Number(data?.width) || 400
  const h = Number(data?.height) || 200

  return (
    <div
      className="rounded-xl border border-zinc-600/80 bg-zinc-700/40 relative"
      style={{ width: w, height: h, pointerEvents: 'none' }}
    >
      <div
        className="cluster-drag-handle absolute top-0 right-0 w-8 h-8 flex items-center justify-center rounded-tr-xl rounded-bl-md bg-zinc-600/80 hover:bg-zinc-500/80 cursor-grab active:cursor-grabbing text-zinc-300 hover:text-white border-l border-b border-zinc-600/80"
        style={{ pointerEvents: 'auto' }}
        title="Drag to move whole group"
      >
        <FiMove className="w-4 h-4" />
      </div>
    </div>
  )
}

export default memo(ClusterBg)
