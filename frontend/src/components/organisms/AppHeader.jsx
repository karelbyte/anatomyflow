import { useEffect } from 'react'
import toast from 'react-hot-toast'
import { FiArrowLeft, FiUpload, FiX } from 'react-icons/fi'
import { Button, Text } from '../atoms'
import { FileInputLabel, LegendItem } from '../molecules'
import { KIND_CONFIG } from '../../constants'

export default function AppHeader({
  onFileSelect,
  selectedNodeId,
  onClearPath,
  error,
  onBack,
}) {
  useEffect(() => {
    if (error) toast.error(error)
  }, [error])
  return (
    <header className="flex items-center gap-6 flex-wrap px-4 py-3 bg-surface border-b border-surface-border">
      {onBack && (
        <Button variant="ghost" onClick={onBack} className="inline-flex items-center gap-2"><FiArrowLeft className="w-4 h-4" /> Back to project</Button>
      )}
      <Text as="strong" variant="title">
        Project Anatomy
      </Text>
     {/* <FileInputLabel accept=".json" onChange={onFileSelect} className="inline-flex items-center gap-2">
        <FiUpload className="w-4 h-4" /> Load graph JSON
      </FileInputLabel> */}
      {selectedNodeId != null ? (
        <>
         {/* <Text variant="accent">Path: {selectedNodeId}</Text> */}
          <Button variant="secondary" onClick={onClearPath} className="inline-flex items-center gap-2">
            <FiX className="w-4 h-4" /> Clear path
          </Button>
        </>
      ) : (
        <Text variant="muted">Click a node to highlight its path</Text>
      )}
      <div className="flex items-center gap-4 text-xs ml-auto">
        {Object.entries(KIND_CONFIG).map(([key, { color, label }]) => (
          <LegendItem key={key} color={color} label={label} />
        ))}
      </div>
    </header>
  )
}
