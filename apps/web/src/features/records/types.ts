// C04 wire shapes from services/clinical_records/app/schemas.py.
export type RecordContext = {
  tenant_id: string
  appointment_id: string
  patient_id: string
  doctor_id: string
  created_at: string
  updated_at: string
}
export type Note = RecordContext & { note_id: string; text: string }
export type PrescriptionInput = {
  medication_id: string
  quantity: number
  instructions: string
}
export type Prescription = RecordContext & {
  prescription_id: string
  status: 'draft' | 'issued' | 'voided'
  issued_at: string | null
  items: (PrescriptionInput & {
    prescription_item_id: string
    display_name: string
  })[]
}
export type Medication = {
  tenant_id: string
  medication_id: string
  display_name: string
  unit_label: string
  active: boolean
}
export function prescriptionItems(
  items: PrescriptionInput[],
): PrescriptionInput[] {
  return items.map(({ medication_id, quantity, instructions }) => ({
    medication_id,
    quantity,
    instructions: instructions.trim(),
  }))
}
export function validItems(items: PrescriptionInput[]) {
  return (
    items.length > 0 &&
    items.length <= 100 &&
    items.every(
      (item) =>
        Boolean(item.medication_id) &&
        Number.isSafeInteger(item.quantity) &&
        item.quantity > 0 &&
        item.quantity <= 10000 &&
        Boolean(item.instructions.trim()) &&
        item.instructions.trim().length <= 20000,
    ) &&
    new Set(items.map((item) => item.medication_id)).size === items.length
  )
}
