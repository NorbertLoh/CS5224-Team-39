import { addSlot, removeSlot, slotStart } from './fixtures'
import type { Slot } from './fixtures'

export type Cell = { day: number; row: number }
export type Selection = { from: Cell; to: Cell }
export const times = Array.from({ length: 48 }, (_, index) => `${String(Math.floor(index / 2)).padStart(2, '0')}:${index % 2 ? '30' : '00'}`)

export function shiftDate(date: string, days: number) {
  return new Date(Date.parse(date) + days * 86400000).toISOString().slice(0, 10)
}

export function weekStart(date: string) {
  return shiftDate(date, -((new Date(date).getUTCDay() + 6) % 7))
}

export function isSelected(selection: Selection | null, day: number, row: number) {
  return Boolean(selection && day >= Math.min(selection.from.day, selection.to.day) && day <= Math.max(selection.from.day, selection.to.day) &&
    row >= Math.min(selection.from.row, selection.to.row) && row <= Math.max(selection.from.row, selection.to.row))
}

export function cellsInSelection(selection: Selection, dates: string[]) {
  return dates.flatMap((date, day) => times.flatMap((time, row) => isSelected(selection, day, row) ? [{ date, time, start: slotStart(date, time) }] : []))
}

export function updateSelections(selections: Selection[], next: Selection | null, extend = false): Selection[] {
  if (!next) return []
  return [...(extend ? selections.slice(0, -1) : selections), next]
}

export function deselectCell(selections: Selection[], cell: Cell): Selection[] {
  return selections.flatMap(range => {
    if (!isSelected(range, cell.day, cell.row)) return [range]
    const left = Math.min(range.from.day, range.to.day)
    const right = Math.max(range.from.day, range.to.day)
    const top = Math.min(range.from.row, range.to.row)
    const bottom = Math.max(range.from.row, range.to.row)
    const remaining: Selection[] = []
    if (top < cell.row) remaining.push({ from: { day: left, row: top }, to: { day: right, row: cell.row - 1 } })
    if (bottom > cell.row) remaining.push({ from: { day: left, row: cell.row + 1 }, to: { day: right, row: bottom } })
    if (left < cell.day) remaining.push({ from: { day: left, row: cell.row }, to: { day: cell.day - 1, row: cell.row } })
    if (right > cell.day) remaining.push({ from: { day: cell.day + 1, row: cell.row }, to: { day: right, row: cell.row } })
    return remaining
  })
}

export function cellsInSelections(selections: Selection[], dates: string[]) {
  const unique = new Map<number, ReturnType<typeof cellsInSelection>[number]>()
  for (const range of selections) for (const cell of cellsInSelection(range, dates)) unique.set(cell.start, cell)
  return [...unique.values()].sort((a, b) => a.start - b.start)
}

export function applySelection(slots: Slot[], tenantId: string, doctorId: string, selections: Selection[], dates: string[], action: 'add' | 'remove', now = Date.now()) {
  const cells = cellsInSelections(selections, dates)
  if (action === 'add') return cells.reduce((result, cell) => addSlot(result, tenantId, doctorId, cell.date, cell.time, now), slots)
  const selected = slots.filter(slot => slot.doctor_id === doctorId && cells.some(cell => Date.parse(slot.starts_at) < cell.start + 1800000 && Date.parse(slot.ends_at) > cell.start))
  if (!selected.length) throw new Error('There is no availability to remove in this selection.')
  if (selected.some(slot => slot.tenant_id !== tenantId)) throw new Error('This selection includes another clinic. Choose that clinic to edit its availability.')
  return selected.reduce((result, slot) => removeSlot(result, slot.slot_id, tenantId, doctorId, now), slots)
}
