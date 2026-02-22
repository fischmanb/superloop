export type BlockCategory =
  | 'deep-work'
  | 'medication'
  | 'exercise'
  | 'therapy'
  | 'self-care'
  | 'social'

export interface CalendarBlock {
  id: string
  title: string
  category: BlockCategory
  date: string // ISO date string, e.g. "2026-02-16"
  startTime: string // "HH:MM" 24h format
  endTime: string // "HH:MM" 24h format
}

export interface WeekViewProps {
  blocks: CalendarBlock[]
  /** The week to display — any date within the target week. Defaults to current week. */
  weekOf?: Date
}

export const CATEGORY_COLORS: Record<BlockCategory, { bg: string; border: string }> = {
  'deep-work': { bg: 'bg-primary-light', border: 'border-primary' },
  medication: { bg: 'bg-error-light', border: 'border-error' },
  exercise: { bg: 'bg-success-light', border: 'border-success' },
  therapy: { bg: 'bg-secondary-light', border: 'border-secondary' },
  'self-care': { bg: 'bg-warning-light', border: 'border-warning' },
  social: { bg: 'bg-info-light', border: 'border-info' },
}

export const CATEGORY_LABELS: Record<BlockCategory, string> = {
  'deep-work': 'Deep Work',
  medication: 'Medication',
  exercise: 'Exercise',
  therapy: 'Therapy',
  'self-care': 'Self-Care',
  social: 'Social',
}
