import { useEffect, useRef } from 'react'
import type { Slot } from './fixtures'
import { slotStart } from './fixtures'
import { applyDragSelection, deselectCell, isSelected, times, updateSelections } from './timetable'
import type { Cell, Selection } from './timetable'

const dayLabel = (date: string) => new Intl.DateTimeFormat('en-SG', { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC' }).format(new Date(date))

export function WeeklyTimetable({ slots, tenantId, doctorId, dates, selections, onChange }: {
  slots: Slot[]; tenantId: string; doctorId: string; dates: string[]
  selections: Selection[]; onChange: (selections: Selection[]) => void
}) {
  const viewport = useRef<HTMLDivElement>(null)
  const anchor = useRef<Cell | null>(null)
  const dragging = useRef(false)
  const extending = useRef(false)
  const beforeDrag = useRef<Selection[]>([])
  useEffect(() => { if (viewport.current) viewport.current.scrollTop = 16 * 32 }, [])
  const doctorSlots = slots.filter(slot => slot.doctor_id === doctorId)

  return <div ref={viewport} className="max-h-[620px] overflow-auto rounded-xl border" aria-label="Weekly availability timetable">
    <table className="w-full min-w-[780px] table-fixed select-none border-collapse text-sm" onPointerMove={event => {
      if (!dragging.current || !anchor.current) return
      const cell = document.elementFromPoint(event.clientX, event.clientY)?.closest<HTMLElement>('[data-day][data-row]')
      if (cell && event.currentTarget.contains(cell)) onChange(applyDragSelection(beforeDrag.current, { from: anchor.current, to: { day: Number(cell.dataset.day), row: Number(cell.dataset.row) } }))
    }} onPointerUp={() => { dragging.current = false }} onLostPointerCapture={() => { dragging.current = false }} onPointerCancel={() => { dragging.current = false; onChange(beforeDrag.current) }}
      onKeyDown={event => { if (event.key === 'Escape') { dragging.current = false; anchor.current = null; onChange([]) } }}>
      <thead className="sticky top-0 z-10 bg-white shadow-sm"><tr>
        <th className="w-20 border-b px-2 py-4 text-xs text-slate-500">SGT</th>
        {dates.map(date => <th key={date} scope="col" className="border-b border-l px-2 py-4 font-medium">{dayLabel(date)}</th>)}
      </tr></thead>
      <tbody>{times.map((time, row) => <tr key={time}>
        <th scope="row" className="h-8 border-t px-2 align-top text-xs font-normal text-slate-500">{time}</th>
        {dates.map((date, day) => {
          const start = slotStart(date, time)
          const overlaps = doctorSlots.filter(slot => Date.parse(slot.starts_at) < start + 1800000 && Date.parse(slot.ends_at) > start)
          const foreign = overlaps.some(slot => slot.tenant_id !== tenantId)
          const unavailable = overlaps.some(slot => slot.availability !== 'available')
          const past = start <= Date.now()
          const selected = selections.some(range => isSelected(range, day, row))
          const status = foreign ? 'Other clinic' : unavailable ? 'Unavailable' : overlaps.length ? 'Available' : past ? 'Past' : 'Empty'
          const colour = foreign ? 'bg-violet-100 text-violet-900' : unavailable ? 'bg-slate-200 text-slate-700' : overlaps.length ? 'bg-emerald-100 text-emerald-900' : past ? 'bg-slate-50 text-slate-400' : 'bg-white hover:bg-sky-50'
          return <td key={date} className="border-t border-l p-0">
            <button type="button" data-day={day} data-row={row} aria-label={`${date} ${time} SGT, ${status}`} aria-pressed={selected}
              className={`block h-8 w-full touch-none overflow-hidden px-1 text-xs outline-offset-[-3px] focus-visible:outline-2 focus-visible:outline-sky-700 ${colour} ${selected ? 'ring-2 ring-inset ring-sky-600 brightness-95' : ''}`}
              onPointerDown={event => {
                if (event.button !== 0) return
                event.preventDefault(); event.currentTarget.focus()
                const cell = { day, row }
                beforeDrag.current = selections
                anchor.current = cell; dragging.current = true; extending.current = !selected
                event.currentTarget.closest('table')!.setPointerCapture(event.pointerId)
                onChange(applyDragSelection(beforeDrag.current, { from: cell, to: cell }))
              }} onClick={event => {
                if (event.detail !== 0) return
                const cell = { day, row }
                if (selected && !event.shiftKey) {
                  extending.current = false; anchor.current = cell
                  onChange(deselectCell(selections, cell))
                  return
                }
                onChange(updateSelections(selections, { from: event.shiftKey && anchor.current ? anchor.current : cell, to: cell }, event.shiftKey && extending.current))
                if (!event.shiftKey || !anchor.current) anchor.current = cell
                extending.current = true
              }} onKeyDown={event => {
                const offsets: Record<string, [number, number]> = { ArrowUp: [0, -1], ArrowDown: [0, 1], ArrowLeft: [-1, 0], ArrowRight: [1, 0] }
                const offset = offsets[event.key]
                if (!offset) return
                event.preventDefault()
                const next = { day: Math.max(0, Math.min(6, day + offset[0])), row: Math.max(0, Math.min(47, row + offset[1])) }
                event.currentTarget.closest('table')?.querySelector<HTMLButtonElement>(`[data-day="${next.day}"][data-row="${next.row}"]`)?.focus()
                if (event.shiftKey) {
                  if (!anchor.current) anchor.current = { day, row }
                  onChange(updateSelections(selections, { from: anchor.current, to: next }, extending.current))
                  extending.current = true
                } else { anchor.current = next; extending.current = false }
              }}>{status === 'Empty' || status === 'Past' ? '' : status}</button>
          </td>
        })}
      </tr>)}</tbody>
    </table>
  </div>
}
