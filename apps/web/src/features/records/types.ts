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
  display_name?: string
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
  unit_price: { amount_minor: number; currency: 'SGD' } | null
  updated_at: string
}
