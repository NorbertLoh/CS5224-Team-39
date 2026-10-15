import example from '../../../../../contracts/examples/prescription-order-quote.json'

export const prescriptionFixture = example.prescription
export type Prescription = Omit<typeof prescriptionFixture, 'status' | 'issued_at'> & {
  status: 'draft' | 'issued' | 'voided'
  issued_at: string | null
}
export type PrescriptionInput = {
  display_name: string
  quantity: number
  instructions: string
}
// Free-text preview entries are not catalogue-linked API prescription items.
export type PreviewPrescription = Omit<Prescription, 'items'> & {
  items: (PrescriptionInput & { prescription_item_id: string })[]
}

export function validItems(items: PrescriptionInput[]) {
  return items.length > 0 && items.every(item =>
    Boolean(item.display_name.trim()) &&
    Number.isSafeInteger(item.quantity) && item.quantity > 0 &&
    Boolean(item.instructions.trim()),
  ) && new Set(items.map(item => item.display_name.trim().toLowerCase())).size === items.length
}

export function draftPrescription(items: PrescriptionInput[]): PreviewPrescription {
  if (!validItems(items)) throw new Error('Enter a medication name, a whole positive quantity and instructions. Each medication may appear once.')
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
      display_name: item.display_name.trim(),
      prescription_item_id: prescriptionFixture.items[index]?.prescription_item_id ?? crypto.randomUUID(),
    })),
  }
}
