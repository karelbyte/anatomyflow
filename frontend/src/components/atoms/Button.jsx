export default function Button({ children, variant = 'secondary', className = '', ...props }) {
  const variants = {
    primary: 'bg-sky-600 hover:bg-sky-500 text-white border-sky-500',
    secondary: 'bg-surface border border-surface-muted hover:bg-zinc-600 text-zinc-200',
    ghost: 'hover:bg-zinc-700/50 text-zinc-300',
  }
  return (
    <button
      type="button"
      className={`inline-flex items-center justify-center rounded-md px-2.5 py-1.5 text-sm font-medium transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ${variants[variant] || variants.secondary} ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}
