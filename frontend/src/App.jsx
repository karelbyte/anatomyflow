import { useCallback, useEffect, useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import { useNodesState, useEdgesState } from 'reactflow'
import GraphLayout from './components/templates/GraphLayout'
import ProjectsList from './pages/ProjectsList'
import ProjectDetail from './pages/ProjectDetail'
import NewProjectForm from './pages/NewProjectForm'
import { getPathToNodeIds, getPathFromNodeIds, parseGraph } from './lib/graphUtils'
import { fetchProjectGraph } from './lib/api'

const emptyGraph = { nodes: [], edges: [] }

function App() {
  const [view, setView] = useState('list')
  const [selectedProjectId, setSelectedProjectId] = useState(null)
  const [graphData, setGraphData] = useState(null)

  const [nodes, setNodes, onNodesChange] = useNodesState(emptyGraph.nodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(emptyGraph.edges)
  const [error, setError] = useState(null)
  const [selectedNodeId, setSelectedNodeId] = useState(null)

  const highlightedIds = useMemo(() => {
    if (!selectedNodeId) return new Set()
    const upstream = getPathToNodeIds(selectedNodeId, edges)
    const downstream = getPathFromNodeIds(selectedNodeId, edges)
    return new Set([...upstream, ...downstream])
  }, [selectedNodeId, edges])

  const nodesWithHighlight = useMemo(() => {
    return nodes.map((n) => {
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
  }, [nodes, selectedNodeId, highlightedIds])

  const edgesWithHighlight = useMemo(() => {
    if (selectedNodeId == null) return edges
    return edges.map((e) => {
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
  }, [edges, selectedNodeId, highlightedIds])

  const onNodeClick = useCallback((_, node) => {
    if (node.type === 'clusterBg') {
      setSelectedNodeId(null)
      return
    }
    setSelectedNodeId((prev) => (prev === node.id ? null : node.id))
  }, [])

  const onPaneClick = useCallback(() => setSelectedNodeId(null), [])
  const onEdgeClick = useCallback(() => setSelectedNodeId(null), [])
  const onClearPath = useCallback(() => setSelectedNodeId(null), [])

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
        setGraphData(null)
        setView('graph')
        toast.success('Graph loaded')
      } catch {
        setError('Invalid JSON graph file.')
        toast.error('Invalid JSON graph file.')
      }
    }
    reader.readAsText(file)
  }, [setNodes, setEdges])

  const onOpenGraph = useCallback((apiGraph) => {
    const { nodes: n, edges: e } = parseGraph(apiGraph)
    setNodes(n)
    setEdges(e)
    setGraphData(apiGraph)
    setView('graph')
  }, [setNodes, setEdges])

  const onViewGraph = useCallback((projectId) => {
    fetchProjectGraph(projectId)
      .then(onOpenGraph)
      .catch((e) => toast.error(e.message || 'Failed to load graph'))
  }, [onOpenGraph])

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
      setSelectedProjectId(projectId)
      setView('detail')
      toast.success('GitHub account connected. You can run analysis on private repos.')
      window.history.replaceState({}, '', window.location.pathname || '/')
    }
  }, [])

  if (view === 'list') {
    return (
      <ProjectsList
        onNewProject={() => setView('new')}
        onOpenAnalysis={(id) => {
          setSelectedProjectId(id)
          setView('detail')
        }}
        onViewGraph={onViewGraph}
      />
    )
  }

  if (view === 'new') {
    return (
      <NewProjectForm
        onCreated={(id) => {
          setSelectedProjectId(id)
          setView('detail')
        }}
        onCancel={() => setView('list')}
      />
    )
  }

  if (view === 'detail') {
    return (
      <ProjectDetail
        projectId={selectedProjectId}
        onBack={() => setView('list')}
        onOpenGraph={onOpenGraph}
      />
    )
  }

  return (
    <GraphLayout
      nodes={nodes}
      edges={edges}
      nodesWithHighlight={nodesWithHighlight}
      edgesWithHighlight={edgesWithHighlight}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onNodeClick={onNodeClick}
      onPaneClick={onPaneClick}
      onEdgeClick={onEdgeClick}
      onFileSelect={onFileSelect}
      selectedNodeId={selectedNodeId}
      onClearPath={onClearPath}
      error={error}
      selectedNode={selectedNode}
      onBack={graphData ? () => setView('detail') : undefined}
    />
  )
}

export default App
