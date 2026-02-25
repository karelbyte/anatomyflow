import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Routes, Route, useNavigate, useLocation, useParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import { useNodesState, useEdgesState, applyNodeChanges } from 'reactflow'
import GraphLayout from './components/templates/GraphLayout'
import ProjectsList from './pages/ProjectsList'
import ProjectDetail from './pages/ProjectDetail'
import NewProjectForm from './pages/NewProjectForm'
import { toPng } from 'html-to-image'
import { getPathToNodeIds, getPathFromNodeIds, getCycleThroughNode, getUpstreamDistances, getDownstreamDistances, parseGraph, getLayoutedElements } from './lib/graphUtils'
import { fetchProjectGraph, fetchGraphUIState, updateGraphUIState } from './lib/api'
import { KIND_CONFIG } from './constants'

const emptyGraph = { nodes: [], edges: [] }
const CRITICAL_NODE_THRESHOLD = 3 // fanIn or fanOut >= this → "critical" (many connections)

function matchSearch(node, query) {
  if (!query || !node?.data) return false
  const q = query.toLowerCase().trim()
  const label = (node.data.label || '').toLowerCase()
  const path = (node.data.file_path || '').toLowerCase()
  return label.includes(q) || path.includes(q)
}

function ProjectDetailRoute() {
  const { id } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const stepParam = new URLSearchParams(location.search || '').get('step')
  return (
    <ProjectDetail
      projectId={id}
      onBack={() => navigate('/')}
      onOpenGraph={(graph) => navigate(`/projects/${id}/graph`, { state: { graph } })}
      initialStep={stepParam}
    />
  )
}

const GraphLayoutRoute = React.forwardRef(function GraphLayoutRoute(props, ref) {
  const { id } = useParams()
  const navigate = useNavigate()
  const loading = props.graphLoading
  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <p className="text-surface-muted">Loading graph…</p>
      </div>
    )
  }
  return (
    <GraphLayout
      {...props}
      ref={ref}
      projectId={id}
      onBack={() => navigate(`/projects/${id}`)}
    />
  )
})

