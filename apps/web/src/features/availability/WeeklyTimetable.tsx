import { useEffect, useRef } from 'react'
import type { Slot } from './fixtures'
import { isSelected, times } from './timetable'
import type { Selection } from './timetable'
import { TimetableCell } from './TimetableCell'
import { useTimetableSelection } from './useTimetableSelection'

const dayFormatter = new Intl.DateTimeFormat('en-SG', {
  weekday: 'short',
  day: 'numeric',
  month: 'short',
  timeZone: 'UTC',
})

type WeeklyTimetableProps = {
  slots: Slot[]
  tenantId: string
  doctorId: string
  dates: string[]
  selections: Selection[]
  onChange: (selections: Selection[]) => void
}

export function WeeklyTimetable({
  slots,
  tenantId,
  doctorId,
  dates,
  selections,
  onChange,
}: WeeklyTimetableProps) {
  const viewport = useRef<HTMLDivElement>(null)
  const interaction = useTimetableSelection(selections, onChange)
  const doctorSlots = slots.filter((slot) => slot.doctor_id === doctorId)

  useEffect(() => {
    // Start at 08:00; earlier and later hours remain reachable by scrolling.
    if (viewport.current) viewport.current.scrollTop = 16 * 32
  }, [])

  return (
    <div
      ref={viewport}
      className="max-h-[620px] overflow-auto rounded-xl border"
      aria-label="Weekly availability timetable"
    >
      <table
        className="w-full min-w-[780px] table-fixed select-none border-collapse text-sm"
        {...interaction.tableHandlers}
      >
        <thead className="sticky top-0 z-10 bg-white shadow-sm">
          <tr>
            <th className="w-20 border-b px-2 py-4 text-xs text-slate-500">
              SGT
            </th>
            {dates.map((date) => (
              <th
                key={date}
                scope="col"
                className="border-b border-l px-2 py-4 font-medium"
              >
                {dayFormatter.format(new Date(date))}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {times.map((time, row) => (
            <tr key={time}>
              <th
                scope="row"
                className="h-8 border-t px-2 align-top text-xs font-normal text-slate-500"
              >
                {time}
              </th>
              {dates.map((date, day) => {
                const cell = { day, row }
                const selected = selections.some((range) =>
                  isSelected(range, day, row),
                )

                return (
                  <TimetableCell
                    key={date}
                    cell={cell}
                    date={date}
                    time={time}
                    slots={doctorSlots}
                    tenantId={tenantId}
                    selected={selected}
                    onPointerDown={(event) =>
                      interaction.startDrag(event, cell, selected)
                    }
                    onClick={(event) =>
                      interaction.toggleCell(event, cell, selected)
                    }
                    onKeyDown={(event) => interaction.moveFocus(event, cell)}
                  />
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
