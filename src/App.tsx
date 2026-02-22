import { WeekView } from './components/calendar/WeekView'
import { mockWeekBlocks } from './components/calendar/__mocks__/weekBlocks'

export default function App() {
  return (
    <div className="min-h-screen bg-surface p-4 sm:p-8">
      <h1 className="text-2xl font-bold text-gray-900 mb-4">ADHD Calendar</h1>
      <WeekView blocks={mockWeekBlocks} weekOf={new Date(2026, 1, 16)} />
    </div>
  )
}
