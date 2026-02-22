import { CalendarBlock } from '../../types/calendar'
import { BlockCard } from './BlockCard'

interface DayColumnProps {
  dayLabel: string
  dateLabel: string
  dateISO: string
  blocks: CalendarBlock[]
}

export function DayColumn({ dayLabel, dateLabel, dateISO, blocks }: DayColumnProps) {
  // Sort blocks by start time (earliest first)
  const sorted = [...blocks].sort((a, b) => a.startTime.localeCompare(b.startTime))

  return (
    <div data-testid={`day-column-${dateISO}`} className="flex-1 min-w-0 border-r border-gray-200 last:border-r-0">
      <div className="text-center py-2 border-b border-gray-200 bg-white sticky top-0">
        <p className="text-sm font-semibold text-gray-900">{dayLabel}</p>
        <p className="text-xs text-gray-500">{dateLabel}</p>
      </div>
      <div className="p-1.5 space-y-0">
        {sorted.map((block) => (
          <BlockCard key={block.id} block={block} />
        ))}
      </div>
    </div>
  )
}
