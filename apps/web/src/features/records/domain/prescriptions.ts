import type { PrescriptionInput } from '../types'

export function prescriptionItems(
  items: PrescriptionInput[],
): PrescriptionInput[] {
  return items.map(
    ({ medication_id, display_name, quantity, instructions }) => ({
      medication_id,
      ...(display_name !== undefined
        ? { display_name: display_name.trim() }
        : {}),
      quantity,
      instructions: instructions.trim(),
    }),
  )
}

export function validItems(items: PrescriptionInput[]) {
  return (
    items.length > 0 &&
    items.length <= 100 &&
    items.every(
      (item) =>
        Boolean(item.medication_id || item.display_name?.trim()) &&
        (item.display_name?.trim().length ?? 0) <= 200 &&
        Number.isSafeInteger(item.quantity) &&
        item.quantity > 0 &&
        item.quantity <= 10000 &&
        Boolean(item.instructions.trim()) &&
        item.instructions.trim().length <= 20000,
    ) &&
    new Set(
      items.map(
        (item) => item.display_name?.trim().toLowerCase() || item.medication_id,
      ),
    ).size === items.length
  )
}
