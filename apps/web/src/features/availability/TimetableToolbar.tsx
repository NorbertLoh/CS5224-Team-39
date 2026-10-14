import { Button } from '../../components/ui/button'
import { shiftDate, weekStart } from './timetable'
import { singaporeDate } from './fixtures'

type TimetableToolbarProps = {
  week: string
  onWeekChange: (week: string) => void
}

export function TimetableToolbar({
  week,
  onWeekChange,
}: TimetableToolbarProps) {
  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold">
            {week} – {shiftDate(week, 6)}
          </h3>
          <p className="text-sm text-slate-600">
            Singapore time (SGT, UTC+8) · 30-minute slots
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => onWeekChange(shiftDate(week, -7))}
            aria-label="Previous week"
          >
            ←
          </Button>
          <Button
            variant="outline"
            onClick={() => onWeekChange(weekStart(singaporeDate()))}
          >
            This week
          </Button>
          <Button
            variant="outline"
            onClick={() => onWeekChange(shiftDate(week, 7))}
            aria-label="Next week"
          >
            →
          </Button>
        </div>
      </div>
      <div
        className="flex flex-wrap gap-4 text-xs text-slate-600"
        aria-label="Timetable legend"
      >
        <span className="rounded bg-emerald-100 px-2 py-1 text-emerald-900">
          Available
        </span>
        <span className="rounded bg-slate-200 px-2 py-1">Unavailable</span>
        <span className="rounded bg-violet-100 px-2 py-1 text-violet-900">
          Other clinic
        </span>
        <span className="rounded border-2 border-sky-600 px-2 py-0.5">
          Selected
        </span>
      </div>
      <p className="text-xs text-slate-500">
        Drag from an unselected cell to select a range, or from a selected cell
        to deselect a range. Click any cell to toggle it. Separate selections
        stay selected. Keyboard: toggle with Enter or Space, use arrow keys to
        move, Shift + arrows to extend, and Escape to clear. Scroll for all 24
        hours.
      </p>
    </>
  )
}
