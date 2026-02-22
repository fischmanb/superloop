const DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] as const
const MONTH_LABELS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
] as const

export interface DayInfo {
  label: string // e.g. "Mon"
  dateLabel: string // e.g. "Feb 16"
  dateISO: string // e.g. "2026-02-16"
}

/**
 * Returns an array of 7 DayInfo objects (Mon–Sun) for the week containing `anchor`.
 */
export function getWeekDays(anchor: Date): DayInfo[] {
  const d = new Date(anchor)
  // getDay: 0=Sun, 1=Mon ... 6=Sat → shift to Mon=0
  const jsDay = d.getDay()
  const mondayOffset = jsDay === 0 ? -6 : 1 - jsDay
  const monday = new Date(d)
  monday.setDate(d.getDate() + mondayOffset)

  return DAY_LABELS.map((label, i) => {
    const day = new Date(monday)
    day.setDate(monday.getDate() + i)
    const month = MONTH_LABELS[day.getMonth()]
    const date = day.getDate()
    const yyyy = day.getFullYear()
    const mm = String(day.getMonth() + 1).padStart(2, '0')
    const dd = String(date).padStart(2, '0')
    return {
      label,
      dateLabel: `${month} ${date}`,
      dateISO: `${yyyy}-${mm}-${dd}`,
    }
  })
}

/**
 * Formats a 24h "HH:MM" string into "H:MM AM/PM".
 */
export function formatTime(time24: string): string {
  const [hourStr, min] = time24.split(':')
  let hour = parseInt(hourStr, 10)
  const ampm = hour >= 12 ? 'PM' : 'AM'
  if (hour === 0) hour = 12
  else if (hour > 12) hour -= 12
  return `${hour}:${min} ${ampm}`
}
