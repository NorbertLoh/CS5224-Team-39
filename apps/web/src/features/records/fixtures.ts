import example from '../../../../../contracts/examples/prescription-order-quote.json'

export const prescriptionFixture = example.prescription
export type Prescription = Omit<typeof prescriptionFixture, 'status' | 'issued_at'> & {
  status: 'draft' | 'issued' | 'voided'
  issued_at: string | null
}
export type PrescriptionInput = {
  medication_id: string
  quantity: number
  instructions: string
}
export const catalogue = prescriptionFixture.items.map(item => ({
  medication_id: item.medication_id,
  display_name: item.display_name,
}))

export function validItems(items: PrescriptionInput[]) {
  return items.length > 0 && items.every(item =>
    catalogue.some(medication => medication.medication_id === item.medication_id) &&
    Number.isSafeInteger(item.quantity) && item.quantity > 0 &&
    Boolean(item.instructions.trim()),
  ) && new Set(items.map(item => item.medication_id)).size === items.length
}

export function draftPrescription(items: PrescriptionInput[]): Prescription {
  if (!validItems(items)) throw new Error('Select a catalogue item, a whole positive quantity and instructions. Each item may appear once.')
  const now = new Date().toISOString()
  return {
    ...prescriptionFixture,
    status: 'draft',
    issued_at: null,
    created_at: now,
    updated_at: now,
    items: items.map((item, index) => ({
      ...item,
      instructions: item.instructions.trim(),
      display_name: catalogue.find(medication => medication.medication_id === item.medication_id)!.display_name,
      prescription_item_id: prescriptionFixture.items[index]?.prescription_item_id ?? crypto.randomUUID(),
    })),
  }
}
