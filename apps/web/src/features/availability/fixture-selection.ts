import { addSlot, removeSlot } from './fixtures'
import type { Slot } from './fixtures'
import { cellsInSelections } from './timetable'
import type { Selection } from './timetable'

export function applySelection(
  slots: Slot[],
  tenantId: string,
  doctorId: string,
  selections: Selection[],
  dates: string[],
  action: 'add' | 'remove',
  now = Date.now(),
) {
  const cells = cellsInSelections(selections, dates)
  if (action === 'add')
    return cells.reduce(
      (result, cell) =>
        addSlot(result, tenantId, doctorId, cell.date, cell.time, now),
      slots,
    )
  const selected = slots.filter(
    (slot) =>
      slot.doctor_id === doctorId &&
      cells.some(
        (cell) =>
          Date.parse(slot.starts_at) < cell.start + 1800000 &&
          Date.parse(slot.ends_at) > cell.start,
      ),
  )
  if (!selected.length)
    throw new Error('There is no availability to remove in this selection.')
  if (selected.some((slot) => slot.tenant_id !== tenantId))
    throw new Error(
      'This selection includes another clinic. Choose that clinic to edit its availability.',
    )
  return selected.reduce(
    (result, slot) => removeSlot(result, slot.slot_id, tenantId, doctorId, now),
    slots,
  )
}