function App() {
  const navigate = useNavigate()
  const location = useLocation()
  const pathname = location.pathname || ''
  const graphProjectIdFromRoute = useMemo(() => {
    const m = pathname.match(/^\/projects\/([^/]+)\/graph$/)
    return m ? m[1] : null
  }, [pathname])

  const [nodes, setNodes, onNodesChangeBase] = useNodesState(emptyGraph.nodes)
  const onNodesChange = useCallback(
    (changes) => {
      setNodes((oldNodes) => {
        const next = applyNodeChanges(changes, oldNodes)
        const clusterChange = changes.find(
          (c) => c.type === 'position' && c.id?.startsWith('cluster-bg-') && c.position != null
        )
        if (!clusterChange) return next
        const clusterId = clusterChange.id
        const newPos = clusterChange.position
        const oldClusterNode = oldNodes.find((n) => n.id === clusterId)
        if (!oldClusterNode) return next
        const delta = {
          x: newPos.x - oldClusterNode.position.x,
          y: newPos.y - oldClusterNode.position.y,
        }
        return next.map((n) =>
          n.data?.clusterId === clusterId
            ? { ...n, position: { x: n.position.x + delta.x, y: n.position.y + delta.y } }
            : n
        )
      })
    },
    [setNodes]
  )
  const [edges, setEdges, onEdgesChange] = useEdgesState(emptyGraph.edges)
  const [graphLoading, setGraphLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selectedNodeId, setSelectedNodeId] = useState(null)
  const [lockedPathNodeId, setLockedPathNodeId] = useState(null)
  const [hidePathHighlight, setHidePathHighlight] = useState(false)
  const [visibleKinds, setVisibleKinds] = useState(() =>
    Object.keys(KIND_CONFIG).reduce((acc, k) => ({ ...acc, [k]: true }), {})
  )
  const [searchQuery, setSearchQuery] = useState('')
  const [layoutMode, setLayoutMode] = useState('stored') // 'stored' = circular (backend), 'cascade' = jerárquico (front)
  const graphLayoutRef = useRef(null)
  const graphContainerRef = useRef(null)
  const skipNextUISaveRef = useRef(false)
  const savePositionsTimeoutRef = useRef(null)

  const projectKinds = useMemo(() => {
    const set = new Set(nodes.map((n) => n.data?.kind).filter(Boolean))
    return set.size > 0 ? [...set] : Object.keys(KIND_CONFIG)
  }, [nodes])

  useEffect(() => {
    if (projectKinds.length === 0 || projectKinds.length === Object.keys(KIND_CONFIG).length) return
    setVisibleKinds(projectKinds.reduce((acc, k) => ({ ...acc, [k]: true }), {}))
  }, [projectKinds])

  const filteredNodes = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    return nodes.filter((n) => {
      if (n.type === 'clusterBg') return true
      const kind = n.data?.kind
      if (kind && visibleKinds[kind] === false) return false
      if (!q) return true
      return matchSearch(n, searchQuery)
    })
  }, [nodes, visibleKinds, searchQuery])

  const visibleIds = useMemo(() => new Set(filteredNodes.map((n) => n.id)), [filteredNodes])

  const filteredEdges = useMemo(
    () => edges.filter((e) => visibleIds.has(e.source) && visibleIds.has(e.target)),
    [edges, visibleIds]
  )

  const displayNodes = useMemo(() => {
    if (layoutMode !== 'cascade') return filteredNodes
    const { nodes: layouted } = getLayoutedElements(filteredNodes, filteredEdges, 'TB')
    return layouted
  }, [layoutMode, filteredNodes, filteredEdges])

  const displayEdges = useMemo(() => {
    if (layoutMode !== 'cascade') return filteredEdges
    const { edges: layouted } = getLayoutedElements(filteredNodes, filteredEdges, 'TB')
    return layouted
  }, [layoutMode, filteredNodes, filteredEdges])

  const pathSourceId = lockedPathNodeId ?? selectedNodeId
  const cycleNodeIds = useMemo(
    () => (pathSourceId ? getCycleThroughNode(pathSourceId, filteredEdges) : null),
    [pathSourceId, filteredEdges]
  )
  const fanInFanOut = useMemo(() => {
    if (!pathSourceId || !filteredEdges.length) return null
    let fanIn = 0
    let fanOut = 0
    for (const e of filteredEdges) {
      if (e.target === pathSourceId) fanIn++
      if (e.source === pathSourceId) fanOut++
    }
    return { fanIn, fanOut }
  }, [pathSourceId, filteredEdges])

  const pathDistances = useMemo(() => {
    if (!pathSourceId || !filteredEdges.length || !nodes.length) return null
    const up = getUpstreamDistances(pathSourceId, filteredEdges)
    const down = getDownstreamDistances(pathSourceId, filteredEdges)
    const byId = (id) => nodes.find((n) => n.id === id)?.data?.label || id
    return {
      upstream: [...up.entries()].map(([id, d]) => ({ id, label: byId(id), distance: d })).sort((a, b) => a.distance - b.distance),
      downstream: [...down.entries()].map(([id, d]) => ({ id, label: byId(id), distance: d })).sort((a, b) => a.distance - b.distance),
    }
  }, [pathSourceId, filteredEdges, nodes])

  const highlightedIds = useMemo(() => {
    if (!pathSourceId) return new Set()
    const upstream = getPathToNodeIds(pathSourceId, filteredEdges)
    const downstream = getPathFromNodeIds(pathSourceId, filteredEdges)
    return new Set([...upstream, ...downstream])
  }, [pathSourceId, filteredEdges])

  const pathEdgeReasons = useMemo(() => {
    if (!highlightedIds?.size || !filteredEdges.length || !nodes.length) return null
    const byId = (id) => nodes.find((n) => n.id === id)?.data?.label || id
    return filteredEdges
      .filter((e) => highlightedIds.has(e.source) && highlightedIds.has(e.target))
      .map((e) => ({ from: byId(e.source), to: byId(e.target), relation: e.data?.relation || e.label || 'uses' }))
  }, [highlightedIds, filteredEdges, nodes])

  const pathOrder = useMemo(() => {
    if (!pathDistances || !pathSourceId) return []
    const up = pathDistances.upstream.map((u) => u.id).reverse()
    const down = pathDistances.downstream.map((d) => d.id)
    return [...up, pathSourceId, ...down]
  }, [pathDistances, pathSourceId])


  const pathNodesWithCode = useMemo(() => {
    if (!highlightedIds?.size || !nodes.length) return []
    return nodes
      .filter((n) => n.id && highlightedIds.has(n.id) && n.type !== 'clusterBg' && (n.data?.code || ''))
      .map((n) => ({ id: n.id, label: n.data?.label || n.id, code: n.data?.code || '' }))
  }, [highlightedIds, nodes])

  const searchMatches = useMemo(
    () => filteredNodes.filter((n) => n.type !== 'clusterBg' && matchSearch(n, searchQuery)),
    [filteredNodes, searchQuery]
  )

  useEffect(() => {
    if (!searchQuery?.trim() || !searchMatches?.length) return
    const t = setTimeout(() => {
      const nodeOpts = searchMatches.map((n) => ({ id: n.id }))
      requestAnimationFrame(() => {
        graphLayoutRef.current?.fitView?.({
          nodes: nodeOpts,
          padding: 0.2,
          duration: 300,
        })
      })
    }, 500)
    return () => clearTimeout(t)
  }, [searchQuery, searchMatches])

  useEffect(() => {
    if (layoutMode !== 'cascade') return
    const t = setTimeout(() => {
      requestAnimationFrame(() => {
        graphLayoutRef.current?.fitView?.({ padding: 0.2, duration: 300 })
      })
    }, 50)
    return () => clearTimeout(t)
  }, [layoutMode])

  const nodeMetrics = useMemo(() => {
    const m = {}
    for (const n of nodes) {
      if (n.type === 'clusterBg' || !n.id) continue
      m[n.id] = { fanIn: 0, fanOut: 0 }
    }
    for (const e of filteredEdges) {
      if (m[e.target]) m[e.target].fanIn++
      if (m[e.source]) m[e.source].fanOut++
    }
    for (const id of Object.keys(m)) {
      const fanIn = m[id].fanIn
      const fanOut = m[id].fanOut
      m[id].isEntry = fanIn === 0
      m[id].isLeaf = fanOut === 0
      m[id].isCritical = fanIn >= CRITICAL_NODE_THRESHOLD || fanOut >= CRITICAL_NODE_THRESHOLD
    }
    return m
  }, [nodes, filteredEdges])

  const pathVisible = pathSourceId != null && !hidePathHighlight
  const nodesWithHighlight = useMemo(() => {
    const draggable = layoutMode === 'stored'
    return displayNodes.map((n) => {
      if (n.type === 'clusterBg') {
        return { ...n, draggable, data: { ...n.data, dimmed: false, pathHighlight: false } }
      }
      const metrics = nodeMetrics[n.id] || {}
      return {
        ...n,
        draggable,
        data: {
          ...n.data,
          ...metrics,
          dimmed: pathVisible ? !highlightedIds.has(n.id) : false,
          pathHighlight: pathVisible && highlightedIds.has(n.id),
        },
        style: pathVisible ? { ...n.style, opacity: highlightedIds.has(n.id) ? 1 : 0.2, transition: 'opacity 0.2s ease' } : n.style,
      }
    })
  }, [layoutMode, displayNodes, pathVisible, highlightedIds, nodeMetrics])

  const edgesWithHighlight = useMemo(() => {
    if (!pathVisible) return displayEdges
    return displayEdges.map((e) => {
      const inPath = highlightedIds.has(e.source) && highlightedIds.has(e.target)
      return {
        ...e,
        style: {
          ...e.style,
          opacity: inPath ? 1 : 0.18,
          strokeWidth: inPath ? 2.5 : 1.5,
          transition: 'opacity 0.2s ease, stroke-width 0.2s ease',
        },
        labelStyle: { ...e.labelStyle, opacity: inPath ? 1 : 0.18 },
      }
    })
  }, [displayEdges, pathVisible, highlightedIds])

  const onNodeClick = useCallback((_, node) => {
    if (node.type === 'clusterBg') {
      setSelectedNodeId(null)
      return
    }
    setSelectedNodeId((prev) => (prev === node.id ? null : node.id))
  }, [])

  const onPaneClick = useCallback(() => {
    if (!lockedPathNodeId) setSelectedNodeId(null)
    setSearchQuery('')
  }, [lockedPathNodeId])
  const onEdgeClick = useCallback(() => {
    if (!lockedPathNodeId) setSelectedNodeId(null)
    setSearchQuery('')
  }, [lockedPathNodeId])
  const onClearPath = useCallback(() => {
    setSelectedNodeId(null)
    setLockedPathNodeId(null)
    setSearchQuery('')
  }, [])
  const isGraphView = pathname === '/graph' || /^\/projects\/[^/]+\/graph$/.test(pathname)
  useEffect(() => {
    if (!isGraphView) return
    const onKeyDown = (e) => {
      if (e.key === 'Escape') {
        onClearPath()
        e.preventDefault()
        return
      }
      if (pathOrder.length === 0) return
      const current = selectedNodeId ?? pathSourceId
      const idx = pathOrder.indexOf(current)
      if (idx === -1) return
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
        const next = pathOrder[idx + 1]
        if (next) {
          setSelectedNodeId(next)
          e.preventDefault()
        }
      } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
        const prev = pathOrder[idx - 1]
        if (prev) {
          setSelectedNodeId(prev)
          e.preventDefault()
        }
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [isGraphView, pathOrder, selectedNodeId, pathSourceId, onClearPath])
  const onToggleLockPath = useCallback(() => {
    setLockedPathNodeId((prev) => {
      if (prev != null) return null
      return selectedNodeId ?? prev
    })
  }, [selectedNodeId])

  const selectedNode = useMemo(
    () => (selectedNodeId ? nodes.find((n) => n.id === selectedNodeId) : null),
    [nodes, selectedNodeId]
  )

  const relatedNodesForSelected = useMemo(() => {
    if (!selectedNodeId) return []
    const byId = (id) => nodes.find((n) => n.id === id)
    const map = new Map()
    for (const e of filteredEdges) {
      if (e.source === selectedNodeId && e.target !== selectedNodeId) {
        const n = byId(e.target)
        if (!n) continue
        const prev = map.get(n.id) || { id: n.id, label: n.data?.label || n.id, incoming: false, outgoing: false }
        prev.outgoing = true
        map.set(n.id, prev)
      }
      if (e.target === selectedNodeId && e.source !== selectedNodeId) {
        const n = byId(e.source)
        if (!n) continue
        const prev = map.get(n.id) || { id: n.id, label: n.data?.label || n.id, incoming: false, outgoing: false }
        prev.incoming = true
        map.set(n.id, prev)
      }
    }
    return Array.from(map.values()).sort((a, b) => a.label.localeCompare(b.label))
  }, [selectedNodeId, nodes, filteredEdges])

  const modelAndTableNames = useMemo(() => {
    const out = []
    const seen = new Set()
    for (const n of nodes) {
      if (n.type === 'clusterBg' || !n.id) continue
      const kind = (n.data?.kind || '').toLowerCase()
      if (kind !== 'model' && kind !== 'table') continue
      const label = n.data?.label || (n.id.includes(':') ? n.id.split(':')[1] : n.id)
      if (label && !seen.has(label)) {
        seen.add(label)
        out.push(label)
      }
    }
    return out
  }, [nodes])

  const onFileSelect = useCallback((e) => {
    const file = e.target?.files?.[0]
    if (!file) return
    setError(null)
    setSelectedNodeId(null)
    const reader = new FileReader()
    reader.onload = (ev) => {
      try {
        const graph = parseGraph(ev.target.result)
        setNodes(graph.nodes)
        setEdges(graph.edges)
        navigate('/graph')
        toast.success('Graph loaded')
      } catch {
        setError('Invalid JSON graph file.')
        toast.error('Invalid JSON graph file.')
      }
    }
    reader.readAsText(file)
  }, [setNodes, setEdges, navigate])

  const onExport = useCallback(() => {
    const projectId = graphProjectIdFromRoute || 'export'
    const blob = new Blob([JSON.stringify({ nodes, edges }, null, 2)], { type: 'application/json' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `graph-${projectId}-${Date.now()}.json`
    a.click()
    URL.revokeObjectURL(a.href)
    toast.success('Graph exported')
  }, [nodes, edges, graphProjectIdFromRoute])

  const pathHasNodes = highlightedIds?.size > 0
  const onExportPathJson = useCallback(() => {
    if (!pathHasNodes) return
    const pathNodes = nodes.filter((n) => n.id && highlightedIds.has(n.id) && n.type !== 'clusterBg')
    const pathEdges = filteredEdges.filter((e) => highlightedIds.has(e.source) && highlightedIds.has(e.target))
    const payload = {
      pathSourceId,
      exportedAt: new Date().toISOString(),
      nodes: pathNodes.map((n) => ({ id: n.id, data: n.data, position: n.position })),
      edges: pathEdges.map((e) => ({ source: e.source, target: e.target, data: e.data })),
    }
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `path-${pathSourceId || 'export'}-${Date.now()}.json`
    a.click()
    URL.revokeObjectURL(a.href)
    toast.success('Path exported as JSON')
  }, [pathHasNodes, pathSourceId, nodes, filteredEdges, highlightedIds])

  const onExportPathImage = useCallback(() => {
    if (!pathHasNodes || !graphContainerRef.current) return
    const pathNodeIds = Array.from(highlightedIds)
    graphLayoutRef.current?.fitView?.({ nodes: pathNodeIds.map((id) => ({ id })), padding: 0.3, duration: 300 })
    setTimeout(() => {
      const flowEl = graphContainerRef.current.querySelector('.react-flow')
      const target = flowEl || graphContainerRef.current
      // Force inline SVG attributes on edge paths so html-to-image clone shows them (cloned DOM often loses CSS for SVG)
      const edgePaths = target.querySelectorAll('.react-flow__edge-path, .react-flow__connection-path')
      const restores = []
      edgePaths.forEach((path) => {
        const origStroke = path.getAttribute('stroke')
        const origSw = path.getAttribute('stroke-width')
        const origFill = path.getAttribute('fill')
        restores.push({ path, origStroke, origSw, origFill })
        const stroke = origStroke || getComputedStyle(path).stroke
        const sw = (origSw || getComputedStyle(path).strokeWidth || '2').toString().replace('px', '')
        const fill = origFill || getComputedStyle(path).fill
        path.setAttribute('stroke', stroke && stroke !== 'none' ? stroke : '#a1a1aa')
        path.setAttribute('stroke-width', sw || '2')
        path.setAttribute('fill', fill && fill !== 'none' ? fill : 'none')
      })
      toPng(target, { pixelRatio: 2, backgroundColor: '#18181b' })
        .then((dataUrl) => {
          restores.forEach(({ path, origStroke, origSw, origFill }) => {
            if (origStroke != null) path.setAttribute('stroke', origStroke)
            else path.removeAttribute('stroke')
            if (origSw != null) path.setAttribute('stroke-width', origSw)
            else path.removeAttribute('stroke-width')
            if (origFill != null) path.setAttribute('fill', origFill)
            else path.removeAttribute('fill')
          })
          const a = document.createElement('a')
          a.href = dataUrl
          a.download = `path-${pathSourceId || 'export'}-${Date.now()}.png`
          a.click()
          toast.success('Path exported as image')
        })
        .catch(() => {
          restores.forEach(({ path, origStroke, origSw, origFill }) => {
            if (origStroke != null) path.setAttribute('stroke', origStroke)
            else path.removeAttribute('stroke')
            if (origSw != null) path.setAttribute('stroke-width', origSw)
            else path.removeAttribute('stroke-width')
            if (origFill != null) path.setAttribute('fill', origFill)
            else path.removeAttribute('fill')
          })
          toast.error('Failed to export image')
        })
    }, 500)
  }, [pathHasNodes, pathSourceId, highlightedIds])

  useEffect(() => {
    if (!graphProjectIdFromRoute) return
    if (location.state?.graph) {
      try {
        const { nodes: n, edges: e } = parseGraph(location.state.graph)
        setNodes(n)
        setEdges(e)
      } catch {
        toast.error('Invalid graph in state')
      }
      setGraphLoading(false)
      return
    }
    setNodes(emptyGraph.nodes)
    setEdges(emptyGraph.edges)
    setGraphLoading(true)
    fetchProjectGraph(graphProjectIdFromRoute)
      .then((apiGraph) => {
        const { nodes: n, edges: e } = parseGraph(apiGraph)
        setNodes(n)
        setEdges(e)
        return fetchGraphUIState(graphProjectIdFromRoute).then((uiState) => {
          if (!uiState || Object.keys(uiState).length === 0) return
          const positions = uiState.node_positions || {}
          const nodesWithPositions = n.map((node) => {
            const pos = positions[node.id]
            return pos ? { ...node, position: pos } : node
          })
          setNodes(nodesWithPositions)
          if (uiState.layout_mode === 'cascade' || uiState.layout_mode === 'stored') {
            setLayoutMode(uiState.layout_mode)
          }
          if (uiState.selected_node_id != null && uiState.selected_node_id !== '') {
            setSelectedNodeId(uiState.selected_node_id)
          }
          if (uiState.path_locked && uiState.selected_node_id) {
            setLockedPathNodeId(uiState.selected_node_id)
          } else {
            setLockedPathNodeId(null)
          }
          skipNextUISaveRef.current = true
        })
      })
      .catch((e) => {
        if (e?.message?.includes('No graph')) toast.error(e.message)
        else toast.error(e?.message || 'Failed to load graph')
      })
      .finally(() => setGraphLoading(false))
  }, [graphProjectIdFromRoute])

  useEffect(() => {
    if (!graphProjectIdFromRoute) return
    if (skipNextUISaveRef.current) {
      skipNextUISaveRef.current = false
      return
    }
    updateGraphUIState(graphProjectIdFromRoute, {
      selected_node_id: selectedNodeId || null,
      path_locked: lockedPathNodeId != null,
      layout_mode: layoutMode,
    }).catch(() => {})
  }, [graphProjectIdFromRoute, selectedNodeId, layoutMode, lockedPathNodeId])

  useEffect(() => {
    if (!graphProjectIdFromRoute || layoutMode !== 'stored' || nodes.length === 0) return
    if (savePositionsTimeoutRef.current) clearTimeout(savePositionsTimeoutRef.current)
    savePositionsTimeoutRef.current = setTimeout(() => {
      const node_positions = {}
      nodes.forEach((n) => {
        if (n.id && n.type !== 'clusterBg' && n.position) {
          node_positions[n.id] = { x: n.position.x, y: n.position.y }
        }
      })
      if (Object.keys(node_positions).length > 0) {
        updateGraphUIState(graphProjectIdFromRoute, { node_positions }).catch(() => {})
      }
      savePositionsTimeoutRef.current = null
    }, 600)
    return () => {
      if (savePositionsTimeoutRef.current) clearTimeout(savePositionsTimeoutRef.current)
    }
  }, [graphProjectIdFromRoute, layoutMode, nodes])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const projectId = params.get('project_id')
    const connected = params.get('github_connected')
    const err = params.get('github_error')
    if (err) {
      toast.error(decodeURIComponent(err))
      window.history.replaceState({}, '', window.location.pathname || '/')
      return
    }
    if (connected === '1' && projectId) {
      navigate(`/projects/${projectId}`, { replace: true })
      toast.success('GitHub account connected. You can run analysis on private repos.')
      window.history.replaceState({}, '', window.location.pathname || '/')
    }
  }, [navigate])

  const onSearchSelect = useCallback((id, node) => {
    setSelectedNodeId(id)
    setSearchQuery('')
    const upstream = getPathToNodeIds(id, edges)
    const downstream = getPathFromNodeIds(id, edges)
    const pathIds = [...new Set([...upstream, ...downstream])]
    setTimeout(() => {
      graphLayoutRef.current?.fitView?.({
        nodes: pathIds.map((nid) => ({ id: nid })),
        padding: 0.2,
        duration: 300,
      })
    }, 80)
  }, [edges])

  const commonGraphProps = {
    layoutMode,
    setLayoutMode,
    nodes,
    edges: filteredEdges,
    nodesWithHighlight,
    edgesWithHighlight,
    onNodesChange,
    onEdgesChange,
    onNodeClick,
    onPaneClick,
    onEdgeClick,
    onFileSelect,
    selectedNodeId,
    onClearPath,
    pathLocked: lockedPathNodeId != null,
    onToggleLockPath,
    hidePathHighlight,
    onToggleHidePathHighlight: () => setHidePathHighlight((v) => !v),
    error,
    selectedNode,
    nodeMetrics,
    relatedNodesForSelected,
    modelAndTableNames,
    cycleNodeIds,
    fanInFanOut,
    pathDistances,
    pathEdgeReasons,
    pathNodesWithCode,
    onExport,
    visibleKinds,
    setVisibleKinds,
    projectKinds,
    searchQuery,
    setSearchQuery,
    searchMatches,
    onSearchSelect,
    graphContainerRef,
    pathHasNodes,
    onExportPathJson,
    onExportPathImage,
  }

  return (
    <Routes>
      <Route
        path="/"
        element={
          <ProjectsList
            onNewProject={() => navigate('/projects/new')}
            onOpenAnalysis={(id) => navigate(`/projects/${id}`)}
            onViewGraph={(id) => navigate(`/projects/${id}/graph`)}
          />
        }
      />
      <Route
        path="/projects/new"
        element={
          <NewProjectForm
            onCreated={(id) => navigate(`/projects/${id}`)}
            onCancel={() => navigate('/')}
          />
        }
      />
      <Route path="/projects/:id" element={<ProjectDetailRoute />} />
      <Route
        path="/projects/:id/graph"
        element={
          <GraphLayoutRoute
            {...commonGraphProps}
            graphLoading={graphLoading}
            ref={graphLayoutRef}
          />
        }
      />
      <Route
        path="/graph"
        element={
          <GraphLayout
            {...commonGraphProps}
            projectId={null}
            onBack={undefined}
            ref={graphLayoutRef}
          />
        }
      />
    </Routes>
  )
}

export default App
