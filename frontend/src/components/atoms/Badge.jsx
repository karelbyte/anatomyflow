export default function Badge({ children, variant = 'default', className = '', ...props }) {
  const variants = {
    default: 'bg-zinc-600 text-zinc-200',
    danger: 'bg-red-500/25 text-red-400',
    accent: 'bg-sky-500/25 text-sky-400',
  }
  return (
    <span
      className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-semibold ${variants[variant] || variants.default} ${className}`}
      {...props}
    >
      {children}
    </span>
  )
}
