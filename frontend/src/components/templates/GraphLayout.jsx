import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react'
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
} from 'reactflow'
import 'reactflow/dist/style.css'
import { AppHeader, CodePanel, AnatomyNode, ClusterBg } from '../organisms'
import { KIND_CONFIG } from '../../constants'
import { fetchNodeCode, fetchNodeNotes, updateNodeNotes } from '../../lib/api'

const CODE_PANEL_MIN = 280
const CODE_PANEL_MAX_PERCENT = 0.7
const CODE_PANEL_DEFAULT = 420

const CODE_KINDS_FETCH = ['model', 'view', 'controller', 'route', 'page', 'api_route', 'component', 'express_route', 'middleware', 'service', 'module']

const GraphLayout = forwardRef(function GraphLayout({
  nodes,
  edges,
  nodesWithHighlight,
  edgesWithHighlight,
  onNodesChange,
  onEdgesChange,
  onNodeClick,
  onPaneClick,
  onEdgeClick,
  onFileSelect,
  onExport,
  selectedNodeId,
  onClearPath,
  error,
  selectedNode,
  projectId,
  onBack,
  visibleKinds,
  setVisibleKinds,
  searchQuery,
  setSearchQuery,
  searchMatches,
  onSearchSelect,
}, ref) {
  const [codePanelWidth, setCodePanelWidth] = useState(CODE_PANEL_DEFAULT)
  const containerRef = useRef(null)
  const reactFlowRef = useRef(null)
  const reactFlowInstanceRef = useRef(null)
  const isDragging = useRef(false)
  const [liveCode, setLiveCode] = useState(null)
  const [liveCodeLoading, setLiveCodeLoading] = useState(false)
  const [liveCodeError, setLiveCodeError] = useState(null)
  const [nodeNotes, setNodeNotes] = useState({})

  const nodeTypes = useMemo(() => ({
    anatomy: (props) => <AnatomyNode {...props} nodeNotes={nodeNotes} />,
    clusterBg: ClusterBg,
  }), [nodeNotes])

  useEffect(() => {
    if (!projectId) return
    fetchNodeNotes(projectId)
      .then((data) => setNodeNotes(data.notes || {}))
      .catch(() => setNodeNotes({}))
  }, [projectId])

  const onReactFlowInit = useCallback((instance) => {
    reactFlowInstanceRef.current = instance
  }, [])

  useImperativeHandle(ref, () => ({
    fitView: (opts) => {
      const instance = reactFlowInstanceRef.current || reactFlowRef.current
      instance?.fitView?.(opts)
    },
  }), [])

  const onResizeStart = useCallback((e) => {
    e.preventDefault()
    isDragging.current = true
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }, [])

  useEffect(() => {
    const handleMove = (e) => {
      if (!isDragging.current || !containerRef.current) return
      const rect = containerRef.current.getBoundingClientRect()
      const maxPx = rect.width * CODE_PANEL_MAX_PERCENT
      const newWidth = Math.round(rect.right - e.clientX)
      setCodePanelWidth(Math.max(CODE_PANEL_MIN, Math.min(maxPx, newWidth)))
    }
    const handleUp = () => {
      if (!isDragging.current) return
      isDragging.current = false
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
    document.addEventListener('mousemove', handleMove)
    document.addEventListener('mouseup', handleUp)
    return () => {
      document.removeEventListener('mousemove', handleMove)
      document.removeEventListener('mouseup', handleUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
  }, [])

  const kind = (selectedNode?.data?.kind || '').toLowerCase()
  const shouldFetchLive = projectId && selectedNodeId && CODE_KINDS_FETCH.includes(kind)

  useEffect(() => {
    if (!shouldFetchLive) {
      setLiveCode(null)
      setLiveCodeError(null)
      return
    }
    setLiveCodeLoading(true)
    setLiveCodeError(null)
    fetchNodeCode(projectId, selectedNodeId)
      .then(({ code, language, label, file_path }) => {
        setLiveCode({ code, language, label, file_path })
      })
      .catch((e) => {
        setLiveCodeError(e.message || 'Failed to load code')
        setLiveCode(null)
      })
      .finally(() => setLiveCodeLoading(false))
  }, [projectId, selectedNodeId, shouldFetchLive])

  const selectedCode = liveCode?.code ?? selectedNode?.data?.code ?? null
  const selectedLabel = liveCode?.label ?? (selectedNodeId ? selectedNode?.data?.label ?? selectedNodeId : null)
  const selectedFilePath = liveCode?.file_path ?? selectedNode?.data?.file_path ?? null
  const selectedCodeLanguage = liveCode?.language ?? (selectedNode?.data?.kind === 'table' ? 'sql' : (kind === 'view' ? 'blade' : 'php'))

  return (
    <div className="w-screen h-screen flex flex-col">
      <AppHeader
        onFileSelect={onFileSelect}
        onExport={onExport}
        selectedNodeId={selectedNodeId}
        onClearPath={onClearPath}
        error={error}
        onBack={onBack}
        visibleKinds={visibleKinds}
        setVisibleKinds={setVisibleKinds}
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
        searchMatches={searchMatches}
        onSearchSelect={onSearchSelect}
      />
      <div ref={containerRef} className="flex-1 flex overflow-hidden">
        <div className="flex-1 min-w-0">
          <ReactFlow
            ref={reactFlowRef}
            onInit={onReactFlowInit}
            nodeTypes={nodeTypes}
            nodes={nodesWithHighlight}
            edges={edgesWithHighlight}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            onPaneClick={onPaneClick}
            onEdgeClick={onEdgeClick}
            selectNodesOnDrag={false}
            fitView
            fitViewOptions={{ padding: 0.2 }}
          >
            <Background color="#373a40" gap={16} />
            <Controls />
            <MiniMap
              nodeColor={(n) => KIND_CONFIG[n.data?.kind]?.color ?? '#868e96'}
              maskColor="rgba(0, 0, 0, 0.7)"
            />
          </ReactFlow>
        </div>
        <div
          role="separator"
          aria-orientation="vertical"
          aria-valuenow={codePanelWidth}
          className="w-1.5 flex-shrink-0 bg-zinc-600 hover:bg-sky-500 cursor-col-resize select-none flex items-center justify-center group"
          onMouseDown={onResizeStart}
        >
          <span className="w-1 h-8 rounded-full bg-zinc-500 group-hover:bg-sky-400 opacity-0 group-hover:opacity-100 transition-opacity" />
        </div>
        <aside
          className="flex-shrink-0 bg-panel border-l border-surface-border flex flex-col overflow-hidden"
          style={{ width: codePanelWidth, minWidth: CODE_PANEL_MIN }}
        >
          <CodePanel
            code={liveCodeLoading ? '' : selectedCode}
            label={selectedLabel}
            filePath={selectedFilePath}
            language={selectedCodeLanguage}
            nodeKind={selectedNode?.data?.kind}
            loading={liveCodeLoading}
            error={liveCodeError}
            notes={projectId && selectedNodeId ? (nodeNotes[selectedNodeId] || []) : []}
            onSaveNotes={projectId && selectedNodeId ? (newNotes) => {
              updateNodeNotes(projectId, selectedNodeId, newNotes).then(() => {
                setNodeNotes((prev) => ({ ...prev, [selectedNodeId]: newNotes }))
              }).catch(() => {})
            } : undefined}
          />
        </aside>
      </div>
    </div>
  )
})

export default GraphLayout
