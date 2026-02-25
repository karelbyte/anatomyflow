import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react'
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
} from 'reactflow'
import 'reactflow/dist/style.css'
import { AppHeader, CodePanel, PathPanel, AnatomyNode, ClusterBg } from '../organisms'
import { KIND_CONFIG } from '../../constants'
import { fetchNodeCode, fetchNodeNotes, updateNodeNotes } from '../../lib/api'

const CODE_PANEL_MIN = 280
const CODE_PANEL_MAX_PERCENT = 0.7
const CODE_PANEL_DEFAULT = 420
const PATH_PANEL_MIN = 260
const PATH_PANEL_MAX_PERCENT = 0.5
const PATH_PANEL_DEFAULT = 320

const CODE_KINDS_FETCH = ['model', 'view', 'controller', 'route', 'page', 'api_route', 'component', 'express_route', 'middleware', 'service', 'module', 'repository', 'use_case', 'handler', 'adapter', 'entity', 'factory', 'other']

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
  pathLocked,
  onToggleLockPath,
  hidePathHighlight,
  onToggleHidePathHighlight,
  error,
  selectedNode,
  cycleNodeIds,
  fanInFanOut,
  pathDistances,
  pathEdgeReasons,
  pathNodesWithCode,
  projectId,
  onBack,
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
}, ref) {
  const [codePanelWidth, setCodePanelWidth] = useState(CODE_PANEL_DEFAULT)
  const [pathPanelWidth, setPathPanelWidth] = useState(PATH_PANEL_DEFAULT)
  const containerRef = useRef(null)
  const reactFlowRef = useRef(null)
  const reactFlowInstanceRef = useRef(null)
  const isDraggingCode = useRef(false)
  const isDraggingPath = useRef(false)
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

  const onResizeCodeStart = useCallback((e) => {
    e.preventDefault()
    isDraggingCode.current = true
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }, [])

  const onResizePathStart = useCallback((e) => {
    e.preventDefault()
    isDraggingPath.current = true
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }, [])

  useEffect(() => {
    const handleMove = (e) => {
      if (!containerRef.current) return
      const rect = containerRef.current.getBoundingClientRect()
      const maxCodePx = rect.width * CODE_PANEL_MAX_PERCENT
      const maxPathPx = rect.width * PATH_PANEL_MAX_PERCENT
      if (isDraggingPath.current) {
        const newWidth = Math.round(e.clientX - rect.left)
        setPathPanelWidth(Math.max(PATH_PANEL_MIN, Math.min(maxPathPx, newWidth)))
      } else if (isDraggingCode.current) {
        const newWidth = Math.round(rect.right - e.clientX)
        setCodePanelWidth(Math.max(CODE_PANEL_MIN, Math.min(maxCodePx, newWidth)))
      }
    }
    const handleUp = () => {
      if (isDraggingCode.current || isDraggingPath.current) {
        isDraggingCode.current = false
        isDraggingPath.current = false
        document.body.style.cursor = ''
        document.body.style.userSelect = ''
      }
    }
    document.addEventListener('mousemove', handleMove)
    document.addEventListener('mouseup', handleUp)
    return () => {
      document.removeEventListener('mousemove', handleMove)
      document.removeEventListener('mouseup', handleUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
  }, [pathPanelWidth])

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
  const cycleDisplay = cycleNodeIds?.length && nodes?.length
    ? cycleNodeIds.map((id) => nodes.find((n) => n.id === id)?.data?.label || id).join(' → ')
    : null

  return (
    <div className="w-screen h-screen flex flex-col">
      <AppHeader
        onFileSelect={onFileSelect}
        onExport={onExport}
        selectedNodeId={selectedNodeId}
        onClearPath={onClearPath}
        pathLocked={pathLocked}
        onToggleLockPath={onToggleLockPath}
        hidePathHighlight={hidePathHighlight}
        onToggleHidePathHighlight={onToggleHidePathHighlight}
        error={error}
        onBack={onBack}
        visibleKinds={visibleKinds}
        setVisibleKinds={setVisibleKinds}
        projectKinds={projectKinds}
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
        searchMatches={searchMatches}
        onSearchSelect={onSearchSelect}
        pathHasNodes={pathHasNodes}
        onExportPathJson={onExportPathJson}
        onExportPathImage={onExportPathImage}
      />
      <div ref={containerRef} className="flex-1 flex overflow-hidden">
        <aside
          className="flex-shrink-0 flex flex-col overflow-hidden border-r border-surface-border"
          style={{ width: pathPanelWidth, minWidth: PATH_PANEL_MIN }}
        >
          <PathPanel
            cycleDisplay={cycleDisplay}
            fanInFanOut={fanInFanOut}
            pathDistances={pathDistances}
            pathEdgeReasons={pathEdgeReasons}
            pathNodesWithCode={pathNodesWithCode}
          />
        </aside>
        <div
          role="separator"
          aria-orientation="vertical"
          aria-valuenow={pathPanelWidth}
          className="w-1.5 flex-shrink-0 bg-zinc-600 hover:bg-sky-500 cursor-col-resize select-none flex items-center justify-center group"
          onMouseDown={onResizePathStart}
        >
          <span className="w-1 h-8 rounded-full bg-zinc-500 group-hover:bg-sky-400 opacity-0 group-hover:opacity-100 transition-opacity" />
        </div>
        <div ref={graphContainerRef} className="flex-1 min-w-0">
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
          onMouseDown={onResizeCodeStart}
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
