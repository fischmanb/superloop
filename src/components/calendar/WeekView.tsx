import { WeekViewProps } from '../../types/calendar'
import { getWeekDays } from '../../utils/date'
import { DayColumn } from './DayColumn'

export function WeekView({ blocks, weekOf }: WeekViewProps) {
  const anchor = weekOf ?? new Date()
  const days = getWeekDays(anchor)

  // Group blocks by date
  const blocksByDate = new Map<string, typeof blocks>()
  for (const block of blocks) {
    const existing = blocksByDate.get(block.date) ?? []
    existing.push(block)
    blocksByDate.set(block.date, existing)
  }

  return (
    <div className="bg-white rounded-lg shadow-md border border-gray-200 overflow-hidden">
      <div className="flex">
        {days.map((day) => (
          <DayColumn
            key={day.dateISO}
            dayLabel={day.label}
            dateLabel={day.dateLabel}
            dateISO={day.dateISO}
            blocks={blocksByDate.get(day.dateISO) ?? []}
          />
        ))}
      </div>
    </div>
  )
}
