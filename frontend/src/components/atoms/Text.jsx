export default function Text({ as: Tag = 'span', variant = 'body', className = '', ...props }) {
  const variants = {
    body: 'text-sm text-zinc-300',
    muted: 'text-xs text-zinc-500',
    accent: 'text-xs text-sky-400',
    strong: 'text-base font-semibold text-zinc-100',
    title: 'text-lg font-semibold text-zinc-100',
    danger: 'text-sm text-red-400',
  }
  return <Tag className={`${variants[variant] || variants.body} ${className}`} {...props} />
}
