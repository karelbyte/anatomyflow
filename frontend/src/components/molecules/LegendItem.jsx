import ColorDot from '../atoms/ColorDot'
import Text from '../atoms/Text'

export default function LegendItem({ color, label }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <ColorDot color={color} />
      <Text variant="muted">{label}</Text>
    </span>
  )
}
