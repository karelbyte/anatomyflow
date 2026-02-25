import dagre from 'dagre'
import { MarkerType } from 'reactflow'

const NODE_WIDTH = 200
const NODE_HEIGHT = 85

/**
 * Layout en cascada (jerárquico) con dagre. Excluye nodos clusterBg.
 * @param {import('reactflow').Node[]} nodes
 * @param {import('reactflow').Edge[]} edges
 * @param {'TB'|'LR'} direction - TB = top-bottom (cascada), LR = left-right
 * @returns {{ nodes: import('reactflow').Node[], edges: import('reactflow').Edge[] }}
 */
export function getLayoutedElements(nodes, edges, direction = 'TB') {
  const realNodes = (nodes || []).filter((n) => n.type !== 'clusterBg' && n.id)
  const ids = new Set(realNodes.map((n) => n.id))
  const realEdges = (edges || []).filter((e) => ids.has(e.source) && ids.has(e.target))
  if (realNodes.length === 0) return { nodes: realNodes, edges: realEdges }

  const g = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: direction, nodesep: 60, ranksep: 80 })

  realNodes.forEach((n) => g.setNode(n.id, { width: NODE_WIDTH, height: NODE_HEIGHT }))
  realEdges.forEach((e) => g.setEdge(e.source, e.target))

  dagre.layout(g)

  const layoutedNodes = realNodes.map((n) => {
    const pos = g.node(n.id)
    return {
      ...n,
      position: {
        x: pos.x - NODE_WIDTH / 2,
        y: pos.y - NODE_HEIGHT / 2,
      },
    }
  })
  return { nodes: layoutedNodes, edges: realEdges }
}

/** Returns Map of nodeId -> distance (steps) for all nodes that can reach nodeId (upstream). */
export function getUpstreamDistances(nodeId, edges) {
  if (!nodeId || !edges?.length) return new Map()
  const incoming = new Map()
  for (const e of edges) {
    if (!incoming.has(e.target)) incoming.set(e.target, [])
    incoming.get(e.target).push(e.source)
  }
  const dist = new Map([[nodeId, 0]])
  const queue = [nodeId]
  while (queue.length) {
    const cur = queue.shift()
    const d = dist.get(cur) ?? 0
    for (const prev of incoming.get(cur) || []) {
      if (!dist.has(prev)) {
        dist.set(prev, d + 1)
        queue.push(prev)
      }
    }
  }
  dist.delete(nodeId)
  return dist
}

/** Returns Map of nodeId -> distance (steps) for all nodes reachable from nodeId (downstream). */
export function getDownstreamDistances(nodeId, edges) {
  if (!nodeId || !edges?.length) return new Map()
  const outgoing = new Map()
  for (const e of edges) {
    if (!outgoing.has(e.source)) outgoing.set(e.source, [])
    outgoing.get(e.source).push(e.target)
  }
  const dist = new Map([[nodeId, 0]])
  const queue = [nodeId]
  while (queue.length) {
    const cur = queue.shift()
    const d = dist.get(cur) ?? 0
    for (const next of outgoing.get(cur) || []) {
      if (!dist.has(next)) {
        dist.set(next, d + 1)
        queue.push(next)
      }
    }
  }
  dist.delete(nodeId)
  return dist
}

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

/**
 * Finds a cycle that contains nodeId (if any). Returns array of node ids [nodeId, ..., nodeId] or null.
 */
export function getCycleThroughNode(nodeId, edges) {
  if (!nodeId || !edges?.length) return null
  const outgoing = new Map()
  for (const e of edges) {
    if (!outgoing.has(e.source)) outgoing.set(e.source, [])
    outgoing.get(e.source).push(e.target)
  }
  const path = [nodeId]
  const visited = new Set([nodeId])

  function dfs(cur) {
    for (const next of outgoing.get(cur) || []) {
      if (next === nodeId && path.length >= 2) return path.concat(nodeId)
      if (!visited.has(next)) {
        visited.add(next)
        path.push(next)
        const result = dfs(next)
        if (result) return result
        path.pop()
        visited.delete(next)
      }
    }
    return null
  }
  return dfs(nodeId)
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
      draggable: true,
      ...(type === 'anatomy' && { dragHandle: '.anatomy-drag-handle' }),
      ...(type === 'clusterBg' && { dragHandle: '.cluster-drag-handle' }),
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
