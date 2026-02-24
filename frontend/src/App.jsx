import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Routes, Route, useNavigate, useLocation, useParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import { useNodesState, useEdgesState } from 'reactflow'
import GraphLayout from './components/templates/GraphLayout'
import ProjectsList from './pages/ProjectsList'
import ProjectDetail from './pages/ProjectDetail'
import NewProjectForm from './pages/NewProjectForm'
import { getPathToNodeIds, getPathFromNodeIds, parseGraph } from './lib/graphUtils'
import { fetchProjectGraph } from './lib/api'
import { KIND_CONFIG } from './constants'

const emptyGraph = { nodes: [], edges: [] }

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

  const [nodes, setNodes, onNodesChange] = useNodesState(emptyGraph.nodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(emptyGraph.edges)
  const [graphLoading, setGraphLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selectedNodeId, setSelectedNodeId] = useState(null)
  const [visibleKinds, setVisibleKinds] = useState(() =>
    Object.keys(KIND_CONFIG).reduce((acc, k) => ({ ...acc, [k]: true }), {})
  )
  const [searchQuery, setSearchQuery] = useState('')
  const graphLayoutRef = useRef(null)

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

  const highlightedIds = useMemo(() => {
    if (!selectedNodeId) return new Set()
    const upstream = getPathToNodeIds(selectedNodeId, filteredEdges)
    const downstream = getPathFromNodeIds(selectedNodeId, filteredEdges)
    return new Set([...upstream, ...downstream])
  }, [selectedNodeId, filteredEdges])

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

  const nodesWithHighlight = useMemo(() => {
    return filteredNodes.map((n) => {
      if (n.type === 'clusterBg') {
        return { ...n, data: { ...n.data, dimmed: false, pathHighlight: false } }
      }
      return {
        ...n,
        data: {
          ...n.data,
          dimmed: selectedNodeId != null ? !highlightedIds.has(n.id) : false,
          pathHighlight: selectedNodeId != null && highlightedIds.has(n.id),
        },
        style: selectedNodeId != null ? { ...n.style, opacity: highlightedIds.has(n.id) ? 1 : 0.2, transition: 'opacity 0.2s ease' } : n.style,
      }
    })
  }, [filteredNodes, selectedNodeId, highlightedIds])

  const edgesWithHighlight = useMemo(() => {
    if (selectedNodeId == null) return filteredEdges
    return filteredEdges.map((e) => {
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
  }, [filteredEdges, selectedNodeId, highlightedIds])

  const onNodeClick = useCallback((_, node) => {
    if (node.type === 'clusterBg') {
      setSelectedNodeId(null)
      return
    }
    setSelectedNodeId((prev) => (prev === node.id ? null : node.id))
  }, [])

  const onPaneClick = useCallback(() => {
    setSelectedNodeId(null)
    setSearchQuery('')
  }, [])
  const onEdgeClick = useCallback(() => {
    setSelectedNodeId(null)
    setSearchQuery('')
  }, [])
  const onClearPath = useCallback(() => {
    setSelectedNodeId(null)
    setSearchQuery('')
  }, [])

  const selectedNode = useMemo(
    () => (selectedNodeId ? nodes.find((n) => n.id === selectedNodeId) : null),
    [nodes, selectedNodeId]
  )

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
      })
      .catch((e) => {
        toast.error(e.message || 'Failed to load graph')
      })
      .finally(() => setGraphLoading(false))
  }, [graphProjectIdFromRoute])

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
    error,
    selectedNode,
    onExport,
    visibleKinds,
    setVisibleKinds,
    searchQuery,
    setSearchQuery,
    searchMatches,
    onSearchSelect,
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
