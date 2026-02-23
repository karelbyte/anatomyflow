import { memo } from 'react'

function ClusterBg({ data }) {
  const w = Number(data?.width) || 400
  const h = Number(data?.height) || 200

  return (
    <div
      className="rounded-xl pointer-events-none border border-zinc-600/80 bg-zinc-700/40"
      style={{ width: w, height: h }}
    />
  )
}

export default memo(ClusterBg)
