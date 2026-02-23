import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import Text from '../atoms/Text'

const CODE_NODE_KINDS = ['table', 'model', 'view', 'controller']

export default function CodePanel({ code, label, language = 'php', nodeKind = '' }) {
  const isCodeNode = CODE_NODE_KINDS.includes((nodeKind || '').toLowerCase())
  if (!code) {
    return (
      <div className="flex items-center justify-center h-full text-center p-6">
        <Text variant="muted">
          {isCodeNode
            ? `No code available for this ${nodeKind || 'node'}. Re-run analysis to generate it.`
            : 'Select a node with associated code'}
        </Text>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {label && (
        <div className="px-4 py-2.5 bg-surface border-b border-surface-border">
          <Text as="div" variant="strong" className="text-sm">
            {label}
          </Text>
        </div>
      )}
      <div className="flex-1 overflow-auto code-panel-scroll">
        <SyntaxHighlighter
          language={language}
          style={oneDark}
          customStyle={{
            margin: 0,
            padding: 16,
            background: '#1e1e1e',
            fontSize: 13,
            minHeight: '100%',
          }}
          showLineNumbers
          lineNumberStyle={{ minWidth: '2em', color: '#495057', userSelect: 'none' }}
          codeTagProps={{ style: { fontFamily: 'ui-monospace, monospace' } }}
        >
          {code}
        </SyntaxHighlighter>
      </div>
    </div>
  )
}
