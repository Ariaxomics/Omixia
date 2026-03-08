const tierColors: Record<string, string> = {
  tier_1: 'bg-red-100 text-red-800',
  tier_2: 'bg-orange-100 text-orange-800',
  tier_3: 'bg-yellow-100 text-yellow-800',
  tier_4: 'bg-gray-100 text-gray-700',
}

const statusColors: Record<string, string> = {
  unreviewed: 'bg-gray-100 text-gray-600',
  pending_second_review: 'bg-blue-100 text-blue-700',
  concordant: 'bg-green-100 text-green-700',
  discordant: 'bg-red-100 text-red-700',
  resolved: 'bg-purple-100 text-purple-700',
  artifact: 'bg-gray-100 text-gray-400 line-through',
  draft: 'bg-yellow-100 text-yellow-800',
  pending_sign_off: 'bg-blue-100 text-blue-700',
  finalised: 'bg-green-100 text-green-700',
  confirmed: 'bg-green-100 text-green-700',
}

interface BadgeProps {
  value: string
  type?: 'tier' | 'status'
  className?: string
}

export default function Badge({ value, type = 'status', className = '' }: BadgeProps) {
  const colorMap = type === 'tier' ? tierColors : statusColors
  const colors = colorMap[value] ?? 'bg-gray-100 text-gray-600'
  const label = value?.replace(/_/g, ' ')
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${colors} ${className}`}>
      {label}
    </span>
  )
}
