import { CalendarBlock, CATEGORY_COLORS } from '../../types/calendar'
import { formatTime } from '../../utils/date'

interface BlockCardProps {
  block: CalendarBlock
}

export function BlockCard({ block }: BlockCardProps) {
  const colors = CATEGORY_COLORS[block.category]
  const timeRange = `${formatTime(block.startTime)} – ${formatTime(block.endTime)}`

  return (
    <div
      data-testid={`block-card-${block.id}`}
      className={`${colors.bg} ${colors.border} border-l-[3px] rounded-md px-2 py-1.5 mb-1.5`}
    >
      <p data-testid="block-title" className="text-sm font-semibold text-gray-900 leading-tight">
        {block.title}
      </p>
      <p className="text-xs text-gray-500 leading-tight">{timeRange}</p>
    </div>
  )
}
