---
feature: Calendar Week View
domain: calendar
source: src/components/calendar/WeekView.tsx
tests:
  - src/components/calendar/__tests__/WeekView.test.tsx
components:
  - WeekView
  - DayColumn
  - BlockCard
status: implemented
created: 2026-02-22
updated: 2026-02-22
---

# Calendar: Week View

**Source File**: src/components/calendar/WeekView.tsx
**Design System**: .specs/design-system/tokens.md

## Feature: Week View

A 7-day calendar grid that renders color-coded time blocks. The component accepts a `blocks` prop and renders them in the correct day columns by category color.

### Categories

The app uses 6 block categories, each with a distinct color:

| Category | Color | Token |
|----------|-------|-------|
| Deep Work | Blue `#3B82F6` | `color-primary` |
| Medication | Red `#EF4444` | `color-error` |
| Exercise | Green `#10B981` | `color-success` |
| Therapy | Purple `#8B5CF6` | `color-secondary` |
| Self-Care | Amber `#F59E0B` | `color-warning` |
| Social | Cyan `#06B6D4` | `color-info` |

### Scenario: Render week with blocks across multiple days

```gherkin
Given the WeekView component is rendered with a blocks prop
And the blocks span 4 different days across the current week
When the component mounts
Then 7 day columns are displayed (Mon–Sun)
And each day column shows a day-of-week label and date
And blocks appear in the correct day column
And each block displays its title and time range
And each block is color-coded by its category
```

### Scenario: Empty day shows no blocks

```gherkin
Given the WeekView is rendered with blocks
And some days have no blocks assigned
When the component mounts
Then those day columns render with just the header and no block cards
```

### Scenario: Multiple blocks in one day stack vertically

```gherkin
Given a single day has 3 blocks assigned
When the WeekView renders
Then the 3 blocks appear stacked vertically in that day's column
And they are ordered by start time (earliest on top)
```

### Scenario: Block card displays essential info

```gherkin
Given a block with title "Morning Focus", category "Deep Work", startTime "09:00", endTime "11:00"
When rendered as a BlockCard
Then it shows the title "Morning Focus"
And it shows the time "9:00 AM – 11:00 AM"
And the card background uses the Deep Work category color
```

## UI Mockup

```
┌─────────────────────────────────────────────────────────────────────┐
│  Week View (bg: background)                                        │
│                                                                     │
│  ┌────────┬────────┬────────┬────────┬────────┬────────┬────────┐  │
│  │ Mon    │ Tue    │ Wed    │ Thu    │ Fri    │ Sat    │ Sun    │  │
│  │ Feb 16 │ Feb 17 │ Feb 18 │ Feb 19 │ Feb 20 │ Feb 21 │ Feb 22 │  │
│  ├────────┼────────┼────────┼────────┼────────┼────────┼────────┤  │
│  │┌──────┐│        │┌──────┐│        │┌──────┐│        │        │  │
│  ││Deep  ││        ││Meds  ││        ││Exer- ││        │        │  │
│  ││Work  ││        ││      ││        ││cise  ││        │        │  │
│  ││9-11a ││        ││8:00a ││        ││7-8a  ││        │        │  │
│  │└──────┘│        │└──────┘│        │└──────┘│        │        │  │
│  │┌──────┐│        │┌──────┐│        │        │        │        │  │
│  ││Ther- ││        ││Self  ││        │        │        │        │  │
│  ││apy   ││        ││Care  ││        │        │        │        │  │
│  ││2-3p  ││        ││12-1p ││        │        │        │        │  │
│  │└──────┘│        │└──────┘│        │        │        │        │  │
│  │        │        │        │        │        │        │        │  │
│  └────────┴────────┴────────┴────────┴────────┴────────┴────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

Block Card (bg: category color-light, border-left: 3px category color, radius: md)
┌──────────────────────┐
│ ▎ Title              │  (text: sm, weight: semibold, color: text)
│ ▎ 9:00 AM – 11:00 AM│  (text: xs, color: text-secondary)
└──────────────────────┘
```

## Mock Data

A static mock dataset is co-located at `src/components/calendar/__mocks__/weekBlocks.ts`.

Requirements:
- At least 6 blocks across 4 different days
- All 6 categories represented
- Each block has: `id`, `title`, `category`, `date` (ISO string), `startTime`, `endTime`

## Types

```typescript
type BlockCategory = 'deep-work' | 'medication' | 'exercise' | 'therapy' | 'self-care' | 'social';

interface CalendarBlock {
  id: string;
  title: string;
  category: BlockCategory;
  date: string;        // ISO date string, e.g. "2026-02-16"
  startTime: string;   // "HH:MM" 24h format
  endTime: string;     // "HH:MM" 24h format
}

interface WeekViewProps {
  blocks: CalendarBlock[];
}
```

## Component References

- BlockCard: new component (stub needed)
- DayColumn: new component (stub needed)

## Out of Scope

- Navigation between weeks
- Tapping blocks (detail view is Feature 4)
- Adding or editing blocks (Feature 3)
- Coach client switcher (Feature 2)
- Authentication or real data
- Notifications
