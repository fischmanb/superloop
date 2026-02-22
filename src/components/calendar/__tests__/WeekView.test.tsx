import { describe, it, expect } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { WeekView } from '../WeekView'
import { BlockCard } from '../BlockCard'
import { DayColumn } from '../DayColumn'
import { mockWeekBlocks } from '../__mocks__/weekBlocks'
import { CalendarBlock } from '../../../types/calendar'

// The mock week is anchored at 2026-02-16 (Monday)
const WEEK_ANCHOR = new Date(2026, 1, 16) // Feb 16, 2026

describe('WeekView', () => {
  // Scenario: Render week with blocks across multiple days
  describe('Scenario: Render week with blocks across multiple days', () => {
    it('CMP-01: renders 7 day columns (Mon–Sun)', () => {
      render(<WeekView blocks={mockWeekBlocks} weekOf={WEEK_ANCHOR} />)
      const dayLabels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
      dayLabels.forEach((label) => {
        expect(screen.getByText(label)).toBeInTheDocument()
      })
    })

    it('CMP-02: each day column shows a day-of-week label and date', () => {
      render(<WeekView blocks={mockWeekBlocks} weekOf={WEEK_ANCHOR} />)
      // Check that date labels are present for the week of Feb 16–22
      expect(screen.getByText('Feb 16')).toBeInTheDocument()
      expect(screen.getByText('Feb 17')).toBeInTheDocument()
      expect(screen.getByText('Feb 22')).toBeInTheDocument()
    })

    it('CMP-03: blocks appear in the correct day column', () => {
      render(<WeekView blocks={mockWeekBlocks} weekOf={WEEK_ANCHOR} />)
      // Monday (Feb 16) should have "Morning Focus" and "Weekly Therapy"
      const monColumn = screen.getByTestId('day-column-2026-02-16')
      expect(within(monColumn).getByText('Morning Focus')).toBeInTheDocument()
      expect(within(monColumn).getByText('Weekly Therapy')).toBeInTheDocument()

      // Wednesday (Feb 18) should have "Morning Meds", "Afternoon Walk", "Evening Meds"
      const wedColumn = screen.getByTestId('day-column-2026-02-18')
      expect(within(wedColumn).getByText('Morning Meds')).toBeInTheDocument()
      expect(within(wedColumn).getByText('Afternoon Walk')).toBeInTheDocument()
      expect(within(wedColumn).getByText('Evening Meds')).toBeInTheDocument()
    })

    it('CMP-04: each block displays its title and time range', () => {
      render(<WeekView blocks={mockWeekBlocks} weekOf={WEEK_ANCHOR} />)
      expect(screen.getByText('Morning Focus')).toBeInTheDocument()
      expect(screen.getByText('9:00 AM – 11:00 AM')).toBeInTheDocument()
    })

    it('CMP-05: each block is color-coded by its category', () => {
      render(<WeekView blocks={mockWeekBlocks} weekOf={WEEK_ANCHOR} />)
      const blockCard = screen.getByTestId('block-card-block-1')
      // Deep Work → primary colors
      expect(blockCard).toHaveClass('bg-primary-light')
      expect(blockCard).toHaveClass('border-primary')
    })
  })

  // Scenario: Empty day shows no blocks
  describe('Scenario: Empty day shows no blocks', () => {
    it('CMP-06: days with no blocks render with just the header', () => {
      render(<WeekView blocks={mockWeekBlocks} weekOf={WEEK_ANCHOR} />)
      // Tuesday (Feb 17) has no blocks
      const tueColumn = screen.getByTestId('day-column-2026-02-17')
      expect(within(tueColumn).getByText('Tue')).toBeInTheDocument()
      expect(within(tueColumn).getByText('Feb 17')).toBeInTheDocument()
      // Should have no block cards
      expect(within(tueColumn).queryAllByTestId(/^block-card-/)).toHaveLength(0)
    })
  })

  // Scenario: Multiple blocks in one day stack vertically ordered by start time
  describe('Scenario: Multiple blocks in one day stack vertically', () => {
    it('CMP-07: blocks are ordered by start time (earliest on top)', () => {
      render(<WeekView blocks={mockWeekBlocks} weekOf={WEEK_ANCHOR} />)
      // Wednesday (Feb 18) has blocks at 08:00, 12:00, 20:00
      const wedColumn = screen.getByTestId('day-column-2026-02-18')
      const blockCards = within(wedColumn).getAllByTestId(/^block-card-/)
      const titles = blockCards.map((el) => within(el).getByTestId('block-title').textContent)
      expect(titles).toEqual(['Morning Meds', 'Afternoon Walk', 'Evening Meds'])
    })
  })
})

describe('BlockCard', () => {
  // Scenario: Block card displays essential info
  describe('Scenario: Block card displays essential info', () => {
    const block: CalendarBlock = {
      id: 'test-1',
      title: 'Morning Focus',
      category: 'deep-work',
      date: '2026-02-16',
      startTime: '09:00',
      endTime: '11:00',
    }

    it('CMP-08: shows the title', () => {
      render(<BlockCard block={block} />)
      expect(screen.getByText('Morning Focus')).toBeInTheDocument()
    })

    it('CMP-09: shows the formatted time range', () => {
      render(<BlockCard block={block} />)
      expect(screen.getByText('9:00 AM – 11:00 AM')).toBeInTheDocument()
    })

    it('CMP-10: card background uses the category color', () => {
      render(<BlockCard block={block} />)
      const card = screen.getByTestId('block-card-test-1')
      expect(card).toHaveClass('bg-primary-light')
      expect(card).toHaveClass('border-primary')
    })
  })
})

describe('DayColumn', () => {
  it('CMP-11: renders day label and date label', () => {
    render(
      <DayColumn
        dayLabel="Mon"
        dateLabel="Feb 16"
        dateISO="2026-02-16"
        blocks={[]}
      />
    )
    expect(screen.getByText('Mon')).toBeInTheDocument()
    expect(screen.getByText('Feb 16')).toBeInTheDocument()
  })

  it('CMP-12: renders blocks passed to it', () => {
    const blocks: CalendarBlock[] = [
      {
        id: 'dc-1',
        title: 'Test Block',
        category: 'exercise',
        date: '2026-02-16',
        startTime: '07:00',
        endTime: '08:00',
      },
    ]
    render(
      <DayColumn
        dayLabel="Mon"
        dateLabel="Feb 16"
        dateISO="2026-02-16"
        blocks={blocks}
      />
    )
    expect(screen.getByText('Test Block')).toBeInTheDocument()
  })
})
