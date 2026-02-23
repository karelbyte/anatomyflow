import { MarkerType } from 'reactflow'

/** Nodos que tienen camino hacia nodeId (dependencias / upstream). */
export function getPathToNodeIds(nodeId, edges) {
  if (!nodeId || !edges?.length) return new Set([nodeId])
  const incoming = new Map()
  for (const e of edges) {
    if (!incoming.has(e.target)) incoming.set(e.target, [])
    incoming.get(e.target).push(e.source)
  }
  const out = new Set([nodeId])
  const queue = [nodeId]
  while (queue.length) {
    const cur = queue.shift()
    for (const prev of incoming.get(cur) || []) {
      if (!out.has(prev)) {
        out.add(prev)
        queue.push(prev)
      }
    }
  }
  return out
}

/** Nodos alcanzables desde nodeId siguiendo aristas (dependientes / downstream = impacto). */
export function getPathFromNodeIds(nodeId, edges) {
  if (!nodeId || !edges?.length) return new Set([nodeId])
  const outgoing = new Map()
  for (const e of edges) {
    if (!outgoing.has(e.source)) outgoing.set(e.source, [])
    outgoing.get(e.source).push(e.target)
  }
  const out = new Set([nodeId])
  const queue = [nodeId]
  while (queue.length) {
    const cur = queue.shift()
    for (const next of outgoing.get(cur) || []) {
      if (!out.has(next)) {
        out.add(next)
        queue.push(next)
      }
    }
  }
  return out
}

export function parseGraph(json) {
  const data = typeof json === 'string' ? JSON.parse(json) : json
  const nodes = (data.nodes || []).map((n) => {
    const type = n.type === 'clusterBg' ? 'clusterBg' : n.type === 'default' ? 'anatomy' : (n.type || 'anatomy')
    return {
      ...n,
      type,
      draggable: type !== 'clusterBg',
      ...(type === 'anatomy' && { dragHandle: '.anatomy-drag-handle' }),
      data: { ...n.data, label: n.data?.label ?? n.id },
    }
  })
  const edges = (data.edges || []).map((e, i) => ({
    id: e.id || `e${i}`,
    source: e.source,
    target: e.target,
    type: 'smoothstep',
    markerEnd: { type: MarkerType.ArrowClosed },
    label: e.data?.relation ?? e.label ?? '',
    labelStyle: { fill: '#adb5bd', fontSize: 11, fontWeight: 500 },
    labelBgStyle: { fill: '#25262b', fillOpacity: 0.95 },
    labelBgPadding: [6, 4],
    labelBgBorderRadius: 4,
    data: e.data || {},
  }))
  return { nodes, edges }
}
