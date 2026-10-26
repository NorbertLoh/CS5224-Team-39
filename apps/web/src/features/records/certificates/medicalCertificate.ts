export type MedicalCertificate = {
  medical_certificate_id: string
  appointment_id: string
  tenant_id: string
  selected: boolean
  start_date: string | null
  duration_days: number | null
  additional_notes: string
  end_date: string | null
  finalized_at: string | null
  issued_at: string | null
}

// Calendar arithmetic is UTC here so browser timezones/DST cannot shift an SG date.
export function mcEndDate(start: string, days: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^[1-9]\d*$/.test(days))
    return null
  const count = Number(days)
  const date = new Date(`${start}T00:00:00Z`)
  if (
    !Number.isSafeInteger(count) ||
    Number.isNaN(date.getTime()) ||
    date.toISOString().slice(0, 10) !== start
  )
    return null
  date.setUTCDate(date.getUTCDate() + count - 1)
  if (Number.isNaN(date.getTime()) || date.getUTCFullYear() > 9999) return null
  return date.toISOString().slice(0, 10)
}
