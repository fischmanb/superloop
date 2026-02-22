import { CalendarBlock } from '../../../types/calendar'

/**
 * Mock blocks for the week of 2026-02-16 (Mon) through 2026-02-22 (Sun).
 * Covers all 6 categories across 4 different days with 8 total blocks.
 */
export const mockWeekBlocks: CalendarBlock[] = [
  {
    id: 'block-1',
    title: 'Morning Focus',
    category: 'deep-work',
    date: '2026-02-16',
    startTime: '09:00',
    endTime: '11:00',
  },
  {
    id: 'block-2',
    title: 'Weekly Therapy',
    category: 'therapy',
    date: '2026-02-16',
    startTime: '14:00',
    endTime: '15:00',
  },
  {
    id: 'block-3',
    title: 'Morning Meds',
    category: 'medication',
    date: '2026-02-18',
    startTime: '08:00',
    endTime: '08:15',
  },
  {
    id: 'block-4',
    title: 'Afternoon Walk',
    category: 'self-care',
    date: '2026-02-18',
    startTime: '12:00',
    endTime: '13:00',
  },
  {
    id: 'block-5',
    title: 'Gym Session',
    category: 'exercise',
    date: '2026-02-20',
    startTime: '07:00',
    endTime: '08:00',
  },
  {
    id: 'block-6',
    title: 'Coffee with Alex',
    category: 'social',
    date: '2026-02-20',
    startTime: '10:00',
    endTime: '11:00',
  },
  {
    id: 'block-7',
    title: 'Deep Reading',
    category: 'deep-work',
    date: '2026-02-21',
    startTime: '09:00',
    endTime: '11:30',
  },
  {
    id: 'block-8',
    title: 'Evening Meds',
    category: 'medication',
    date: '2026-02-18',
    startTime: '20:00',
    endTime: '20:15',
  },
]
