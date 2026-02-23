import { useCallback, useEffect, useRef, useState } from 'react'
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
} from 'reactflow'
import 'reactflow/dist/style.css'
import { AppHeader, CodePanel, AnatomyNode, ClusterBg } from '../organisms'
import { KIND_CONFIG } from '../../constants'

const nodeTypes = { anatomy: AnatomyNode, clusterBg: ClusterBg }

const CODE_PANEL_MIN = 280
const CODE_PANEL_MAX_PERCENT = 0.7
const CODE_PANEL_DEFAULT = 420

export default function GraphLayout({
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
  selectedNodeId,
  onClearPath,
  error,
  selectedNode,
  onBack,
}) {
  const [codePanelWidth, setCodePanelWidth] = useState(CODE_PANEL_DEFAULT)
  const containerRef = useRef(null)
  const isDragging = useRef(false)

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

  const selectedCode = selectedNode?.data?.code ?? null
  const selectedLabel = selectedNodeId ? selectedNode?.data?.label ?? selectedNodeId : null
  const selectedCodeLanguage = selectedNode?.data?.kind === 'table' ? 'sql' : 'php'

  return (
    <div className="w-screen h-screen flex flex-col">
      <AppHeader
        onFileSelect={onFileSelect}
        selectedNodeId={selectedNodeId}
        onClearPath={onClearPath}
        error={error}
        onBack={onBack}
      />
      <div ref={containerRef} className="flex-1 flex overflow-hidden">
        <div className="flex-1 min-w-0">
          <ReactFlow
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
            code={selectedCode}
            label={selectedLabel}
            language={selectedCodeLanguage}
            nodeKind={selectedNode?.data?.kind}
          />
        </aside>
      </div>
    </div>
  )
}
