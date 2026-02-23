import Text from '../atoms/Text'

export default function FileInputLabel({ children, accept = '.json', onChange, className = '' }) {
  return (
    <label className={`cursor-pointer underline decoration-sky-400 text-sky-400 hover:text-sky-300 transition-colors ${className}`}>
      <Text as="span" variant="body">
        {children}
      </Text>
      <input type="file" accept={accept} onChange={onChange} className="sr-only" />
    </label>
  )
}
