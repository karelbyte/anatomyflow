export default function ColorDot({ color, size = 'sm', className = '' }) {
  const sizes = { sm: 'w-2.5 h-2.5', md: 'w-3 h-3' }
  return (
    <span
      className={`inline-block rounded ${sizes[size]} shrink-0 ${className}`}
      style={{ backgroundColor: color }}
      aria-hidden
    />
  )
}
