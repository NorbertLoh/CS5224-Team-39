import { slotStart } from '@/features/availability/slot-time'

export type Cell = { day: number; row: number }
export type Selection = { from: Cell; to: Cell }
export const times = Array.from(
  { length: 48 },
  (_, index) =>
    `${String(Math.floor(index / 2)).padStart(2, '0')}:${index % 2 ? '30' : '00'}`,
)

export function shiftDate(date: string, days: number) {
  return new Date(Date.parse(date) + days * 86400000).toISOString().slice(0, 10)
}

export function weekStart(date: string) {
  return shiftDate(date, -((new Date(date).getUTCDay() + 6) % 7))
}

export function isSelected(
  selection: Selection | null,
  day: number,
  row: number,
) {
  return Boolean(
    selection &&
      day >= Math.min(selection.from.day, selection.to.day) &&
      day <= Math.max(selection.from.day, selection.to.day) &&
      row >= Math.min(selection.from.row, selection.to.row) &&
      row <= Math.max(selection.from.row, selection.to.row),
  )
}

export function cellsInSelection(selection: Selection, dates: string[]) {
  return dates.flatMap((date, day) =>
    times.flatMap((time, row) =>
      isSelected(selection, day, row)
        ? [{ date, time, start: slotStart(date, time) }]
        : [],
    ),
  )
}

export function updateSelections(
  selections: Selection[],
  next: Selection | null,
  extend = false,
): Selection[] {
  if (!next) return []
  return [...(extend ? selections.slice(0, -1) : selections), next]
}

export function deselectRange(
  selections: Selection[],
  area: Selection,
): Selection[] {
  return selections.flatMap((range) => {
    const left = Math.min(range.from.day, range.to.day)
    const right = Math.max(range.from.day, range.to.day)
    const top = Math.min(range.from.row, range.to.row)
    const bottom = Math.max(range.from.row, range.to.row)
    const cutLeft = Math.max(left, Math.min(area.from.day, area.to.day))
    const cutRight = Math.min(right, Math.max(area.from.day, area.to.day))
    const cutTop = Math.max(top, Math.min(area.from.row, area.to.row))
    const cutBottom = Math.min(bottom, Math.max(area.from.row, area.to.row))
    if (cutLeft > cutRight || cutTop > cutBottom) return [range]
    const remaining: Selection[] = []
    if (top < cutTop)
      remaining.push({
        from: { day: left, row: top },
        to: { day: right, row: cutTop - 1 },
      })
    if (bottom > cutBottom)
      remaining.push({
        from: { day: left, row: cutBottom + 1 },
        to: { day: right, row: bottom },
      })
    if (left < cutLeft)
      remaining.push({
        from: { day: left, row: cutTop },
        to: { day: cutLeft - 1, row: cutBottom },
      })
    if (right > cutRight)
      remaining.push({
        from: { day: cutRight + 1, row: cutTop },
        to: { day: right, row: cutBottom },
      })
    return remaining
  })
}

export function deselectCell(selections: Selection[], cell: Cell): Selection[] {
  return deselectRange(selections, { from: cell, to: cell })
}

// Always use the selection at pointer-down so reversing/shrinking a drag restores cells.
export function applyDragSelection(
  before: Selection[],
  area: Selection,
): Selection[] {
  return before.some((range) => isSelected(range, area.from.day, area.from.row))
    ? deselectRange(before, area)
    : [...before, area]
}

export function cellsInSelections(selections: Selection[], dates: string[]) {
  const unique = new Map<number, ReturnType<typeof cellsInSelection>[number]>()
  for (const range of selections)
    for (const cell of cellsInSelection(range, dates))
      unique.set(cell.start, cell)
  return [...unique.values()].sort((a, b) => a.start - b.start)
}
